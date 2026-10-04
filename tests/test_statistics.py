import datetime as dt

import pytest

from attendance_manager.domain.models import (
    AttendanceSession,
    AttendanceStatus,
    SessionStatus,
    Student,
    StudentStanding,
)
from attendance_manager.domain.statistics import Thresholds, classify, compute_statistics

P, A = AttendanceStatus.PRESENT, AttendanceStatus.ABSENT
NOW = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)


def student(i: int, active: bool = True) -> Student:
    return Student(i, 1, str(i), str(i), f"Student {i}", {}, i, active)


def session(i: int, day: int) -> AttendanceSession:
    return AttendanceSession(
        id=i,
        uuid=str(i),
        course_id=1,
        session_number=i,
        title=f"L{i}",
        session_date=dt.date(2026, 7, day),
        original_filename=f"{i}.xls",
        file_id=i,
        file_sha256="x",
        uploaded_at=NOW,
        present_count=0,
        absent_count=0,
        unmatched_count=0,
        status=SessionStatus.ACTIVE,
        removed_at=None,
        removed_reason="",
    )


def test_cumulative_counts_and_percentages():
    students = [student(1), student(2), student(3), student(4)]
    sessions = [session(1, 1), session(2, 2), session(3, 3), session(4, 4)]
    pattern = {1: "PPPP", 2: "PPPA", 3: "PAAA", 4: "AAAA"}
    records = [
        (s, st, P if pattern[st][s - 1] == "P" else A) for st in pattern for s in range(1, 5)
    ]
    stats = compute_statistics(students, sessions, records, Thresholds(75, 85))
    by_id = {s.student.id: s for s in stats.students}
    assert (by_id[1].present, by_id[1].absent, by_id[1].percentage) == (4, 0, 100.0)
    assert (by_id[2].present, by_id[2].absent, by_id[2].percentage) == (3, 1, 75.0)
    assert by_id[3].percentage == 25.0
    assert by_id[4].percentage == 0.0
    assert by_id[1].standing is StudentStanding.PERFECT
    assert by_id[2].standing is StudentStanding.WARNING
    assert by_id[3].standing is StudentStanding.AT_RISK

    d = stats.dashboard
    assert d.total_students == 4
    assert d.total_sessions == 4
    assert d.total_present == 8
    assert d.total_absent == 8
    assert d.average_percentage == 50.0
    assert [s.student.id for s in d.perfect_students] == [1]
    assert {s.student.id for s in d.students_with_absences} == {2, 3, 4}
    assert d.highest_percentage == 100.0
    assert d.highest_absence_count == 4
    assert [s.student.id for s in d.highest_absence_students] == [4]
    assert [s.student.id for s in d.at_risk_students] == [4, 3]  # lowest first
    assert [(s.present, s.absent) for s in d.trend] == [(3, 1), (2, 2), (2, 2), (1, 3)]
    assert dict(d.distribution) == {
        "Below 50%": 2,
        "50–74%": 0,
        "75–89%": 1,
        "90–99%": 0,
        "100%": 1,
    }
    assert sum(c for _, c in d.distribution) == 4


def test_student_added_later_is_not_penalised():
    students = [student(1), student(2)]
    sessions = [session(1, 1), session(2, 2)]
    records = [(1, 1, P), (2, 1, P), (2, 2, P)]  # student 2 joined for session 2 only
    stats = compute_statistics(students, sessions, records, Thresholds())
    s2 = stats.for_student(2)
    assert s2 is not None and (s2.sessions, s2.present, s2.percentage) == (1, 1, 100.0)


def test_records_of_removed_sessions_are_ignored():
    students = [student(1)]
    records = [(1, 1, P), (2, 1, A)]
    stats = compute_statistics(students, [session(1, 1)], records, Thresholds())
    assert stats.students[0].absent == 0
    assert stats.dashboard.total_sessions == 1


def test_no_sessions():
    stats = compute_statistics([student(1)], [], [], Thresholds())
    assert stats.students[0].standing is StudentStanding.NO_SESSIONS
    assert stats.dashboard.average_percentage is None
    assert stats.dashboard.highest_percentage is None


def test_trend_is_ordered_by_date_then_number():
    sessions = [session(1, 5), session(2, 3), session(3, 4)]
    stats = compute_statistics([student(1)], sessions, [], Thresholds())
    assert [s.session.id for s in stats.sessions] == [2, 3, 1]


def test_inactive_students_excluded_from_totals_but_keep_history():
    students = [student(1), student(2, active=False)]
    records = [(1, 1, P), (1, 2, A)]
    stats = compute_statistics(students, [session(1, 1)], records, Thresholds())
    assert stats.dashboard.total_students == 1
    assert stats.for_student(2).absent == 1


@pytest.mark.parametrize(
    ("pct", "standing"),
    [
        (None, StudentStanding.NO_SESSIONS),
        (100.0, StudentStanding.PERFECT),
        (90.0, StudentStanding.GOOD),
        (85.0, StudentStanding.GOOD),
        (84.9, StudentStanding.WARNING),
        (75.0, StudentStanding.WARNING),
        (74.9, StudentStanding.AT_RISK),
        (0.0, StudentStanding.AT_RISK),
    ],
)
def test_classify(pct, standing):
    assert classify(pct, Thresholds(75, 85)) is standing


def test_invalid_thresholds():
    with pytest.raises(ValueError):
        Thresholds(90, 80)
    with pytest.raises(ValueError):
        Thresholds(-1, 80)
