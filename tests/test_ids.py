import datetime as dt

import pytest

from attendance_manager.domain.ids import (
    clean_cell_text,
    display_student_id,
    looks_like_student_id,
    normalize_student_id,
)


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("202400123", "202400123"),
        (202400123.0, "202400123"),
        (202400123, "202400123"),
        ("  202400123  ", "202400123"),
        ("202400123.0", "202400123"),
        ("'202400123", "202400123"),
        ("202400123@university.edu", "202400123"),
        ("202400123@UNIVERSITY.EDU", "202400123"),
        (" 202400123@university.edu ", "202400123"),
        (" 202400123​", "202400123"),
        ("2024 00123", "202400123"),
        ("0012345", "12345"),
        ("S123456", "s123456"),
        ("s123456", "s123456"),
        ("2.02400123E8", "202400123"),
        ("j.doe@university.edu", "j.doe"),
        ("", None),
        (None, None),
        ("   ", None),
    ],
)
def test_normalize_student_id(raw, key):
    assert normalize_student_id(raw) == key


def test_numeric_and_text_ids_match():
    assert normalize_student_id(202400001.0) == normalize_student_id(" 202400001 ")
    assert normalize_student_id("00042") == normalize_student_id(42)


def test_display_keeps_case_and_zeros():
    assert display_student_id("0012345") == "0012345"
    assert display_student_id("S123456@uni.edu") == "S123456"
    assert display_student_id(202400123.0) == "202400123"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("202400123", True),
        (202400123.0, True),
        ("202400123@university.edu", True),
        ("S1234567", True),
        ("2021-cs-001", True),
        ("j.doe@university.edu", False),
        ("SARA HADDAD", False),
        ("08-07-2026", False),
        ("1h 3m 50s", False),
        ("57m 24s", False),
        ("7/25/26, 4:02:27 PM", False),
        ("12", False),
        ("45", False),
        (dt.datetime(2026, 7, 1), False),
        ("Student Id", False),
        ("", False),
        (None, False),
    ],
)
def test_looks_like_student_id(value, expected):
    assert looks_like_student_id(value) is expected


def test_clean_cell_text():
    assert clean_cell_text("SARA   HADDAD") == "SARA HADDAD"
    assert clean_cell_text(29.0) == "29"
    assert clean_cell_text(1.5) == "1.5"
    assert clean_cell_text(dt.datetime(2026, 7, 18)) == "2026-07-18"
    assert clean_cell_text(float("nan")) == ""
