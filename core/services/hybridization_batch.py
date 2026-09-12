"""Immutable batch plans and file-backed results for hybridization analysis."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
import json
import numpy as np
from PySide6.QtCore import QThread, Signal
from core.loader import DataLoader
from core.pdos_metadata import input_context_from_entry, PDOSInputContext
from core.parsers.common import resolve_selection, _site_symbol, _load_structure_file
from core.orbital_selection import resolve_orbital_request, materialize_orbital_outputs
from core.services.file_identity import context_fingerprint

MODES = (
    "One to one", "One to many (individual)", "One to many (merged)",
    "Many to many (ordered)", "Many to many (all pairs)", "Group to group",
)


def pair_selections(left, right, mode):
    if not left or not right:
        raise ValueError("Both fragments need at least one atom.")
    if mode == MODES[0]:
        if len(left) != 1 or len(right) != 1:
            raise ValueError("One-to-one requires exactly one atom on each side.")
        pairs = [(left, right)]
    elif mode in MODES[1:3]:
        if len(left) != 1:
            raise ValueError("One-to-many requires exactly one atom in Fragment 1.")
        pairs = [([left[0]], [r]) for r in right] if mode == MODES[1] else [(left, right)]
    elif mode == MODES[3]:
        if len(left) != len(right):
            raise ValueError("Ordered pairing requires equal atom counts.")
        pairs = [([l], [r]) for l, r in zip(left, right)]
    elif mode == MODES[4]:
        if len(left) * len(right) > 10000:
            raise ValueError("More than 10,000 pairs. Narrow the atom selection.")
        pairs = [([l], [r]) for l, r in product(left, right)]
    elif mode == MODES[5]:
        pairs = [(left, right)]
    else:
        raise ValueError("Unknown pairing mode.")
    if any(set(l) & set(r) for l, r in pairs):
        raise ValueError("A pair contains the same atom in both fragments. Adjust the selections.")
    return [(tuple(l), tuple(r)) for l, r in pairs]


@dataclass(frozen=True)
class BatchTask:
    system: str
    context: PDOSInputContext
    fingerprint: tuple
    left: tuple
    right: tuple
    orbitals1: tuple
    orbitals2: tuple
    alias1: str
    alias2: str
    spin: str
    mode: str

    def title(self):
        return f"{self.system}: {','.join(map(str,self.left))} → {','.join(map(str,self.right))}"


def prepare_row(row, orbs1, orbs2, spin, aliases, mode):
    entry = row['entry']
    fmt = (entry.get('capabilities') or {}).get('source_format') or DataLoader.detect(entry['path'])
    context = input_context_from_entry(entry, fmt)
    if fmt not in ('vasprun.xml', 'DOSCAR'):
        raise ValueError("Batch atom pairing requires vasprun.xml or DOSCAR with atom-resolved PDOS. Use single analysis for pre-aggregated PDOS files.")
    source_identity = context_fingerprint(context)
    caps = DataLoader.inspect(context)
    resolve_orbital_request(orbs1, caps)
    resolve_orbital_request(orbs2, caps)
    if fmt == 'vasprun.xml':
        from core.parsers.vasprun import _get_structure_from_vasprun_or_poscar
        structure = _get_structure_from_vasprun_or_poscar(context.primary_path, structure_path=context.structure_path)
        count = len(structure)
    else:
        from core.parsers.doscar import _read_doscar_raw
        count = len(_read_doscar_raw(context.primary_path)[2])
        structure = _load_structure_file(context.structure_path) if context.structure_path else None
    symbols = [_site_symbol(site) for site in structure] if structure is not None else None
    if not row['left'].strip() or not row['right'].strip():
        raise ValueError("Enter explicit atom selections for both fragments.")
    left = [i + 1 for i in resolve_selection(row['left'], count, symbols)]
    right = [i + 1 for i in resolve_selection(row['right'], count, symbols)]
    for values, field in ((left, 'element1'), (right, 'element2')):
        expected = row.get(field, '').strip()
        if expected and symbols is None:
            raise ValueError("Element validation requires an explicitly selected structure.")
        if expected and any(symbols[i-1] != expected for i in values):
            raise ValueError(f"Selected atoms do not all match expected element {expected}.")
    if context_fingerprint(context) != source_identity:
        raise ValueError("Source changed during preview. Preview again.")
    return [BatchTask(entry.get('label', Path(entry['path']).name), context,
        source_identity, l, r, tuple(orbs1), tuple(orbs2),
        aliases[0], aliases[1], spin, mode) for l,r in pair_selections(left, right, mode)]


def write_result(path, data1, data2):
    arrays = {}
    metadata = []
    for i, (e, up, down, orbitals, label) in enumerate((data1, data2)):
        arrays[f'e{i}'] = e
        metadata.append([list(orbitals), label, up is not None, down is not None])
        for name, rho in (('u', up), ('d', down)):
            for orb, values in (rho or {}).items():
                arrays[f'{i}_{name}_{orb}'] = values
    arrays['metadata'] = np.array(json.dumps(metadata))
    np.savez_compressed(path, **arrays)


def read_result(path):
    with np.load(path, allow_pickle=False) as stored:
        result = []
        for i, (orbitals, label, has_up, has_down) in enumerate(json.loads(str(stored['metadata']))):
            up = {o: stored[f'{i}_u_{o}'] for o in orbitals} if has_up else None
            down = {o: stored[f'{i}_d_{o}'] for o in orbitals} if has_down else None
            result.append((stored[f'e{i}'], up, down, orbitals, label))
        return tuple(result)


class BatchPreviewWorker(QThread):
    row_ready = Signal(int, object, str)

    def __init__(self, rows, orbs1, orbs2, spin, aliases, mode, parent=None):
        super().__init__(parent)
        self.arguments = rows, orbs1, orbs2, spin, aliases, mode

    def run(self):
        rows, *options = self.arguments
        for i, row in enumerate(rows):
            if self.isInterruptionRequested():
                break
            try:
                self.row_ready.emit(i, prepare_row(row, *options), '')
            except Exception as exc:
                self.row_ready.emit(i, [], str(exc))


class BatchAnalysisWorker(QThread):
    task_ready = Signal(int, str, str)
    progress = Signal(str)

    def __init__(self, tasks, directory, parent=None):
        super().__init__(parent)
        self.tasks = list(tasks)  # (stable row id, frozen task)
        self.directory = Path(directory)

    def run(self):
        groups = {}
        for index, task in self.tasks:
            groups.setdefault(task.context, []).append((index, task))
        for context, group in groups.items():
            if self.isInterruptionRequested():
                break
            atom_data = {}
            try:
                self.progress.emit(f"Reading {group[0][1].system} ({len(group)} tasks)…")
                if any(context_fingerprint(context) != task.fingerprint for _,task in group):
                    raise ValueError("Source files changed after preview. Generate a new preview.")
                caps = DataLoader.inspect(context)
                requested = tuple(dict.fromkeys(o for _,t in group for o in t.orbitals1+t.orbitals2))
                resolved = resolve_orbital_request(requested, caps)
                atoms = sorted({a for _,t in group for a in t.left+t.right})
                if context.source_format == 'vasprun.xml':
                    from core.parsers.vasprun import parse_vasprun_spin_all as parser
                else:
                    from core.parsers.doscar import parse_doscar_spin_all as parser
                parser(context.primary_path, ','.join(map(str, atoms)),
                    orbitals=list(resolved.parser_orbitals), input_context=context, per_atom_output=atom_data)
                if context_fingerprint(context) != group[0][1].fingerprint:
                    raise ValueError("Source changed while parsing. Generate a new preview.")
            except Exception as exc:
                for index, task in group:
                    self.task_ready.emit(index, '', str(exc))
                continue
            for index, task in group:
                if self.isInterruptionRequested():
                    break
                try:
                    data = []
                    for atoms, orbs, alias in ((task.left,task.orbitals1,task.alias1), (task.right,task.orbitals2,task.alias2)):
                        request = resolve_orbital_request(orbs, caps)
                        energy, _, _, _, ef = atom_data[atoms[0]]
                        up = {o: sum(atom_data[a][1][o] for a in atoms) for o in request.parser_orbitals}
                        down = {o: sum(atom_data[a][2][o] for a in atoms) for o in request.parser_orbitals}
                        up = materialize_orbital_outputs(up, request)
                        down = materialize_orbital_outputs(down, request)
                        if task.spin == 'up':
                            down = None
                        elif task.spin == 'down':
                            up = None
                        elif caps.spin_mode == 'nonspin':
                            down = None
                        data.append((energy-ef, up, down, list(orbs), f"{task.system} / {alias}"))
                    path = str(self.directory / f'{index:05d}.npz')
                    write_result(path, *data)
                    self.task_ready.emit(index, path, '')
                except Exception as exc:
                    self.task_ready.emit(index, '', str(exc))
            atom_data.clear()
