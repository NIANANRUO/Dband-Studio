"""
Strongly-typed data model for d-band calculation results.

Replaces the previous loose dict (rd["Label"], rd["Center"], ...)
which was prone to key-typo bugs.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class DbandResult:
    """Single result row: one file x one integration range."""

    label: str
    range_name: str
    center: float
    width: float
    filling: float

    # Per-orbital decomposition (keyed by orbital name)
    orb_weights: Dict[str, float] = field(default_factory=dict)   # percentages
    orb_centers: Dict[str, float] = field(default_factory=dict)   # eV
    # ``lm`` exposes the five d orbitals.  ``l`` is LORBIT=10 and only has
    # a physical aggregate d channel; callers must not fabricate components.
    orbital_resolution: str = "lm"
    source_format: str = "unknown"
    vasp_version: str = ""
    spin_mode: str = "unknown"
    field_source: str = "unknown"
    integration_method: str = "trapezoid"
    structure_source: str = "none"
    metadata_source: str = "none"
    saxis_source: str = "not applicable"

    @property
    def is_aggregate_d(self) -> bool:
        """Whether the result is an l-resolved (LORBIT=10) d total."""
        return self.orbital_resolution == "l"
