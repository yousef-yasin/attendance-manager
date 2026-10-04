import datetime as dt
import json
import zipfile

import pytest

from attendance_manager.domain.errors import BackupError
from attendance_manager.services.settings_service import AppSettings

from .conftest import SYNTHETIC, add_session, create_course


def test_backup_and_restore_roundtrip(ctx, tmp_path):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    add_session(ctx, course.id, SYNTHETIC / "11.xls")
    backup = ctx.backups.create_backup(tmp_path / "b.zip")
    info = ctx.backups.validate_backup(backup)
    assert (info.courses, info.sessions) == (1, 1)

    # change data after the backup
    add_session(ctx, course.id, SYNTHETIC / "22.xls")
    create_course(ctx, SYNTHETIC / "00.xls", "Other", "9")
    assert len(ctx.courses.list_courses()) == 2

    safety = ctx.backups.restore_backup(backup)
    assert safety.exists()
    courses = ctx.courses.list_courses()
    assert [c.name for c in courses] == ["Course"]
    assert len(ctx.attendance.sessions(courses[0].id)) == 1
    stats = ctx.statistics.course_statistics(courses[0].id).dashboard
    assert (stats.total_present, stats.total_absent) == (8, 4)
    # original files are available after restore
    session = ctx.attendance.sessions(courses[0].id)[0]
    assert ctx.attendance.verify_original(session.id)

    # the safety backup can undo the restore
    ctx.backups.restore_backup(safety)
    assert len(ctx.courses.list_courses()) == 2


def test_restore_into_fresh_installation(ctx, tmp_path, data_dir):
    from attendance_manager.paths import AppPaths
    from attendance_manager.services.context import AppContext

    course = create_course(ctx, SYNTHETIC / "00.xls")
    add_session(ctx, course.id, SYNTHETIC / "11.xls")
    backup = ctx.backups.create_backup(tmp_path / "b.zip")
    other = AppContext(AppPaths(tmp_path / "fresh"))
    try:
        other.backups.restore_backup(backup)
        restored = other.courses.list_courses()
        assert len(restored) == 1
        sid = other.attendance.sessions(restored[0].id)[0].id
        assert other.attendance.verify_original(sid)
    finally:
        other.close()


def test_rejects_non_backup_zip(ctx, tmp_path):
    path = tmp_path / "x.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("hello.txt", "hi")
    with pytest.raises(BackupError, match="not an Attendance Manager backup"):
        ctx.backups.validate_backup(path)


def test_rejects_tampered_database(ctx, tmp_path):
    create_course(ctx, SYNTHETIC / "00.xls")
    good = ctx.backups.create_backup(tmp_path / "good.zip")
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(good) as src, zipfile.ZipFile(bad, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "attendance.db":
                data = data[:-10] + b"0123456789"
            dst.writestr(item, data)
    with pytest.raises(BackupError, match="checksum"):
        ctx.backups.restore_backup(bad)
    assert len(ctx.courses.list_courses()) == 1  # current data untouched


def test_rejects_path_traversal(ctx, tmp_path):
    good = ctx.backups.create_backup(tmp_path / "good.zip")
    bad = tmp_path / "evil.zip"
    with zipfile.ZipFile(good) as src, zipfile.ZipFile(bad, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        dst.writestr("../../evil.txt", "x")
    with pytest.raises(BackupError, match="unsafe"):
        ctx.backups.validate_backup(bad)


def test_rejects_newer_schema(ctx, tmp_path):
    good = ctx.backups.create_backup(tmp_path / "good.zip")
    newer = tmp_path / "newer.zip"
    with zipfile.ZipFile(good) as src, zipfile.ZipFile(newer, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "manifest.json":
                manifest = json.loads(data)
                manifest["schema_version"] = 999
                data = json.dumps(manifest).encode()
            dst.writestr(item, data)
    with pytest.raises(BackupError, match="newer version"):
        ctx.backups.validate_backup(newer)


def test_automatic_backups_and_pruning(ctx):
    assert ctx.backups.auto_backup_if_due() is None  # nothing to back up yet
    create_course(ctx, SYNTHETIC / "00.xls")
    first = ctx.backups.auto_backup_if_due()
    assert first is not None
    assert ctx.backups.auto_backup_if_due() is None  # not due again the same day
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)
    assert ctx.backups.auto_backup_if_due(now=later) is not None
    ctx.settings.save(AppSettings(auto_backup=True, auto_backup_keep=1))
    removed = ctx.backups.prune_automatic(1)
    assert removed == 1
    assert len([b for b in ctx.backups.list_backups() if b.is_automatic]) == 1


def test_backup_disabled(ctx):
    create_course(ctx, SYNTHETIC / "00.xls")
    ctx.settings.save(AppSettings(auto_backup=False))
    assert ctx.backups.auto_backup_if_due() is None
