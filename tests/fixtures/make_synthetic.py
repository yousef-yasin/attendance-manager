"""Generate synthetic fixtures that mirror the real file formats (no real student data).

    python tests/fixtures/make_synthetic.py

* 00.xls  — master list, sheet "studentsTable": # | Student Id | Student Name | Major | Status | Register Date
* 11.xls  — Microsoft Teams attendance report (summary block, "2. Participants", header row,
            organizer row, a guest, a student who re-joined)
* 22.xls  — Teams report WITHOUT a header row and sorted so the header ended up mid-table
            (exactly like the real 33.xls)
* 33.xlsx — plain table with numeric (float) student IDs and leading/trailing spaces
* 44.csv  — UTF-16 tab-separated Teams export
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import xlwt

OUT = Path(__file__).resolve().parent / "synthetic"
DOMAIN = "uni.example.edu"

STUDENTS = [
    ("202400001", "ADAM SAMI KHALIL", "Computer Science / Bachelor"),
    ("202400002", "BASMA FUAD HADDAD", "Pharmacy / Bachelor"),
    ("202400003", "CARIM NABIL ODEH", "Law / Bachelor"),
    ("202400004", "DANA RAED SALEH", "Accounting / Bachelor"),
    ("202400005", "EMAD TAREQ YOUSEF", "Civil Engineering / Bachelor"),
    ("202400006", "FARAH ZIAD AMER", "Digital Marketing / Bachelor"),
    ("202400007", "GHAITH OMAR NASSER", "Computer Science / Bachelor"),
    ("202400008", "HALA MAHER ISSA", "Special Education / Bachelor"),
    ("202400009", "IYAD KAMAL FARES", "Law / Bachelor"),
    ("202400010", "JANA WALID SABRI", "Pharmacy / Bachelor"),
    ("202400011", "KHALED ADEL MANSOUR", "Accounting / Bachelor"),
    ("202400012", "LAYAN HANI DAJANI", "Data Science and Artificial Intelligence / Bachelor"),
]

# Presence per weekly file (student numbers by index 1..12).
PRESENT_11 = {1, 2, 3, 4, 5, 6, 7, 8}
PRESENT_22 = {1, 2, 3, 5, 6, 7, 9, 10, 11}
PRESENT_33 = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
PRESENT_44 = {1, 3, 5, 7, 9, 11}


def _sid(i: int) -> str:
    return STUDENTS[i - 1][0]


def _teams_rows(present: set[int], day: str) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "Dr. Test Instructor",
            f"{day}, 3:59:24 PM",
            f"{day}, 5:19:07 PM",
            "1h 19m 42s",
            f"instructor@{DOMAIN}",
            f"instructor@{DOMAIN}",
            "Organizer",
        ],
    ]
    for i in sorted(present):
        name = STUDENTS[i - 1][1].title()
        rows.append(
            [
                name,
                f"{day}, 4:03:11 PM",
                f"{day}, 5:05:17 PM",
                "1h 2m 5s",
                f"{_sid(i)}@{DOMAIN}",
                f"{_sid(i)}@{DOMAIN}",
                "Attendee",
            ]
        )
    return rows


def _summary(count: int, day: str) -> list[list[object]]:
    return [
        ["1. Summary"],
        ["Meeting title", "Meeting with Dr. Test Instructor"],
        ["Attended participants", float(count)],
        ["Start time", f"{day}, 3:56:40 PM"],
        ["End time", f"{day}, 5:01:02 PM"],
        ["Meeting duration", "1h 4m 21s"],
        ["Average attendance time", "50m 29s"],
        [],
        ["2. Participants"],
    ]


HEADER = [
    "Name",
    "First Join",
    "Last Leave",
    "In-Meeting Duration",
    "Email",
    "Participant ID (UPN)",
    "Role",
]


def _write_xls(path: Path, sheet_name: str, rows: list[list[object]]) -> None:
    book = xlwt.Workbook()
    sheet = book.add_sheet(sheet_name)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            sheet.write(r, c, value)
    book.save(str(path))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    master = [["#", "Student Id", "Student Name", "Major", "Status", "Register Date"]]
    for n, (sid, name, major) in enumerate(STUDENTS, start=1):
        # Whitespace variations must not matter.
        shown = f" {sid} " if n == 3 else sid
        master.append([str(n), shown, name, major, "Enrolled", f"{n:02d}-07-2026"])
    _write_xls(OUT / "00.xls", "studentsTable", master)

    # 11: header present, organizer, a guest, student 2 re-joined (duplicate row), upper-case e-mail.
    rows = [*_summary(len(PRESENT_11) + 3, "7/18/26"), HEADER, *_teams_rows(PRESENT_11, "7/18/26")]
    rows.append(
        [
            "Guest Visitor",
            "7/18/26, 4:10:00 PM",
            "7/18/26, 4:30:00 PM",
            "20m",
            f"299999999@{DOMAIN}",
            f"299999999@{DOMAIN}",
            "Attendee",
        ]
    )
    rows.append(
        [
            "Basma Fuad Haddad",
            "7/18/26, 4:40:00 PM",
            "7/18/26, 5:00:00 PM",
            "20m",
            f"{_sid(2)}@{DOMAIN.upper()}",
            f"{_sid(2)}@{DOMAIN.upper()}",
            "Attendee",
        ]
    )
    _write_xls(OUT / "11.xls", "1", rows)

    # 22: no header before the data; the header row got sorted into the middle.
    body = _teams_rows(PRESENT_22, "7/19/26")
    body.insert(5, HEADER)
    _write_xls(OUT / "22.xls", "2", _summary(len(PRESENT_22) + 1, "7/19/26") + body)

    # 33: plain xlsx with numeric IDs.
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.append(["Student ID", "Name", "Date"])
    for i in sorted(PRESENT_33, reverse=True):  # row order must not matter
        ws.append([float(_sid(i)), STUDENTS[i - 1][1], "2026-07-25"])
    ws.append([None, None, None])
    ws.append(["Total", None, None])
    wb.save(OUT / "33.xlsx")

    # 44: UTF-16 TSV like Teams "Download attendance list".
    lines = ["\t".join(map(str, r)) for r in _summary(len(PRESENT_44) + 1, "7/26/26")]
    lines.append("\t".join(HEADER))
    lines += ["\t".join(map(str, r)) for r in _teams_rows(PRESENT_44, "7/26/26")]
    (OUT / "44.csv").write_bytes("\r\n".join(lines).encode("utf-16"))
    print(f"Wrote synthetic fixtures to {OUT}")


if __name__ == "__main__":
    main()
