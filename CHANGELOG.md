# Changelog

## 1.2.2 - 2026-07-11

- Removed all implicit discovery of neighboring POSCAR, CONTCAR, INCAR,
  vasprun.xml, and VASPKIT spin-partner files.
- Added explicit per-source authorization for structure, metadata, and spin
  partner files.
- Added `Needs input` import state and a visible diagnostic area.
- Added content-based detection for renamed DOSCAR files such as `DOSCAR(3)`.
- Added auxiliary-file fingerprints to calculation and hybridization caches.
- Migrated workspaces to schema 1.1 without restoring implicit file links.
- Added structure, metadata, and SAXIS provenance to CSV results.

## 1.2.1 - 2026-07-10

- Added import-time PDOS capability inspection and actionable diagnostics.
- Added safe VASP 5/6 `vasprun.xml` field recovery for uniquely known layouts.
- Added explicit DOSCAR ambiguity, integrity, structure, atom, and orbital errors.
- Added capability-driven merged/component orbital selection in hybridization.
- Removed missing-orbital zero filling from hybridization analysis.
- Added calculation provenance to result exports and result tooltips.
- Clarified that ordinary VASP PDOS cannot independently select 3d/4d/5d.
- Restored NumPy 2 compatibility in the test suite.

## 1.2.0

Parser reliability milestone incorporated into the 1.2.1 release.

## 1.1.5

Previous beta release.
