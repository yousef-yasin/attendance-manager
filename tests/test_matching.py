import random

from attendance_manager.domain.matching import ParticipantRow, match_attendance
from attendance_manager.domain.models import AttendanceStatus


def row(n: int, key: str | None, name: str = "") -> ParticipantRow:
    return ParticipantRow(row_number=n, raw_identifier=key or "", key=key, name=name)


ROSTER = ["1001", "1002", "1003", "1004", "1005"]


def test_present_and_absent_by_id():
    result = match_attendance(ROSTER, [row(1, "1002"), row(2, "1004")])
    assert result.present_keys == ["1002", "1004"]
    assert result.absent_keys == ["1001", "1003", "1005"]
    assert result.statuses["1002"] is AttendanceStatus.PRESENT
    assert result.percentage == 40.0


def test_row_order_does_not_matter():
    rows = [row(i, k) for i, k in enumerate(["1005", "1001", "1003"], start=1)]
    baseline = match_attendance(ROSTER, rows).statuses
    for seed in range(20):
        shuffled = rows[:]
        random.Random(seed).shuffle(shuffled)
        assert match_attendance(ROSTER, shuffled).statuses == baseline
    # roster order does not matter either
    assert match_attendance(list(reversed(ROSTER)), rows).statuses == baseline


def test_duplicates_count_once():
    result = match_attendance(ROSTER, [row(1, "1001"), row(2, "1001"), row(3, "1001")])
    assert result.present_count == 1
    assert len(result.repeated) == 2
    assert result.evidence["1001"].row_number == 1


def test_unmatched_rows_are_reported_not_counted():
    result = match_attendance(
        ROSTER,
        [
            row(1, "1001"),
            row(2, "9999", "Guest"),
            row(3, "j.doe", "Organizer"),
            row(4, None, "No id"),
        ],
    )
    assert result.present_count == 1
    assert [r.key for r in result.unmatched] == ["9999", "j.doe", None]
    assert set(result.statuses) == set(ROSTER)


def test_empty_file_means_everyone_absent():
    result = match_attendance(ROSTER, [])
    assert result.present_count == 0
    assert result.absent_count == 5
    assert result.recognized_ratio == 0.0


def test_recognized_ratio():
    result = match_attendance(ROSTER, [row(1, "1001"), row(2, "9998"), row(3, "9999")])
    assert abs(result.recognized_ratio - 1 / 3) < 1e-9
