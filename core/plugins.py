"""
Plugin system for external parser extensions.

Provides a simple, dependency-free plugin loader that scans a directory
for Python modules, imports them, and calls their ``register()`` function
to register custom parsers with the DataLoader registry.

Usage (automatic, from main.py):
    from core.plugins import PluginLoader
    PluginLoader.load_all()

Plugin protocol:
    Each plugin is a ``.py`` file placed in ``plugins/`` at the project root.
    It must define a ``register(loader)`` function where ``loader`` is the
    ``DataLoader`` class.  The function typically calls::

        loader.register_parser("my_format", my_parser_func)

    The parser function signature must match::
        (filepath: str, atoms: str, spin: str, orbitals: list | None)
        -> (energy: np.ndarray, rho_dict: dict, ef: float)

Example plugin (plugins/castep_parser.py)::

    import numpy as np

    def parse_castep(filepath, atoms, spin, orbitals=None):
        # ... parse the file ...
        return energy, rho_dict, ef

    def register(loader):
        loader.register_parser("CASTEP", parse_castep)
"""
from __future__ import annotations

import importlib.util
import os
import sys
import logging

_logger = logging.getLogger(__name__)

# Default plugin directory: project root / plugins
_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins",
)


class PluginLoader:
    """Discovers and loads parser plugins from the plugins/ directory."""

    LOADED: bool = False
    _loaded_plugins: list[str] = []

    @classmethod
    def load_all(cls, plugin_dir: str | None = None) -> list[str]:
        """Load all plugins from the plugin directory.

        Args:
            plugin_dir: Override the default plugin directory.

        Returns:
            List of successfully loaded plugin module names.
        """
        if cls.LOADED:
            return cls._loaded_plugins

        search_dir = plugin_dir or _PLUGIN_DIR
        if not os.path.isdir(search_dir):
            _logger.debug("Plugin directory does not exist: %s", search_dir)
            cls.LOADED = True
            return []

        # Import DataLoader lazily to avoid circular imports
        from core.loader import DataLoader

        loaded = []
        for filename in sorted(os.listdir(search_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            mod_name = f"_plugin_{filename[:-3]}"
            filepath = os.path.join(search_dir, filename)

            try:
                spec = importlib.util.spec_from_file_location(mod_name, filepath)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = module
                spec.loader.exec_module(module)

                register_fn = getattr(module, "register", None)
                if callable(register_fn):
                    register_fn(DataLoader)
                    loaded.append(filename[:-3])
                    _logger.info("Loaded plugin: %s", filename)
                else:
                    _logger.warning(
                        "Plugin '%s' has no register() function — skipped",
                        filename)
            except Exception as e:
                _logger.error("Failed to load plugin '%s': %s", filename, e)

        cls._loaded_plugins = loaded
        cls.LOADED = True
        return loaded

    @classmethod
    def reset(cls) -> None:
        """Reset state (useful for testing)."""
        cls.LOADED = False
        cls._loaded_plugins = []
