"""Persistent and predictable locations for image exports."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from PySide6.QtCore import QSettings, QStandardPaths


_ORGANIZATION = "DBandStudio"
_APPLICATION = "DBandStudio"
_LAST_EXPORT_DIR_KEY = "export/last_directory"


def _settings() -> QSettings:
    return QSettings(_ORGANIZATION, _APPLICATION)


def default_export_directory(
    file_entries: Iterable[Mapping[str, str]] = (),
    stored_directory: str = "",
    documents_directory: str | None = None,
) -> Path:
    """Choose the last folder, a shared source folder, or Documents."""
    if stored_directory:
        return Path(stored_directory).expanduser()

    source_parents = {
        Path(entry["path"]).expanduser().resolve().parent
        for entry in file_entries
        if entry.get("path")
    }
    if len(source_parents) == 1:
        return source_parents.pop() / "DBandStudio_Export"

    documents = documents_directory or QStandardPaths.writableLocation(
        QStandardPaths.DocumentsLocation)
    return Path(documents) / "DBand Studio" / "Exports"


def get_export_directory(file_entries=()) -> Path:
    stored = str(_settings().value(_LAST_EXPORT_DIR_KEY, "") or "")
    return default_export_directory(file_entries, stored_directory=stored)


def ensure_export_directory(file_entries=()) -> Path:
    """Create and return the preferred folder used by a save-file dialog."""
    directory = get_export_directory(file_entries)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def remember_export_directory(path: str | Path) -> None:
    """Persist an export directory for the next save or batch operation."""
    directory = Path(path)
    settings = _settings()
    settings.setValue(_LAST_EXPORT_DIR_KEY, str(directory.resolve()))
    settings.sync()
