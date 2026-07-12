# Import Troubleshooting

## Missing vasprun.xml fields

Confirm that `LORBIT=10` or `LORBIT=11` was used and that VASP finished writing
the XML. A field-less layout is accepted only when its columns map uniquely to
a common VASP 5/6 layout. Neighboring files are not read automatically.

## Ambiguous DOSCAR

Some column counts can represent either scalar lm-resolved data or
noncollinear l-resolved data. Add the matching `INCAR` or `vasprun.xml` so
`LSORBIT` and `LNONCOLLINEAR` can be verified. Select it explicitly with
**Aux Files > Select Metadata**.

## Element selection unavailable

Without an authorized structure, use one-based numeric atom indices. Select
the matching file with **Aux Files > Select Structure** to enable element names.

## Reporting a problem

Use **Copy Details** in the Data Source panel. Include the copied diagnosis,
application version, VASP version, calculation flags, and the smallest
redistributable reproducer. Do not upload confidential calculations.
