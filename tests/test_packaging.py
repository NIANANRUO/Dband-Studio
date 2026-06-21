"""Regression checks for runtime dependencies required by advertised features."""

from pathlib import Path


def test_windows_bundle_keeps_scipy_extension_required_by_simpson():
    """The Simpson UI option must not ship without its SciPy binary module."""
    spec = (Path(__file__).parents[1] / "installer" / "dband_studio.spec").read_text(
        encoding="utf-8"
    )

    excludes = spec.split("excludes=[", 1)[1]
    assert "'scipy.special._ufuncs_cxx'" not in excludes
    assert "'scipy.integrate'" in spec
    assert "binaries=SCIPY_BINARIES" in spec
