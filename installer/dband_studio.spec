# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for DBand Studio.
Build: pyinstaller --clean --noconfirm installer/dband_studio.spec
Output: dist/DBandStudio/DBandStudio.exe
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# PyInstaller executes spec files through ``exec`` and does not define
# ``__file__``. ``SPECPATH`` is the supported path supplied by PyInstaller.
# The project root is one directory above installer/.
PROJECT_ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# pymatgen loads reference JSON/YAML resources dynamically (for example
# core/periodic_table.json.gz); hidden imports alone do not include them.
PYMATGEN_DATA = collect_data_files('pymatgen')
# Simpson imports compiled SciPy extensions at runtime in a frozen app.
SCIPY_BINARIES = collect_dynamic_libs('scipy')

a = Analysis(
    [str(PROJECT_ROOT / 'main.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=SCIPY_BINARIES,
    datas=[
        (str(PROJECT_ROOT / 'config' / 'themes.json'), 'config'),
        # Runtime UI resources are resolved relative to the frozen bundle.
        (str(PROJECT_ROOT / 'assets'), 'assets'),
    ] + PYMATGEN_DATA,
    hiddenimports=[
        # pymatgen — lazy-loaded, must be explicit
        'pymatgen',
        'pymatgen.io',
        'pymatgen.io.vasp',
        'pymatgen.io.vasp.inputs',
        'pymatgen.io.vasp.outputs',
        'pymatgen.core',
        'pymatgen.core.structure',
        'pymatgen.core.composition',
        'pymatgen.core.periodic_table',
        'pymatgen.core.lattice',
        'pymatgen.electronic_structure',
        'pymatgen.electronic_structure.core',
        'pymatgen.electronic_structure.dos',
        'pymatgen.electronic_structure.bandstructure',
        'pymatgen.electronic_structure.plotter',
        'pymatgen.analysis',
        'pymatgen.symmetry',
        'pymatgen.symmetry.analyzer',
        # matplotlib — Qt backend
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_qt5agg',
        'matplotlib.backends.qt_compat',
        # numpy — C extensions
        'numpy.core._methods',
        'numpy.lib.format',
        # PySide6 — Qt platform plugin
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        # lxml — used by vasprun.xml parser
        'lxml.etree',
        'lxml._elementpath',
        'scipy.integrate',
        'scipy.special',
        'scipy.special._ufuncs_cxx',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # numba is excluded because calculator.py no longer depends on it
        # (pure NumPy since v4.0). Excluding prevents indirect pulls via
        # scipy/pymatgen from inflating the bundle by ~80 MB.
        'numba',
        'numba.core',
        'IPython',
        'jupyter',
        'jupyter_client',
        'jupyter_core',
        'notebook',
        'ipykernel',
        'pandas',
        'plotly',
        'networkx',
        'palettable',
        'pybtex',
    ],
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DBandStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(PROJECT_ROOT / 'assets' / 'icon.png'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DBandStudio',
)
