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
