"""vasprun.xml parser (pymatgen-based)."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.exceptions import DbandError
from core.parsers.common import (
    _ensure_pymatgen,
    _PYMATGEN_ORB_MAP,
    _resolve_atom_indices, _ensure_positive, _site_symbol,
)
from core.parsers.constants import _ORB_TYPE_TO_ORBITALS, all_orb_names
from core.parsers.doscar import _project_noncollinear_spin

_logger = logging.getLogger("dband.parsers")

# VASP <field> name → internal orbital name.  Lifted to module level to avoid
# re-creating the same dict on every atom iteration (was S-5).
_VASP_FIELD_MAP: dict[str, str] = {
    "s": "s", "py": "py", "pz": "pz", "px": "px",
    "dxy": "dxy", "dyz": "dyz", "dz2": "dz2", "dxz": "dxz",
    "x2-y2": "dx2-y2", "dx2": "dx2-y2", "dx2-y2": "dx2-y2",
    "f-3": "f-3", "f-2": "f-2", "f-1": "f-1",
    "f0": "f0", "f1": "f1", "f2": "f2", "f3": "f3",
    "f_3": "f-3", "f_2": "f-2", "f_1": "f-1",
}

# Bounded LRU cache for parsed structures (prevents unbounded memory growth
# when many distinct vasprun.xml files are loaded in one session).
_STRUCT_CACHE: dict = {}
_STRUCT_CACHE_MAX = 32


def _classify_vasprun_partial_layout(data_width: int, field_count: int) -> str:
    """Classify one ``<partial>`` DOS row without guessing its physics.

    ``data_width`` excludes the leading energy value and ``field_count`` is
    the number of orbital fields declared by VASP.  Collinear vasprun.xml
    uses separate ``spin 1``/``spin 2`` sets, so each row has one value per
    field.  A noncollinear/SOC site PDOS row carries four values per field:
    total, m1, m2 and m3.
    """
    if field_count <= 0:
        raise DbandError("vasprun.xml has no orbital fields in <partial> DOS.")
    if data_width == field_count:
        return "scalar"
    if data_width == 4 * field_count:
        return "noncollinear"
    raise DbandError(
        "Unsupported vasprun.xml partial DOS row: "
        f"{data_width} data columns for {field_count} declared orbital fields. "
        "Refusing to guess an orbital or spin-component mapping.")


def _field_targets(field_name: str, target_orbs: List[str]) -> List[Tuple[str, float]]:
    """Map one VASP field to requested output channels without fabrication.

    LORBIT=10 reports l-resolved values (``d``), not five m-resolved d
    orbitals.  The aggregate is therefore returned only when the caller
    explicitly requests ``d``.  It is never divided equally into dxy/dyz/
    dz2/dxz/dx2-y2.
    """
    name = field_name.strip().lower()
    mapped = _VASP_FIELD_MAP.get(name)
    if mapped is not None:
        return [(mapped, 1.0)] if mapped in target_orbs else []
    if name in _ORB_TYPE_TO_ORBITALS:
        if name in target_orbs:
            return [(name, 1.0)]
        return []
    return []


def _accumulate_vasprun_noncollinear(
    raw_by_atom: Dict[int, np.ndarray],
    target_indices: List[int],
    orb_fields: List[str],
    target_orbs: List[str],
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """Sum VASP total/m3 PDOS, then reconstruct the SAXIS projections."""
    if not raw_by_atom:
        raise DbandError("vasprun.xml contains no selected site-projected DOS rows.")

    first = next(iter(raw_by_atom.values()))
    if first.ndim != 2 or first.shape[0] == 0:
        raise DbandError("vasprun.xml selected PDOS data are empty or malformed.")
    n_energy = first.shape[0]
    totals = {orb: np.zeros(n_energy, dtype=np.float64) for orb in target_orbs}
    m3s = {orb: np.zeros(n_energy, dtype=np.float64) for orb in target_orbs}

    for idx in target_indices:
        if idx not in raw_by_atom:
            raise DbandError(
                f"vasprun.xml has no PDOS rows for selected atom index {idx + 1}.")
        arr = np.asarray(raw_by_atom[idx], dtype=np.float64)
        if arr.ndim != 2 or arr.shape[0] != n_energy:
            raise DbandError("vasprun.xml selected atoms have inconsistent PDOS energy grids.")
        if _classify_vasprun_partial_layout(arr.shape[1], len(orb_fields)) != "noncollinear":
            raise DbandError("Expected noncollinear total/m1/m2/m3 site-PDOS rows.")
        if not np.isfinite(arr).all():
            raise DbandError("vasprun.xml noncollinear PDOS contains NaN or Inf.")
        for field_index, field_name in enumerate(orb_fields):
            for orbital, scale in _field_targets(field_name, target_orbs):
                totals[orbital] += arr[:, field_index * 4] * scale
                m3s[orbital] += arr[:, field_index * 4 + 3] * scale

    up, down = {}, {}
    for orbital in target_orbs:
        up[orbital], down[orbital] = _project_noncollinear_spin(
            totals[orbital], m3s[orbital])
    return up, down, totals


def _structure_cache_key(filepath: str):
    """Cache key that changes when a vasprun.xml file is replaced in place."""
    import os

    abspath = os.path.abspath(filepath)
    try:
        st = os.stat(abspath)
        return (abspath, st.st_mtime_ns, st.st_size)
    except OSError:
        return (abspath, 0, 0)


def _struct_cache_put(key, value):
    _STRUCT_CACHE[key] = value
    while len(_STRUCT_CACHE) > _STRUCT_CACHE_MAX:
        # Pop the oldest entry (FIFO is sufficient here; structure reuse is rare).
        _STRUCT_CACHE.pop(next(iter(_STRUCT_CACHE)))

def _get_structure_from_vasprun_or_poscar(filepath: str):
    """Resolve the Structure that defines atom ordering for PDOS indexing.

    Priority (critical for correctness):
        1. Parse the structure embedded INSIDE vasprun.xml (lxml fast path).
           The ``<set comment="ion N">`` PDOS blocks follow the *internal*
           atom order, which VASP may reorder relative to POSCAR (due to
           LREAL, symmetry, SYMPREC).  Only the in-file structure is
           guaranteed to match the PDOS ion ordering.
        2. CONTCAR (final relaxed structure — closer to actual than POSCAR).
        3. POSCAR (input structure — last resort; may be misaligned).

    A WARNING is logged whenever the vasprun-internal parse fails and we
    fall back to CONTCAR/POSCAR, because atom-index misalignment is silent
    and scientifically fatal.
    """
    import os
    from core.parsers.common import get_pymatgen_classes
    import core.parsers.common as _cmn

    cache_key = _structure_cache_key(filepath)
    if cache_key in _STRUCT_CACHE:
        return _STRUCT_CACHE[cache_key]

    dir_path = os.path.dirname(filepath)
    if not dir_path:
        dir_path = "."

    # ── 1. Preferred: structure embedded in vasprun.xml ──────────────
    try:
        from lxml import etree as ET
        from pymatgen.core import Structure, Lattice

        context = ET.iterparse(filepath, events=('start', 'end'))
        atoms = []
        basis = []
        positions = []

        in_atoms = False
        in_finalpos = False
        current_varray = None

        for ev, el in context:
            tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
            name = el.attrib.get('name', '')

            if ev == 'start':
                if tag == 'array' and name == 'atoms':
                    in_atoms = True
                elif tag == 'structure' and name == 'finalpos':
                    in_finalpos = True
                elif tag == 'varray':
                    current_varray = name
            elif ev == 'end':
                if tag == 'array' and in_atoms:
                    in_atoms = False
                elif tag == 'structure' and in_finalpos:
                    in_finalpos = False
                    break
                elif tag == 'varray':
                    current_varray = None

                # NOTE: previously nested under a redundant ``if ev == 'end'``
                # that was always True here (we are already in the end-branch).
                if in_atoms and tag == 'rc':
                    c_elements = [x for x in el if x.tag.endswith('}c') or x.tag == 'c']
                    if c_elements and c_elements[0].text:
                        atoms.append(c_elements[0].text.strip())
                elif in_finalpos and tag == 'v':
                    if current_varray == 'basis':
                        if el.text: basis.append([float(x) for x in el.text.split()])
                    elif current_varray == 'positions':
                        if el.text: positions.append([float(x) for x in el.text.split()])

                # Safe element cleanup: only clear leaf elements that are
                # NOT inside an active target array, to avoid corrupting
                # the ancestor chain being iterated.  We deliberately do
                # NOT use the ``while el.getprevious(): del parent[0]``
                # pattern here — it can delete siblings of an ancestor
                # still held by an outer scope, corrupting the parse.
                if not in_atoms and not in_finalpos:
                    el.clear()

        if atoms and basis and positions and len(atoms) == len(positions):
            struct = Structure(Lattice(basis), atoms, positions)
            _struct_cache_put(cache_key, struct)
            return struct
        # If in-file parse yielded incomplete data, fall through to POSCAR.
        _logger.debug(
            "%s: in-file structure incomplete (atoms=%d, pos=%d); "
            "falling back to CONTCAR/POSCAR.",
            filepath, len(atoms), len(positions))
    except Exception as e:
        _logger.debug("%s: in-file lxml structure parse failed (%s); "
                      "falling back to CONTCAR/POSCAR.", filepath, e)

    # ── 2/3. Fallback: CONTCAR then POSCAR (with WARNING) ────────────
    pmg = get_pymatgen_classes()
    for name in ("CONTCAR", "POSCAR"):
        candidate = os.path.join(dir_path, name)
        if os.path.exists(candidate):
            try:
                struct = pmg["Poscar"].from_file(candidate).structure
                _logger.warning(
                    "%s: using %s for atom indexing.  If VASP reordered "
                    "atoms (LREAL/symmetry), PDOS ion indices may be "
                    "MISALIGNED.  For guaranteed-correct indexing, keep "
                    "the full vasprun.xml (it embeds the matching structure).",
                    filepath, name)
                _struct_cache_put(cache_key, struct)
                return struct
            except Exception:
                pass

    # ── Last resort: full pymatgen Vasprun parse (slow but complete) ──
    try:
        v = _cmn._Vasprun(filepath, parse_projected_eigen=False,
                          parse_dos=False, parse_eigen=False)
        struct = v.final_structure
        _struct_cache_put(cache_key, struct)
        return struct
    except Exception as e:
        _logger.error("All structure-resolution paths failed for %s: %s",
                      filepath, e)
        raise DbandError(
            f"无法从 {filepath} 解析结构，且目录下无可用 CONTCAR/POSCAR。"
            "原子索引无法对齐，结果将无意义。") from e


def parse_vasprun_spin_all(
    filepath: str,
    atoms_str: str,
    orbitals: Optional[List[str]] = None,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], Dict[str, np.ndarray], Dict[str, np.ndarray], float]:
    """Parse vasprun.xml once, returning (energy, rho_up, rho_dn, rho_total, ef).
    Uses lxml.etree.iterparse for high memory efficiency.
    """
    _ensure_pymatgen()
    import core.parsers.common as _cmn
    from lxml import etree as ET
    
    struct = _get_structure_from_vasprun_or_poscar(filepath)
    target_indices = set(_resolve_atom_indices(atoms_str, struct))
    target_orbs = orbitals if orbitals else all_orb_names
    
    context = ET.iterparse(filepath, events=("start", "end"))

    efermi = 0.0
    # Two-pass approach for energies: collect into a list first, then
    # materialise once.  Pre-allocation would require knowing NEDOS up
    # front (parsing <i name="NEDOS">), which adds an extra scan; the
    # list-append path is O(N) and the final np.array() is a single
    # contiguous copy — adequate for DOS-scale arrays (≤ 10^5 points).
    energies: List[float] = []
    
    in_total = False
    in_partial = False
    in_ion = False
    in_spin_1 = False
    in_spin_2 = False
    current_ion = -1
    
    rho_up_raw = {idx: [] for idx in target_indices}
    rho_dn_raw = {idx: [] for idx in target_indices}

    # Collect <field> names exactly once (from the first ion's set).  VASP
    # repeats the <field> block for every ion, so appending on every match
    # would produce N×duplicated names and silently corrupt column mapping.
    fields: List[str] = []
    fields_collected = False
    
    for event, elem in context:
        if event == "start":
            if elem.tag == "total":
                in_total = True
            elif elem.tag == "partial":
                in_partial = True
            elif (in_total or in_partial) and elem.tag == "set":
                comment = elem.attrib.get("comment", "")
                if comment.startswith("ion"):
                    try:
                        current_ion = int(comment.split()[1]) - 1
                    except (IndexError, ValueError):
                        current_ion = -1
                    in_ion = True
                elif comment == "spin 1":
                    in_spin_1 = True
                elif comment == "spin 2":
                    in_spin_2 = True
                    
        elif event == "end":
            if elem.tag == "i" and elem.attrib.get("name") == "efermi":
                try:
                    efermi = float(elem.text.strip())
                except (ValueError, TypeError):
                    pass
            elif in_partial and elem.tag == "field" and not fields_collected:
                if elem.text:
                    fields.append(elem.text.strip())
            elif in_total and in_spin_1 and elem.tag == "r":
                parts = elem.text.split()
                if parts:
                    try:
                        energies.append(float(parts[0]))
                    except ValueError:
                        pass
            elif in_partial and in_ion and in_spin_1 and elem.tag == "r":
                if current_ion in target_indices:
                    parts = elem.text.split()
                    if len(parts) > 1:
                        try:
                            rho_up_raw[current_ion].append([float(x) for x in parts[1:]])
                        except ValueError:
                            pass
            elif in_partial and in_ion and in_spin_2 and elem.tag == "r":
                if current_ion in target_indices:
                    parts = elem.text.split()
                    if len(parts) > 1:
                        try:
                            rho_dn_raw[current_ion].append([float(x) for x in parts[1:]])
                        except ValueError:
                            pass
            elif elem.tag == "set":
                comment = elem.attrib.get("comment", "")
                if comment.startswith("ion"):
                    in_ion = False
                    current_ion = -1
                    # Lock field collection after the first complete ion set.
                    fields_collected = True
                elif comment == "spin 1":
                    in_spin_1 = False
                elif comment == "spin 2":
                    in_spin_2 = False
            elif elem.tag == "total":
                in_total = False
            elif elem.tag == "partial":
                in_partial = False

            # Safe cleanup: clear leaf elements to free memory.  We avoid the
            # ``while el.getprevious(): del parent[0]`` pattern (C6) which can
            # corrupt ancestors still in scope; a plain clear() is sufficient
            # for iterparse memory management on files up to ~200 MB.
            elem.clear()

    energy = np.array(energies)
    rho_up = {o: np.zeros_like(energy) for o in target_orbs}
    rho_dn = {o: np.zeros_like(energy) for o in target_orbs}

    # First field is usually 'energy', skip it. 
    # If somehow 'energy' isn't first, we use the fact that `parts[1:]` corresponds to orbital data.
    # Usually fields = ['energy', 's', 'py', 'pz', 'px', ...]
    orb_fields = fields[1:] if fields and fields[0].lower() == "energy" else fields

    if not orb_fields:
        raise DbandError(
            f"{filepath}: failed to collect <field> names from the "
            "<partial> DOS block.  The vasprun.xml may be truncated, "
            "corrupted, or from an unsupported VASP version.  Without "
            "field names, orbital-to-column mapping is impossible — "
            "results would be meaningless all-zeros.")
    
    raw_arrays = {}
    layouts = set()
    for idx in target_indices:
        if not rho_up_raw[idx]:
            raise DbandError(
                f"{filepath}: selected atom {idx + 1} has no site-projected DOS rows.")
        arr_up = np.asarray(rho_up_raw[idx], dtype=np.float64)
        if arr_up.ndim != 2 or arr_up.shape[0] != len(energy):
            raise DbandError(
                f"{filepath}: selected atom {idx + 1} PDOS length "
                f"({arr_up.shape[0] if arr_up.ndim else 0}) does not match "
                f"the total DOS energy grid ({len(energy)}).")
        if not np.isfinite(arr_up).all():
            raise DbandError(f"{filepath}: selected atom {idx + 1} PDOS contains NaN or Inf.")
        raw_arrays[idx] = arr_up
        layouts.add(_classify_vasprun_partial_layout(arr_up.shape[1], len(orb_fields)))

    if len(layouts) != 1:
        raise DbandError(
            f"{filepath}: selected atoms use inconsistent vasprun.xml PDOS layouts: "
            f"{sorted(layouts)}.")
    layout = layouts.pop()

    if layout == "noncollinear":
        if any(rho_dn_raw[idx] for idx in target_indices):
            raise DbandError(
                f"{filepath}: noncollinear PDOS unexpectedly contains a second "
                "collinear spin set; refusing an ambiguous interpretation.")
        return (energy, *_accumulate_vasprun_noncollinear(
            raw_arrays, list(target_indices), orb_fields, target_orbs), efermi)

    for idx in target_indices:
        arr_up = raw_arrays[idx]
        arr_dn = np.asarray(rho_dn_raw[idx], dtype=np.float64) if rho_dn_raw[idx] else None
        if arr_dn is not None:
            if (arr_dn.ndim != 2 or arr_dn.shape != arr_up.shape or
                    not np.isfinite(arr_dn).all()):
                raise DbandError(
                    f"{filepath}: selected atom {idx + 1} spin-down PDOS does not "
                    "match its spin-up grid or contains NaN/Inf.")

        for i, field_name in enumerate(orb_fields):
            for oname, scale in _field_targets(field_name, target_orbs):
                rho_up[oname] += np.abs(arr_up[:, i]) * scale
                if arr_dn is not None:
                    rho_dn[oname] += np.abs(arr_dn[:, i]) * scale
                        
    rho_up = _ensure_positive(rho_up)
    rho_dn = _ensure_positive(rho_dn)
    rho_total = {o: rho_up[o] + rho_dn[o] for o in target_orbs}
    
    return energy, rho_up, rho_dn, rho_total, efermi


def parse_vasprun(
    filepath: str,
    atoms_str: str,
    spin_mode: str,
    orbitals: Optional[List[str]] = None,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], float]:
    """Parse vasprun.xml -> (energy, rho_dict, ef)."""
    energy, rho_up, rho_dn, rho_total, ef = parse_vasprun_spin_all(
        filepath, atoms_str, orbitals=orbitals)

    if spin_mode == "up":
        return energy, rho_up, ef
    elif spin_mode == "down":
        return energy, rho_dn, ef
    else:
        return energy, rho_total, ef

def get_vasprun_distances(
    filepath: str,
    atoms_str1: str,
    atoms_str2: str,
    cutoff: float,
    mode: str = "all"
) -> List[Tuple[str, str, float]]:
    """Calculate distances between two sets of atoms in a vasprun.xml file.
    
    mode: 'all' (all pairs within cutoff) or 'shortest' (only the absolute shortest pair).
    Returns: List of tuples (atom1_label, atom2_label, distance_in_angstroms).
    """
    _ensure_pymatgen()
    import core.parsers.common as _cmn
    if not _cmn.HAS_PYMATGEN:
        return []
        
    try:
        struct = _get_structure_from_vasprun_or_poscar(filepath)
    except Exception as e:
        _logger.warning("Failed to parse structure for vasprun calculation: %s", e)
        return []
    
    target1 = _cmn._resolve_atom_indices(atoms_str1, struct)
    target2 = _cmn._resolve_atom_indices(atoms_str2, struct)
    
    results = []
    
    def get_symbol(site, idx):
        return f"{_site_symbol(site)} ({idx+1})"
        
    for i in target1:
        site1 = struct[i]
        sym1 = get_symbol(site1, i)
        for j in target2:
            if i == j: 
                continue # don't calculate self distance
            dist = struct.get_distance(i, j)
            if dist <= cutoff:
                site2 = struct[j]
                sym2 = get_symbol(site2, j)
                results.append((sym1, sym2, float(dist)))
                
    if not results:
        return []
        
    results.sort(key=lambda x: x[2])
    
    if mode == "shortest":
        return [results[0]]
        
    return results
