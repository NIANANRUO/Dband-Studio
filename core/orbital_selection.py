"""Resolve UI orbital choices to physically available parser channels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

import numpy as np

from core.exceptions import OrbitalUnavailableError
from core.pdos_metadata import PDOSCapabilities
from core.parsers.constants import p_orb_names, d_orb_names, f_orb_names

_TOTAL_COMPONENTS = {
    "s": ("s",),
    "p": tuple(p_orb_names),
    "d": tuple(d_orb_names),
    "f": tuple(f_orb_names),
}


def non_overlapping_orbitals(selected: Iterable[str]) -> Tuple[str, ...]:
    """Return selected channels without double-counting total components.

    The hybridization detail panels may display a synthesized ``p``/``d``
    total at the same time as its component curves.  Aggregate overlap curves
    and moment calculations must still count that shell only once, so a
    selected total takes precedence over selected children from the same
    shell.
    """
    ordered = tuple(dict.fromkeys(selected))
    suppressed = {
        component
        for total, components in _TOTAL_COMPONENTS.items()
        if total in ordered
        for component in components
        if component != total
    }
    return tuple(orbital for orbital in ordered if orbital not in suppressed)


@dataclass(frozen=True)
class ResolvedOrbitalRequest:
    parser_orbitals: Tuple[str, ...]
    output_components: Dict[str, Tuple[str, ...]]


def resolve_orbital_request(
    requested: Iterable[str], capabilities: PDOSCapabilities,
) -> ResolvedOrbitalRequest:
    available = set(capabilities.available_orbitals)
    parser_orbitals: list[str] = []
    outputs: Dict[str, Tuple[str, ...]] = {}
    for orbital in dict.fromkeys(requested):
        if orbital in available:
            components = (orbital,)
        elif orbital in _TOTAL_COMPONENTS and set(_TOTAL_COMPONENTS[orbital]) <= available:
            components = _TOTAL_COMPONENTS[orbital]
        else:
            raise OrbitalUnavailableError(orbital, capabilities.available_orbitals)
        outputs[orbital] = tuple(components)
        for component in components:
            if component not in parser_orbitals:
                parser_orbitals.append(component)
    return ResolvedOrbitalRequest(tuple(parser_orbitals), outputs)


def materialize_orbital_outputs(
    rho: Dict[str, np.ndarray], request: ResolvedOrbitalRequest,
) -> Dict[str, np.ndarray]:
    """Build requested totals from real component arrays; never zero-fill."""
    result: Dict[str, np.ndarray] = {}
    for output, components in request.output_components.items():
        missing = [name for name in components if name not in rho]
        if missing:
            raise OrbitalUnavailableError(missing[0], tuple(rho))
        arrays = [np.asarray(rho[name]) for name in components]
        result[output] = np.sum(arrays, axis=0) if len(arrays) > 1 else arrays[0]
    return result
