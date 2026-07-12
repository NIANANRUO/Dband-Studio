# VASP PDOS Compatibility

DBand Studio accepts a file only when its projected-DOS columns have one
defensible physical interpretation.

| Source | Supported common layouts | Required companion data |
|---|---|---|
| `vasprun.xml` | VASP 5/6, LORBIT 10/11, non-spin, collinear, noncollinear/SOC | Uses embedded data; an external structure must be explicitly selected |
| `DOSCAR` | VASP 5/6, LORBIT 10/11, non-spin, collinear, noncollinear/SOC | Explicit metadata for ambiguous SOC layouts; explicit structure for element selection |
| VASPKIT PDOS | Header-declared projected orbitals | Explicit structure for element selection and explicit spin partner when required |

## Resolution Contract

- `l`: aggregate `s`, `p`, `d`, and optionally `f` projections.
- `lm`: component projections such as `py`, `dxy`, and `dx2-y2`.
- LORBIT 10 never produces synthetic m-resolved orbitals.
- Ordinary VASP PDOS does not expose independent 3d/4d/5d channels.

Unknown, ragged, truncated, or ambiguous layouts are rejected. DBand Studio
does not guess column meaning.

## File Authorization

Importing a file authorizes only that file. DBand Studio does not inspect or
open neighboring POSCAR, CONTCAR, INCAR, vasprun.xml, or spin-channel files.
Auxiliary files are read only after the user selects them through **Aux Files**.
Selecting **Add Folder** explicitly authorizes scanning that selected folder
for supported primary data files, but does not create auxiliary associations.

## Release Verification

Before publishing, run the automated suite on Python 3.10 through 3.13 and
verify at least one unmodified VASP 5 and one unmodified VASP 6 calculation.
Real files must remain local if redistribution is not permitted.
