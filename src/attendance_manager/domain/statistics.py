"""Cumulative attendance statistics.

Everything here is computed from immutable per-session records, so results are
always reproducible from history. Only ACTIVE sessions are passed in; removed
sessions stay stored but do not count.

A student is only counted for sessions in which they have a record. A student
added to the roster mid-semester is therefore not penalized for lectures that
took place before they enrolled.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from attendance_manager.domain.models import (
    AttendanceSession,
    AttendanceStatus,
    Student,
    StudentStanding,
)


@dataclass(frozen=True)
class Thresholds:
    """Attendance-percentage limits used to label students."""

    at_risk_below: float = 75.0
    warning_below: float = 85.0

    def __post_init__(self) -> None:
        if not 0 <= self.at_risk_below <= 100 or not 0 <= self.warning_below <= 100:
            raise ValueError("Thresholds must be between 0 and 100")
        if self.at_risk_below > self.warning_below:
            raise ValueError("The at-risk limit must not exceed the warning limit")


def attendance_percentage(present: int, total: int) -> float | None:
    return present / total * 100.0 if total > 0 else None


def classify(percentage: float | None, thresholds: Thresholds) -> StudentStanding:
    if percentage is None:
        return StudentStanding.NO_SESSIONS
    if percentage >= 100.0 - 1e-9:
        return StudentStanding.PERFECT
    if percentage < thresholds.at_risk_below:
        return StudentStanding.AT_RISK
    if percentage < thresholds.warning_below:
        return StudentStanding.WARNING
    return StudentStanding.GOOD


@dataclass(frozen=True)
class StudentStats:
    student: Student
    sessions: int
    present: int
    absent: int
    percentage: float | None
    standing: StudentStanding
    #: session id -> status, for sessions in which the student has a record
    history: Mapping[int, AttendanceStatus]


@dataclass(frozen=True)
class SessionStats:
    session: AttendanceSession
    present: int
    absent: int

    @property
    def total(self) -> int:
        return self.present + self.absent

    @property
    def percentage(self) -> float | None:
        return attendance_percentage(self.present, self.total)


DISTRIBUTION_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("Below 50%", 0.0, 50.0),
    ("50–74%", 50.0, 75.0),
    ("75–89%", 75.0, 90.0),
    ("90–99%", 90.0, 100.0),
    ("100%", 100.0, 100.0 + 1e-9),
)


@dataclass(frozen=True)
class DashboardStats:
    total_students: int
    total_sessions: int
    total_present: int
    total_absent: int
    average_percentage: float | None
    perfect_students: list[StudentStats]
    students_with_absences: list[StudentStats]
    highest_percentage: float | None
    highest_attendance_students: list[StudentStats]
    highest_absence_count: int
    highest_absence_students: list[StudentStats]
    at_risk_students: list[StudentStats]
    warning_students: list[StudentStats]
    trend: list[SessionStats]
    distribution: list[tuple[str, int]] = field(default_factory=list)


@dataclass(frozen=True)
class CourseStatistics:
    students: list[StudentStats]
    sessions: list[SessionStats]
    dashboard: DashboardStats

    def for_student(self, student_id: int) -> StudentStats | None:
        return next((s for s in self.students if s.student.id == student_id), None)


def compute_statistics(
    students: Sequence[Student],
    sessions: Sequence[AttendanceSession],
    records: Iterable[tuple[int, int, AttendanceStatus]],
    thresholds: Thresholds,
) -> CourseStatistics:
    """Compute per-student, per-session and course-level statistics.

    ``records`` are ``(session_id, student_id, status)`` triples. Records that
    belong to sessions not in ``sessions`` (e.g. removed ones) are ignored.
    """
    session_ids = {s.id for s in sessions}
    history: dict[int, dict[int, AttendanceStatus]] = {s.id: {} for s in students}
    per_session: dict[int, list[int]] = {sid: [0, 0] for sid in session_ids}
    for session_id, student_id, status in records:
        if session_id not in session_ids:
            continue
        history.setdefault(student_id, {})[session_id] = status
        per_session[session_id][0 if status is AttendanceStatus.PRESENT else 1] += 1

    student_stats: list[StudentStats] = []
    for student in students:
        h = history.get(student.id, {})
        present = sum(1 for s in h.values() if s is AttendanceStatus.PRESENT)
        absent = len(h) - present
        pct = attendance_percentage(present, len(h))
        student_stats.append(
            StudentStats(
                student=student,
                sessions=len(h),
                present=present,
                absent=absent,
                percentage=pct,
                standing=classify(pct, thresholds),
                history=dict(h),
            )
        )

    ordered_sessions = sorted(sessions, key=lambda s: (s.session_date, s.session_number))
    session_stats = [
        SessionStats(session=s, present=per_session[s.id][0], absent=per_session[s.id][1])
        for s in ordered_sessions
    ]
    dashboard = _dashboard(student_stats, session_stats)
    return CourseStatistics(students=student_stats, sessions=session_stats, dashboard=dashboard)


def _dashboard(students: list[StudentStats], sessions: list[SessionStats]) -> DashboardStats:
    active = [s for s in students if s.student.is_active]
    counted = [s for s in active if s.sessions > 0]
    total_present = sum(s.present for s in sessions)
    total_absent = sum(s.absent for s in sessions)

    highest_pct = max((s.percentage for s in counted if s.percentage is not None), default=None)
    highest_students = (
        [s for s in counted if s.percentage is not None and abs(s.percentage - highest_pct) < 1e-9]
        if highest_pct is not None
        else []
    )
    highest_absences = max((s.absent for s in counted), default=0)
    most_absent = [s for s in counted if s.absent == highest_absences] if highest_absences else []

    distribution: list[tuple[str, int]] = []
    for label, low, high in DISTRIBUTION_BUCKETS:
        count = sum(1 for s in counted if s.percentage is not None and low <= s.percentage < high)
        distribution.append((label, count))

    by_pct = sorted(counted, key=lambda s: (s.percentage or 0.0, -s.absent))
    return DashboardStats(
        total_students=len(active),
        total_sessions=len(sessions),
        total_present=total_present,
        total_absent=total_absent,
        average_percentage=attendance_percentage(total_present, total_present + total_absent),
        perfect_students=[s for s in counted if s.standing is StudentStanding.PERFECT],
        students_with_absences=[s for s in counted if s.absent > 0],
        highest_percentage=highest_pct,
        highest_attendance_students=highest_students,
        highest_absence_count=highest_absences,
        highest_absence_students=most_absent,
        at_risk_students=[s for s in by_pct if s.standing is StudentStanding.AT_RISK],
        warning_students=[s for s in by_pct if s.standing is StudentStanding.WARNING],
        trend=sessions,
        distribution=distribution,
    )
