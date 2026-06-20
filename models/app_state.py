"""
Global application state (data container).
Stores file entries, calculation results, parsed cache, and user preferences.

v4.0 additions:
- MemoryAwareLRUCache: evicts by estimated memory footprint (default 512 MB)
- Workspace serialization: save/restore file list, results, and preferences
"""
from __future__ import annotations

import json
import os
from collections import OrderedDict
from dataclasses import asdict, fields as dc_fields
from typing import Any, Dict, List

import numpy as np

from utils.styling import DEFAULT_D_COLORS
from models.results import DbandResult

# Maximum cache memory in MB (prevents OOM with large systems)
_MAX_CACHE_MEMORY_MB = 512


class MemoryAwareLRUCache(OrderedDict):
    """LRU cache that evicts by estimated memory footprint, not file count.

    Each entry's size is estimated from numpy array nbytes.
    Eviction occurs when total memory exceeds max_memory_bytes.
    """

    def __init__(self, max_memory_mb: int = _MAX_CACHE_MEMORY_MB):
        super().__init__()
        self.max_memory = max_memory_mb * 1024 * 1024  # bytes
        self._current_memory = 0
        self._sizes = {}

    def __setitem__(self, key: str, value: Any) -> None:
        estimated_size = self._estimate_size(value)
        if key in self:
            self._current_memory -= self._sizes[key]
            self.move_to_end(key)
        super().__setitem__(key, value)
        self._sizes[key] = estimated_size
        self._current_memory += estimated_size
        
        while self._current_memory > self.max_memory and len(self) > 1:
            k, _ = self.popitem(last=False)
            self._current_memory -= self._sizes.pop(k, 0)
            if self._current_memory < 0:
                self._current_memory = 0

    def __getitem__(self, key: str) -> Any:
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._current_memory -= self._sizes.pop(key, 0)
        if self._current_memory < 0:
            self._current_memory = 0

    def clear(self) -> None:
        super().clear()
        self._sizes.clear()
        self._current_memory = 0

    def pop(self, key, default=None):
        if key in self:
            val = super().pop(key)
            self._current_memory -= self._sizes.pop(key, 0)
            if self._current_memory < 0:
                self._current_memory = 0
            return val
        return super().pop(key, default)

    @staticmethod
    def _estimate_size(value: Any) -> int:
        """Estimate memory footprint of a cache entry (bytes)."""
        total = 0
        if isinstance(value, dict):
            for v in value.values():
                if isinstance(v, dict):
                    for arr in v.values():
                        if hasattr(arr, 'nbytes'):
                            total += arr.nbytes
                elif hasattr(v, 'nbytes'):
                    total += v.nbytes
                elif isinstance(v, (int, float)):
                    total += 28
                elif isinstance(v, bool):
                    total += 28
                elif isinstance(v, str):
                    total += len(v) * 2 + 50
        elif hasattr(value, 'nbytes'):
            total = value.nbytes
        return total


class AppState:
    """Central data store shared across all UI components."""

    def __init__(self):
        self.file_entries: List[Dict[str, str]] = []       # [{path: str, label: str}]
        self.results_data: List[DbandResult] = []  # DbandResult per result row
        # parsed_cache: {label: {energy, ef, up, down, has_spin}} with memory-aware LRU
        self.parsed_cache: MemoryAwareLRUCache = MemoryAwareLRUCache()
        self.orb_colors: Dict[str, str] = dict(DEFAULT_D_COLORS)
        self.active_theme: str = "Default Material"
        # User calculation parameters (for workspace save/restore)
        self.params: Dict[str, Any] = {}

    def clear_all(self) -> None:
        """Reset all state."""
        self.file_entries.clear()
        self.results_data.clear()
        self.parsed_cache.clear()
        self.params.clear()

    # ── Workspace serialization ──────────────────────────────────────

    # NOTE: This is the *workspace file format* version, semantically
    # distinct from the application release version (see utils.helpers.get_app_version).
    # Bump this only when the JSON schema of save_workspace changes.
    _WORKSPACE_VERSION = "1.0"

    def save_workspace(self, path: str) -> None:
        """Save workspace state to a JSON file.

        Saves: file_entries, results_data, orb_colors, active_theme, params.
        Does NOT save parsed_cache (transient — re-run calculation to rebuild).
        """
        data = {
            "version": self._WORKSPACE_VERSION,
            "file_entries": self.file_entries,
            "results_data": [asdict(r) for r in self.results_data],
            "orb_colors": self.orb_colors,
            "active_theme": self.active_theme,
            "params": self.params,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_workspace(self, path: str) -> None:
        """Load workspace state from a JSON file.

        Restores: file_entries, results_data, orb_colors, active_theme, params.
        parsed_cache is NOT restored — caller should re-run calculation.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        version = data.get("version", "unknown")
        if version != self._WORKSPACE_VERSION:
            import warnings
            warnings.warn(
                f"Workspace version mismatch: file={version}, "
                f"expected={self._WORKSPACE_VERSION}. Attempting to load anyway.")

        self.file_entries = data.get("file_entries", [])
        # Reconstruct DbandResult with forward-compatibility: ignore unknown
        # keys in old workspace files and supply defaults for missing fields,
        # so adding a new field to DbandResult won't break loading old saves.
        valid_keys = {f.name for f in dc_fields(DbandResult)}
        self.results_data = [
            DbandResult(**{k: v for k, v in rd.items() if k in valid_keys})
            for rd in data.get("results_data", [])
        ]
        self.orb_colors = data.get("orb_colors", dict(DEFAULT_D_COLORS))
        self.active_theme = data.get("active_theme", "Default Material")
        self.params = data.get("params", {})
        # parsed_cache stays cleared — user must re-run calculation
        self.parsed_cache.clear()
