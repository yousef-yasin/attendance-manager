"""UI smoke tests (headless): every page and dialog builds and shows real data."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from attendance_manager.importing.importer import load_file
from attendance_manager.ui.dialogs.attendance_dialog import AddAttendanceDialog
from attendance_manager.ui.dialogs.column_mapping import ColumnMappingDialog
from attendance_manager.ui.dialogs.course_dialog import CourseDialog
from attendance_manager.ui.dialogs.detail_dialogs import (
    SessionDetailDialog,
    StudentDetailDialog,
)
from attendance_manager.ui.main_window import NAV, MainWindow
from attendance_manager.ui.theme import apply_theme

from .conftest import SYNTHETIC, add_session, create_course


@pytest.fixture
def window(qtbot, qapp, ctx):
    apply_theme(qapp)
    course = create_course(ctx, SYNTHETIC / "00.xls")
    for name in ("11.xls", "22.xls"):
        add_session(ctx, course.id, SYNTHETIC / name)
    win = MainWindow(ctx)
    qtbot.addWidget(win)
    win.show()
    return win


def test_all_pages_render(window):
    for key, _, _ in NAV:
        window.navigate(key)
        assert window.stack.currentWidget() is window.pages[key]
    assert "45" not in window.pages["dashboard"].c_students.value_label.text()
    assert window.pages["dashboard"].c_students.value_label.text() == "12"
    assert window.pages["dashboard"].c_sessions.value_label.text() == "2"


def test_students_search_and_filter(window):
    page = window.pages["students"]
    window.navigate("students")
    assert page.proxy.rowCount() == 12
    page.search.setText("202400012")
    assert page.proxy.rowCount() == 1
    page.set_filter("perfect")  # stable filter id (labels are translated)
    assert 0 < page.proxy.rowCount() < 12


def test_dialogs_build(window, ctx):
    course_id = window.state.course_id
    dialog = AddAttendanceDialog(ctx, course_id, window)
    loaded = load_file(SYNTHETIC / "33.xlsx")
    dialog._build(loaded, loaded.detection.mapping)
    assert dialog.save.isEnabled()
    dialog.close()

    dup = AddAttendanceDialog(ctx, course_id, window)
    loaded = load_file(SYNTHETIC / "11.xls")
    dup._build(loaded, loaded.detection.mapping)
    assert not dup.save.isEnabled()  # duplicate must be confirmed first
    dup.override.setChecked(True)
    assert dup.save.isEnabled()
    dup.close()

    stats = ctx.statistics.course_statistics(course_id)
    StudentDetailDialog(ctx, stats.students[0], stats.sessions, window).close()
    SessionDetailDialog(ctx, stats.sessions[0].session.id, window).close()
    loaded = load_file(SYNTHETIC / "22.xls")
    mapping = ColumnMappingDialog(window, loaded.workbook, loaded.detection, "test")
    assert mapping.mapping() == loaded.detection.mapping
    mapping.close()
    cd = CourseDialog(ctx, window)
    cd._go(1)  # blocked: no name yet
    assert cd.pages.currentIndex() == 0
    cd.name.setText("New")
    cd._go(1)
    assert cd.pages.currentIndex() == 1
    cd.close()


def test_save_attendance_through_dialog_updates_dashboard(window, ctx):
    dialog = AddAttendanceDialog(ctx, window.state.course_id, window)
    loaded = load_file(SYNTHETIC / "33.xlsx")
    dialog._build(loaded, loaded.detection.mapping)
    dialog._save()
    assert dialog.saved is not None
    window.state.notify_changed()
    window.navigate("dashboard")
    assert window.pages["dashboard"].c_sessions.value_label.text() == "3"
