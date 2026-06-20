"""Immutable provenance describing the physical interpretation of PDOS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple


@dataclass(frozen=True)
class PDOSMetadata:
    """Facts required to prevent a PDOS channel from being mislabelled.

    ``mode='noncollinear'`` means the exposed up/down arrays are projections
    reconstructed along VASP's sigma-3/SAXIS direction, not collinear spin
    channels.  The tuple interface intentionally remains separate so existing
    plugins and UI callers retain backward compatibility.
    """

    mode: Literal["nonspin", "collinear", "noncollinear", "unknown"]
    orbital_resolution: Literal["lm", "l", "unknown"]
    spin_axis: Optional[Tuple[float, float, float]]
    source_format: str

    @property
    def spin_channel_label(self) -> str:
        if self.mode == "noncollinear":
            return "SAXIS-projected spin"
        if self.mode == "collinear":
            return "collinear spin"
        return "total DOS"
