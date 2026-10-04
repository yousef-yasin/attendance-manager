from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from attendance_manager.importing.importer import load_file
from attendance_manager.paths import AppPaths
from attendance_manager.services.context import AppContext
from attendance_manager.services.course_service import CourseDetails

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic"
REAL = FIXTURES / "real"


def _real_master() -> Path | None:
    for name in ("00.xls", "0.xls"):
        if (REAL / name).exists():
            return REAL / name
    return None


requires_real = pytest.mark.skipif(
    _real_master() is None or not (REAL / "11.xls").exists(),
    reason="Real 00/11/22/33/44 fixtures are not present (tests/fixtures/real is git-ignored).",
)


def _force_remove(func, path, _exc) -> None:  # pragma: no cover - cleanup helper
    os.chmod(path, stat.S_IWRITE)
    func(path)


@pytest.fixture
def data_dir(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "data"
    yield root
    shutil.rmtree(root, onerror=_force_remove)


@pytest.fixture
def ctx(data_dir: Path) -> Iterator[AppContext]:
    context = AppContext(AppPaths(data_dir))
    yield context
    context.close()


@pytest.fixture
def real_master() -> Path:
    path = _real_master()
    if path is None:
        pytest.skip("real master file missing")
    return path


def create_course(ctx: AppContext, master: Path, name: str = "Course", section: str = "1"):
    loaded = load_file(master)
    roster = ctx.courses.roster_preview(loaded, loaded.detection.mapping)
    return ctx.courses.create_course(CourseDetails(name, section, "Summer", "2026"), roster, master)


def add_session(
    ctx: AppContext, course_id: int, path: Path, allow_duplicate: bool = False, title: str = ""
):
    loaded = load_file(path)
    preview = ctx.attendance.build_preview(course_id, loaded, loaded.detection.mapping)
    import datetime as dt

    return ctx.attendance.save_session(
        preview,
        title=title or preview.suggested_title,
        session_date=preview.detected_date or dt.date(2026, 7, 1),
        allow_duplicate=allow_duplicate,
    )
