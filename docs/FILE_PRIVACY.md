# File Access and Privacy

DBand Studio follows an explicit authorization rule: selecting or dropping one
file authorizes only that file. Merely sharing a directory does not authorize
access to any neighboring file.

The application does not automatically discover or read POSCAR, CONTCAR,
INCAR, vasprun.xml, or VASPKIT spin-partner files. When an analysis needs one,
the source is marked **Needs input** and the user selects it through **Aux
Files**. Every authorized auxiliary path is visible, removable, persisted in
the workspace, included in cache identity, and represented in result
provenance.

**Add Folder** is the only directory-scoped operation. The folder selected by
the user is scanned for supported primary data files; this does not authorize
automatic auxiliary-file associations.
