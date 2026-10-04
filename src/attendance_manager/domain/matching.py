"""Matching an attendance file against the master roster.

The rule is deliberately simple and independent of row order:

* a roster student whose match key appears anywhere in the attendance file is PRESENT;
* every other roster student is ABSENT;
* file rows whose key is not on the roster are reported as *unmatched* (guests,
  the meeting organizer, students from another section, typos) and never
  create students;
* a student appearing several times (re-joined the meeting) counts once.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from attendance_manager.domain.models import AttendanceStatus


@dataclass(frozen=True)
class ParticipantRow:
    """One data row of an uploaded file, already reduced to its match key."""

    row_number: int
    raw_identifier: str
    key: str | None
    name: str
    data: Mapping[str, str] = field(default_factory=dict)


@dataclass
class MatchResult:
    statuses: dict[str, AttendanceStatus]
    #: roster key -> first file row that proved presence
    evidence: dict[str, ParticipantRow]
    unmatched: list[ParticipantRow]
    #: additional rows for a key that was already seen
    repeated: list[ParticipantRow]

    @property
    def present_keys(self) -> list[str]:
        return [k for k, s in self.statuses.items() if s is AttendanceStatus.PRESENT]

    @property
    def absent_keys(self) -> list[str]:
        return [k for k, s in self.statuses.items() if s is AttendanceStatus.ABSENT]

    @property
    def present_count(self) -> int:
        return len(self.present_keys)

    @property
    def absent_count(self) -> int:
        return len(self.absent_keys)

    @property
    def percentage(self) -> float | None:
        total = len(self.statuses)
        return self.present_count / total * 100.0 if total else None

    @property
    def recognized_ratio(self) -> float:
        """Share of identifiable file rows that belong to the roster."""
        identified = len(self.evidence) + len({r.key for r in self.unmatched if r.key is not None})
        return len(self.evidence) / identified if identified else 0.0


def match_attendance(roster_keys: Iterable[str], rows: Sequence[ParticipantRow]) -> MatchResult:
    roster = list(dict.fromkeys(roster_keys))  # keep roster order, drop duplicates
    roster_set = set(roster)
    evidence: dict[str, ParticipantRow] = {}
    unmatched: list[ParticipantRow] = []
    unmatched_seen: set[str] = set()
    repeated: list[ParticipantRow] = []

    for row in rows:
        if row.key is not None and row.key in roster_set:
            if row.key in evidence:
                repeated.append(row)
            else:
                evidence[row.key] = row
            continue
        dedupe_key = row.key or f"#row{row.row_number}"
        if dedupe_key in unmatched_seen:
            repeated.append(row)
            continue
        unmatched_seen.add(dedupe_key)
        unmatched.append(row)

    statuses = {
        key: AttendanceStatus.PRESENT if key in evidence else AttendanceStatus.ABSENT
        for key in roster
    }
    return MatchResult(statuses=statuses, evidence=evidence, unmatched=unmatched, repeated=repeated)
