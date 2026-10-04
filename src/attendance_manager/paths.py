"""Filesystem locations for user data.

All user data lives in a per-user application-data directory (``%LOCALAPPDATA%``
on Windows). Nothing is written next to the executable, so the app works from a
read-only ``Program Files`` install. ``ATTENDANCE_MANAGER_DATA_DIR`` overrides the
location (used by tests and for portable setups).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from attendance_manager import APP_ID

DATA_DIR_ENV = "ATTENDANCE_MANAGER_DATA_DIR"


def default_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_ID
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_ID


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "attendance.db"

    @property
    def files_dir(self) -> Path:
        """Content-addressed store of every original uploaded Excel file."""
        return self.root / "files"

    @property
    def backups_dir(self) -> Path:
        return self.root / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def temp_dir(self) -> Path:
        return self.root / "temp"

    def ensure(self) -> AppPaths:
        for directory in (
            self.root,
            self.files_dir,
            self.backups_dir,
            self.logs_dir,
            self.temp_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    @classmethod
    def default(cls) -> AppPaths:
        return cls(default_data_dir())


def resource_path(relative: str) -> Path:
    """Locate a bundled resource both from source and from a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidate = base / "attendance_manager" / relative
    if candidate.exists():
        return candidate
    return Path(__file__).resolve().parent / relative
