# Changelog

## 1.3.0 - 2026-09-13

- Added single/multi-system batch hybridization with six explicit pairing modes.
- Added task preview, strict atom/element validation, cancellation, retry and batch export.
- Reuse atom-resolved XML/DOSCAR data for pairs and merged fragments.
- Added independent per-orbital fragment colors, PDOS color import and workspace persistence.
- Preserve component colors when totals are selected; avoid double-counting totals.
- Added Chinese/English UI switching and improved image export options.
- Updated installer dependencies and bundled version metadata.
- Fixed Python 3.10 test TOML loading and LRU cache eviction compatibility.
- Batch inputs currently require vasprun.xml or atom-resolved DOSCAR. Distance-based pairing, batch bond lengths and side-by-side comparison remain future work.


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
