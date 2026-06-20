"""
Parsers package — re-exports all public APIs from sub-modules.

IMPORTANT:  Only **constants** (pure data) are imported at package level
to keep startup fast.  Heavy modules (common, vasprun, doscar, vaspkit)
are loaded lazily on first use.

Thread safety:  ``_load_submodules`` is guarded by ``_load_lock`` so that
concurrent QThread workers (e.g. CalculationWorker + HybridizationWorker)
do not race during the initial lazy import.
"""

import threading

from core.parsers.constants import (
    s_orb_names,
    p_orb_names,
    d_orb_names,
    f_orb_names,
    all_orb_names,
)

# Lazy import of heavy modules
_parsers_loaded = False
_load_lock = threading.Lock()


def _load_submodules():
    """Lazily import heavy parsing modules. Called once on first use.

    Thread-safe: uses a lock to prevent concurrent threads from
    triggering duplicate imports or partial attribute assignment.
    """
    global _parsers_loaded
    if _parsers_loaded:
        return
    with _load_lock:
        # Double-check after acquiring the lock — another thread may
        # have completed the load while we were waiting.
        if _parsers_loaded:
            return
        from core.parsers.common import HAS_PYMATGEN, detect_file_type as _detect
        from core.parsers.vasprun import parse_vasprun as _pv, parse_vasprun_spin_all as _pvs
        from core.parsers.doscar import parse_doscar as _pd, parse_doscar_spin_all as _pds
        from core.parsers.vaspkit import parse_vaspkit as _pvk, parse_vaspkit_spin_all as _pvks

        import core.parsers as _p
        _p.HAS_PYMATGEN = HAS_PYMATGEN
        _p.detect_file_type = _detect
        _p.parse_vasprun = _pv
        _p.parse_vasprun_spin_all = _pvs
        _p.parse_doscar = _pd
        _p.parse_doscar_spin_all = _pds
        _p.parse_vaspkit = _pvk
        _p.parse_vaspkit_spin_all = _pvks

        _parsers_loaded = True


# Lazy stubs — auto-load on first call or first attribute access.
# These are replaced by real implementations after _load_submodules().

def _lazy_stub(name):
    """Create a callable stub that triggers lazy loading on first use."""
    def _stub(*args, **kwargs):
        _load_submodules()
        fn = getattr(__import__('core.parsers', fromlist=[name]), name)
        return fn(*args, **kwargs)
    _stub.__name__ = name
    _stub.__qualname__ = name
    return _stub


HAS_PYMATGEN = False              # updated after _load_submodules
detect_file_type = _lazy_stub('detect_file_type')
parse_vasprun = _lazy_stub('parse_vasprun')
parse_vasprun_spin_all = _lazy_stub('parse_vasprun_spin_all')
parse_doscar = _lazy_stub('parse_doscar')
parse_doscar_spin_all = _lazy_stub('parse_doscar_spin_all')
parse_vaspkit = _lazy_stub('parse_vaspkit')
parse_vaspkit_spin_all = _lazy_stub('parse_vaspkit_spin_all')
