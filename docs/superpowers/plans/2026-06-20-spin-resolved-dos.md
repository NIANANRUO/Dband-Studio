# Spin-resolved DOS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add physically correct non-spin, collinear, noncollinear, SOC, and LORBIT=10 DOS handling without removing existing functionality.

**Architecture:** Keep public loader tuples intact; introduce parser metadata and validated internal PDOS representations. DOSCAR and vasprun parsers classify physical layout before extraction; UI selects compatible displays from metadata.

**Tech Stack:** Python 3.10+, NumPy, lxml, pymatgen, PySide6, pytest.

---

### Task 1: Numerical-input validation and exact windows

**Files:**
- Modify: `core/calculator.py`
- Modify: `tests/test_calculator.py`

- [ ] Write failing tests for mismatched DOS length, NaN, non-monotonic energy, and a custom window whose endpoints lie between grid points.
- [ ] Run `python -m pytest tests/test_calculator.py -q`; confirm the new tests fail because validation/interpolation is absent.
- [ ] Add `validate_energy_and_dos()` and endpoint clipping with `np.interp`; apply it before all moments and orbital metrics.
- [ ] Run `python -m pytest tests/test_calculator.py -q`; expect all tests to pass.
- [ ] Commit: `git commit -am "fix: validate DOS grids and interpolate windows"`.

### Task 2: DOSCAR physical-layout classifier

**Files:**
- Modify: `core/parsers/doscar.py`
- Modify: `core/exceptions.py`
- Modify: `tests/test_parsers.py`

- [ ] Write failing fixtures for scalar non-spin, paired collinear, and four-component noncollinear lm-resolved PDOS blocks; assert mode and column mapping.
- [ ] Run `python -m pytest tests/test_parsers.py -q`; confirm noncollinear classification fails before implementation.
- [ ] Implement explicit layout classification from projected-column count: scalar, paired, four-component; reject unknown layouts with `DbandError`.
- [ ] Run parser tests; expect pass.
- [ ] Commit: `git commit -am "feat: classify DOSCAR spin layouts"`.

### Task 3: Noncollinear/SOC extraction

**Files:**
- Modify: `core/parsers/doscar.py`
- Modify: `core/parsers/vasprun.py`
- Modify: `core/loader.py`
- Modify: `tests/test_parsers.py`

- [ ] Write failing tests that construct `total,m1,m2,m3` PDOS, assert SAXIS-projected spin densities, and reject `abs(m3) > total + tolerance`.
- [ ] Run targeted tests and confirm failure.
- [ ] Add metadata-carrying parse path, SAXIS retrieval from XML/nearby INCAR, projection reconstruction, finite/positivity checks, and total/magnetization preservation.
- [ ] Run targeted parser tests; expect pass.
- [ ] Commit: `git commit -am "feat: parse noncollinear and SOC PDOS"`.

### Task 4: LORBIT=10 aggregate d support

**Files:**
- Modify: `core/parsers/doscar.py`
- Modify: `core/services/calculation_worker.py`
- Modify: `models/results.py`
- Modify: `tests/test_parsers.py`
- Modify: `tests/test_calculator.py`

- [ ] Write failing test showing LORBIT=10 `d` yields a finite d center and no fake m-resolved entries.
- [ ] Run test and confirm failure.
- [ ] Add `d-total` aggregate handling through result creation while retaining LORBIT=11 five-orbital behavior.
- [ ] Run relevant tests; expect pass.
- [ ] Commit: `git commit -am "feat: support LORBIT10 aggregate d DOS"`.

### Task 5: UI, export, and provenance

**Files:**
- Modify: `ui/panels/param_manager.py`
- Modify: `ui/charts/pdos_chart.py`
- Modify: `core/services/exporter.py`
- Modify: `models/results.py`
- Modify: `tests/test_calculator.py`

- [ ] Write tests for provenance fields, removal of the unsupported “matches VASPKIT” label, and exact preservation of existing chart setting defaults.
- [ ] Add a deterministic chart regression fixture for current non-spin and collinear plots. Assert artist labels, line styles, colors, alpha, axes labels, legend settings, center-line style, and export dimensions before introducing new channels.
- [ ] Implement mode/SAXIS labels, compatible channel choices, and CSV metadata fields without removing, renaming, reordering, or changing defaults of existing controls.
- [ ] Route noncollinear/LORBIT=10 data through the existing chart-style and theme code; add only new optional channel entries.
- [ ] Run full `python -m pytest -q`; expect all tests pass.
- [ ] Commit: `git commit -am "feat: expose DOS provenance and spin modes"`.

### Task 6: Real-data regression and packaging

**Files:**
- Modify: `tests/verify_e2e_correctness.py`
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `README.md`

- [ ] Add an optional environment-variable-driven regression for the supplied Mo_N4 DOSCAR; assert documented trapezoid values and no input mutation.
- [ ] Add direct SciPy dependency or make Simpson unavailable at UI construction when absent.
- [ ] Document supported formats, physical definitions, and limitations.
- [ ] Run full tests and the optional real-data verification with the supplied path.
- [ ] Commit: `git commit -am "test: add auditable DOS regression coverage"`.
