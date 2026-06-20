# DBand Studio

A desktop tool for analyzing d-band center, width, filling, and orbital
hybridization from VASP DFT calculations. Designed for catalysis and
materials-science researchers who need fast, reproducible PDOS analysis.

## Features

- **Three data sources**: vasprun.xml, DOSCAR, and VASPKIT-exported PDOS files
- **d-band metrics**: center (first moment), width (standard deviation),
  filling (occupation fraction with Fermi-level linear-interpolation correction)
- **Physical spin modes**: non-spin, collinear spin, and noncollinear/SOC PDOS.
  Noncollinear channels are explicitly reconstructed as projections along
  VASP's `SAXIS`, never presented as ordinary collinear spins.
- **LORBIT-aware d DOS**: `LORBIT=11` preserves five d components; `LORBIT=10`
  reports only the physically available aggregate `d-total` (no fabricated
  m-resolved components).
- **Orbital hybridization**: two-fragment overlap analysis with bond-length statistics
- **Nature-style plots**: matplotlib-based, exportable to PNG/PDF/SVG
- **Plugin system**: drop custom parsers into `plugins/` for automatic registration

## Quick Start

```bash
pip install -e .

# Launch the GUI
d-band-center
# or
python main.py
```

### Requirements

- Python >= 3.10
- pymatgen >= 2024.1, PySide6 >= 6.5, matplotlib >= 3.7, numpy, scipy

See `pyproject.toml` for the full dependency list.

## Usage

1. **Add files** — select vasprun.xml / DOSCAR / VASPKIT PDOS files (drag-drop or browse)
2. **Set atoms** — enter atom selection (e.g. `Mo`, `1-10`, `1,3,5`)
3. **Run analysis** — computes d-band center, width, filling, per-orbital weights
4. **View PDOS** — interactive chart with theme/style/axes configuration
5. **Hybridization** — open the hybridization window for two-fragment analysis

## Scientific Definitions

All metrics follow the Hammer-Norskov d-band framework:

| Metric   | Formula                                              |
|----------|------------------------------------------------------|
| center   | ∫ E·ρ(E)dE / ∫ρ(E)dE                                |
| width    | sqrt(∫(E-center)²·ρ(E)dE / ∫ρ(E)dE)                 |
| filling  | 100 · ∫_{E≤Ef}ρ(E)dE / ∫ρ(E)dE (with bin splitting)|

The `width` is the second-moment standard deviation, **not** FWHM. It may
differ from VASPKIT `--task 11x` width output. Numerical integration methods
are Dband Studio methods; they are not claimed to reproduce a specific VASPKIT
version, whose grid-boundary conventions may differ.

## Architecture

```
main.py              Entry point
core/
  parsers/           vasprun / doscar / vaspkit parsers (lazy-loaded)
  calculator.py      Numerical integration (pure NumPy, no JIT)
  loader.py          DataLoader registry (single entry point)
  services/          QThread workers + exporter (business logic)
models/              AppState + DbandResult dataclasses
ui/                  MainWindow, charts, panels, widgets
utils/               Styling, helpers
tests/               Unit tests + end-to-end verification
```

## Testing

```bash
pytest tests/ -q                          # 41 unit tests
set DBAND_REAL_DOSCAR=D:\\path\\to\\DOSCAR
python tests/verify_e2e_correctness.py    # optional end-to-end on real VASP data
```

## License

MIT — see [LICENSE](LICENSE).
