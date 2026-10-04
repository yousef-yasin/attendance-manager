"""End-to-end service tests: create course -> add weekly files -> cumulative results."""

import datetime as dt
import sqlite3

import openpyxl
import pytest

from attendance_manager.domain.errors import ValidationError
from attendance_manager.domain.models import AttendanceStatus, CourseStatus, SessionStatus
from attendance_manager.importing.importer import load_file
from attendance_manager.services.attendance_service import DuplicateSessionError, Severity

from .conftest import REAL, SYNTHETIC, add_session, create_course, requires_real

# Ground truth computed independently from the real files (see README "Verification").
REAL_EXPECTED = {
    "11.xls": (26, 19, 3),
    "22.xls": (28, 17, 1),
    "33.xls": (36, 9, 1),
    "44.xls": (37, 8, 1),
}


@requires_real
def test_real_00_11_22_33_44_workflow(ctx, real_master):
    course = create_course(ctx, real_master, "Introduction to AI")
    assert ctx.courses.counts(course.id) == (45, 0)
    for name, (present, absent, unmatched) in REAL_EXPECTED.items():
        session = add_session(ctx, course.id, REAL / name)
        assert (session.present_count, session.absent_count, session.unmatched_count) == (
            present,
            absent,
            unmatched,
        ), name
    stats = ctx.statistics.course_statistics(course.id)
    d = stats.dashboard
    assert d.total_students == 45
    assert d.total_sessions == 4
    assert d.total_present == 127
    assert d.total_absent == 53
    assert round(d.average_percentage, 2) == 70.56
    assert len(d.perfect_students) == 22
    assert d.highest_absence_count == 4
    never = [s for s in stats.students if s.present == 0]
    assert len(never) == 6 and all(s.absent == 4 for s in never)
    counts = sorted(s.present for s in stats.students)
    assert counts.count(4) == 22 and counts.count(3) == 7 and counts.count(2) == 8
    assert counts.count(1) == 2 and counts.count(0) == 6
    # session dates come from the Teams "Start time"
    assert [str(s.session.session_date) for s in stats.sessions] == [
        "2026-07-18",
        "2026-07-19",
        "2026-07-25",
        "2026-07-26",
    ]


@requires_real
def test_real_guests_are_listed_not_counted(ctx, real_master):
    course = create_course(ctx, real_master)
    session = add_session(ctx, course.id, REAL / "11.xls")
    detail = ctx.attendance.session_detail(session.id)
    # organizer (e-mail user name) + 2 guests with IDs that are not on this course's roster
    keys = [p.student_key for p in detail.unmatched]
    roster = {s.student_number for s in ctx.courses.students(course.id)}
    assert len(keys) == 3 and sum(not k.isdigit() for k in keys) == 1
    assert not roster & set(keys)
    assert len(detail.present) == 26 and len(detail.absent) == 19


def synthetic_course(ctx):
    course = create_course(ctx, SYNTHETIC / "00.xls", "Synthetic")
    for name in ("11.xls", "22.xls", "33.xlsx", "44.csv"):
        add_session(ctx, course.id, SYNTHETIC / name)
    return course


def test_synthetic_cumulative_results(ctx):
    course = synthetic_course(ctx)
    sessions = ctx.attendance.sessions(course.id)
    assert [(s.present_count, s.absent_count, s.unmatched_count) for s in sessions] == [
        (8, 4, 2),
        (9, 3, 1),
        (10, 2, 0),
        (6, 6, 1),
    ] or sorted((s.present_count, s.absent_count) for s in sessions) == [
        (6, 6),
        (8, 4),
        (9, 3),
        (10, 2),
    ]
    stats = ctx.statistics.course_statistics(course.id)
    present = {s.student.student_number: s.present for s in stats.students}
    assert present == {
        "202400001": 4,
        "202400002": 3,
        "202400003": 4,
        "202400004": 2,
        "202400005": 4,
        "202400006": 3,
        "202400007": 4,
        "202400008": 2,
        "202400009": 3,
        "202400010": 2,
        "202400011": 2,
        "202400012": 0,
    }
    d = stats.dashboard
    assert (d.total_present, d.total_absent) == (33, 15)
    assert d.average_percentage == pytest.approx(68.75)
    assert len(d.perfect_students) == 4
    assert [s.student.student_number for s in d.highest_absence_students] == ["202400012"]


def test_duplicate_upload_is_blocked_then_allowed_explicitly(ctx):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    first = add_session(ctx, course.id, SYNTHETIC / "11.xls")
    loaded = load_file(SYNTHETIC / "11.xls")
    preview = ctx.attendance.build_preview(course.id, loaded, loaded.detection.mapping)
    assert preview.duplicate_of is not None and preview.duplicate_of.id == first.id
    assert preview.notices[0].severity is Severity.DANGER
    with pytest.raises(DuplicateSessionError):
        ctx.attendance.save_session(preview, title="again", session_date=dt.date(2026, 7, 18))
    assert len(ctx.attendance.sessions(course.id)) == 1
    second = ctx.attendance.save_session(
        preview, title="again", session_date=dt.date(2026, 7, 18), allow_duplicate=True
    )
    assert second.session_number == 2
    assert len(ctx.attendance.sessions(course.id)) == 2


def test_duplicate_detected_even_when_renamed(ctx, tmp_path):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    add_session(ctx, course.id, SYNTHETIC / "11.xls")
    renamed = tmp_path / "week1-copy.xls"
    renamed.write_bytes((SYNTHETIC / "11.xls").read_bytes())
    loaded = load_file(renamed)
    preview = ctx.attendance.build_preview(course.id, loaded, loaded.detection.mapping)
    assert preview.duplicate_of is not None


def test_uploading_master_as_attendance_warns(ctx):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    loaded = load_file(SYNTHETIC / "00.xls")
    preview = ctx.attendance.build_preview(course.id, loaded, loaded.detection.mapping)
    assert any("master student list" in n.message for n in preview.notices)


def test_wrong_course_file_warns(ctx, tmp_path):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    other = tmp_path / "other.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["Student ID", "Name"])
    for i in range(10):
        wb.active.append([f"30000{i:04d}", f"Other {i}"])
    wb.save(other)
    loaded = load_file(other)
    preview = ctx.attendance.build_preview(course.id, loaded, loaded.detection.mapping)
    assert preview.match.present_count == 0
    assert preview.notices[0].severity is Severity.DANGER


def test_history_is_never_overwritten(ctx):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    s1 = add_session(ctx, course.id, SYNTHETIC / "11.xls")
    before = [(r.student_id, r.status) for r in ctx.session_repo.records(s1.id)]
    add_session(ctx, course.id, SYNTHETIC / "22.xls")
    add_session(ctx, course.id, SYNTHETIC / "33.xlsx")
    after = [(r.student_id, r.status) for r in ctx.session_repo.records(s1.id)]
    assert before == after
    # the database refuses to modify stored attendance
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        ctx.db.execute(
            "UPDATE attendance_records SET status='present' WHERE session_id=?", (s1.id,)
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        ctx.db.execute("UPDATE sessions SET present_count=0 WHERE id=?", (s1.id,))
    # the original file is kept byte-for-byte
    assert ctx.attendance.verify_original(s1.id)
    copy = ctx.attendance.original_file_copy(s1.id)
    assert copy.read_bytes() == (SYNTHETIC / "11.xls").read_bytes()


def test_remove_and_restore_session(ctx):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    s1 = add_session(ctx, course.id, SYNTHETIC / "11.xls")
    add_session(ctx, course.id, SYNTHETIC / "22.xls")
    ctx.attendance.remove_session(s1.id, "uploaded by mistake")
    d = ctx.statistics.course_statistics(course.id).dashboard
    assert d.total_sessions == 1 and d.total_present == 9
    removed = ctx.session_repo.get(s1.id)
    assert (
        removed.status is SessionStatus.REMOVED and removed.removed_reason == "uploaded by mistake"
    )
    assert len(ctx.session_repo.records(s1.id)) == 12  # still stored
    ctx.attendance.restore_session(s1.id)
    assert ctx.statistics.course_statistics(course.id).dashboard.total_sessions == 2


def test_session_numbers_are_never_reused(ctx):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    s1 = add_session(ctx, course.id, SYNTHETIC / "11.xls")
    ctx.attendance.remove_session(s1.id)
    s2 = add_session(ctx, course.id, SYNTHETIC / "22.xls")
    assert (s1.session_number, s2.session_number) == (1, 2)


def test_rename_session_keeps_results(ctx):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    s1 = add_session(ctx, course.id, SYNTHETIC / "11.xls")
    ctx.attendance.update_session_details(s1.id, "Week 1 — intro", dt.date(2026, 7, 17))
    s = ctx.session_repo.get(s1.id)
    assert (s.title, s.session_date, s.present_count) == ("Week 1 — intro", dt.date(2026, 7, 17), 8)


def test_courses_are_isolated(ctx):
    a = create_course(ctx, SYNTHETIC / "00.xls", "A", "1")
    b = create_course(ctx, SYNTHETIC / "00.xls", "B", "2")
    add_session(ctx, a.id, SYNTHETIC / "11.xls")
    assert ctx.statistics.course_statistics(b.id).dashboard.total_sessions == 0
    assert ctx.courses.counts(a.id) == (12, 1)
    assert ctx.courses.counts(b.id) == (12, 0)
    ids_a = {s.id for s in ctx.courses.students(a.id)}
    ids_b = {s.id for s in ctx.courses.students(b.id)}
    assert not ids_a & ids_b


def test_duplicate_course_requires_confirmation(ctx):
    create_course(ctx, SYNTHETIC / "00.xls", "Same", "1")
    with pytest.raises(ValidationError) as err:
        create_course(ctx, SYNTHETIC / "00.xls", "same ", "1")
    assert err.value.details == "duplicate-course"


def test_course_validation(ctx):
    loaded = load_file(SYNTHETIC / "00.xls")
    roster = ctx.courses.roster_preview(loaded, loaded.detection.mapping)
    from attendance_manager.services.course_service import CourseDetails

    with pytest.raises(ValidationError, match="course name"):
        ctx.courses.create_course(CourseDetails("   "), roster, SYNTHETIC / "00.xls")


def test_edit_archive_delete_course(ctx):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    add_session(ctx, course.id, SYNTHETIC / "11.xls")
    from attendance_manager.services.course_service import CourseDetails

    ctx.courses.update_course(course.id, CourseDetails("Renamed", "3", "Fall", "2027"))
    assert ctx.courses.get(course.id).display_name == "Renamed · Section 3 · Fall 2027"
    ctx.courses.set_archived(course.id, True)
    assert ctx.courses.get(course.id).status is CourseStatus.ARCHIVED
    assert ctx.courses.list_courses(include_archived=False) == []
    ctx.courses.set_archived(course.id, False)
    backup = ctx.courses.delete_course(course.id)
    assert backup.exists()
    assert ctx.courses.list_courses() == []
    assert ctx.db.query_one("SELECT COUNT(*) AS n FROM attendance_records")["n"] == 0


def test_roster_update_adds_and_deactivates_without_touching_history(ctx, tmp_path):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    s1 = add_session(ctx, course.id, SYNTHETIC / "11.xls")
    new_master = tmp_path / "master2.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Student Id", "Student Name", "Major"])
    for i in range(1, 12):  # student 12 dropped
        ws.append([f"2024000{i:02d}", f"Student {i}", "CS"])
    ws.append(["202400099", "NEW STUDENT", "CS"])
    wb.save(new_master)
    loaded = load_file(new_master)
    roster = ctx.courses.roster_preview(loaded, loaded.detection.mapping)
    diff = ctx.courses.roster_diff(course.id, roster)
    assert [s.key for s in diff.added] == ["202400099"]
    assert [s.student_number for s in diff.missing] == ["202400012"]
    ctx.courses.update_roster(course.id, roster, new_master, deactivate_missing=True)
    students = {s.student_number: s for s in ctx.courses.students(course.id)}
    assert students["202400099"].is_active and not students["202400012"].is_active
    assert students["202400001"].full_name == "Student 1"
    # history untouched: the dropped student still has the original absence record
    assert len(ctx.session_repo.records(s1.id)) == 12
    s2 = add_session(ctx, course.id, SYNTHETIC / "22.xls")
    assert s2.present_count + s2.absent_count == 12  # 11 kept + 1 new, dropped student excluded
    stats = ctx.statistics.course_statistics(course.id)
    new = next(s for s in stats.students if s.student.student_number == "202400099")
    assert new.sessions == 1  # not penalised for the lecture before enrolment
    assert new.history == {s2.id: AttendanceStatus.ABSENT}


def test_audit_log_records_actions(ctx):
    course = create_course(ctx, SYNTHETIC / "00.xls")
    add_session(ctx, course.id, SYNTHETIC / "11.xls")
    actions = [r["action"] for r in ctx.audit.recent()]
    assert "course.create" in actions and "session.create" in actions
