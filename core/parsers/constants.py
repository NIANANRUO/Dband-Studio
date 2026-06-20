"""Pure-data constants: orbital names and type mappings.

ZERO external dependencies — safe to import at startup without
triggering pymatgen, matplotlib, or any heavy library.
"""

# ---------- Orbital name definitions ----------
s_orb_names = ["s"]
p_orb_names = ["py", "pz", "px"]
d_orb_names = ["dxy", "dyz", "dz2", "dxz", "dx2-y2"]
f_orb_names = ["f-3", "f-2", "f-1", "f0", "f1", "f2", "f3"]
all_orb_names = s_orb_names + p_orb_names + d_orb_names + f_orb_names

# OrbitalType enum -> list of constituent orbital names (for equal distribution)
# Used by vasprun.py when pymatgen provides OrbitalType instead of Orbital keys.
_ORB_TYPE_TO_ORBITALS = {
    "s": ["s"],
    "p": ["py", "pz", "px"],
    "d": ["dxy", "dyz", "dz2", "dxz", "dx2-y2"],
    "f": ["f-3", "f-2", "f-1", "f0", "f1", "f2", "f3"],
}
