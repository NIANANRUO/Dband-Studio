"""Regression checks for runtime dependencies required by advertised features."""

from pathlib import Path
import re
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


def test_windows_bundle_keeps_scipy_extension_required_by_simpson():
    """The Simpson UI option must not ship without its SciPy binary module."""
    spec = (Path(__file__).parents[1] / "installer" / "dband_studio.spec").read_text(
        encoding="utf-8"
    )

    excludes = spec.split("excludes=[", 1)[1]
    assert "'scipy." not in excludes
    assert "'scipy.integrate'" in spec
    assert "binaries=SCIPY_BINARIES" in spec


def test_windows_bundle_excludes_only_unversioned_host_icu():
    """Keep Qt's versioned ICU chain while rejecting an unrelated PATH DLL."""
    spec = (Path(__file__).parents[1] / "installer" / "dband_studio.spec").read_text(
        encoding="utf-8"
    )

    assert "CONFLICTING_HOST_ICU_DLLS" in spec
    conflict_set = re.search(
        r"CONFLICTING_HOST_ICU_DLLS\s*=\s*\{([^}]*)\}", spec
    ).group(1)
    assert "'icuuc.dll'" in conflict_set
    assert "'icudt78.dll'" not in conflict_set
    assert "icudt78.dll" in spec
    assert "a.binaries = [" in spec


def test_runtime_preflight_exercises_simpson_and_vasprun_dependencies():
    """Release validation must load every package needed by the advertised UI."""
    from main import runtime_preflight

    runtime_preflight()


def test_application_and_installer_versions_match():
    """A release must have one traceable version across its user-facing artifacts."""
    root = Path(__file__).parents[1]
    project_version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    setup = (root / "installer" / "setup.iss").read_text(encoding="utf-8")
    installer_version = re.search(r'#define AppVersion\s+"([^"]+)"', setup).group(1)

    assert installer_version == project_version


def test_pyproject_uses_importable_setuptools_backend():
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["build-system"]["build-backend"] == "setuptools.build_meta:__legacy__"


def test_wheel_configuration_includes_gui_entry_module():
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert "main" in config["tool"]["setuptools"]["py-modules"]
