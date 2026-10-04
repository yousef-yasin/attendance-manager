"""Render every page and the main dialogs to PNG files (for docs and visual QA).

Usage:  python scripts/screenshots.py <output-dir> [fixtures-dir]

Uses a throw-away data directory, imports the fixture course (0/00 master +
weekly files) through the real services and grabs each screen. The default
fixtures are the synthetic ones; never publish screenshots made from real files.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "screenshots")
    # Synthetic by default: screenshots are published, and real files contain student data.
    fixtures = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "tests" / "fixtures" / "synthetic"
    out.mkdir(parents=True, exist_ok=True)
    os.environ["ATTENDANCE_MANAGER_DATA_DIR"] = tempfile.mkdtemp(prefix="am-shots-")

    from PySide6.QtWidgets import QApplication

    from attendance_manager.importing.importer import load_file
    from attendance_manager.paths import AppPaths
    from attendance_manager.services.context import AppContext
    from attendance_manager.services.course_service import CourseDetails
    from attendance_manager.ui.dialogs.attendance_dialog import AddAttendanceDialog
    from attendance_manager.ui.dialogs.column_mapping import ColumnMappingDialog
    from attendance_manager.ui.dialogs.course_dialog import CourseDialog
    from attendance_manager.ui.dialogs.detail_dialogs import (
        SessionDetailDialog,
        StudentDetailDialog,
    )
    from attendance_manager.ui.main_window import MainWindow
    from attendance_manager.ui.theme import apply_theme

    app = QApplication(sys.argv)
    apply_theme(app)
    ctx = AppContext(AppPaths.default())

    def shot(widget, name: str, size=(1440, 900)) -> None:
        widget.resize(*size)
        widget.show()
        for _ in range(8):
            app.processEvents()
        widget.grab().save(str(out / f"{name}.png"))
        print("saved", name)

    # Empty-state first.
    window = MainWindow(ctx)
    shot(window, "01-welcome")

    master = next(p for p in (fixtures / "00.xls", fixtures / "0.xls") if p.exists())
    weekly = sorted(p for p in fixtures.glob("*.xls*") if p.stem not in ("0", "00"))
    loaded = load_file(master)
    roster = ctx.courses.roster_preview(loaded, loaded.detection.mapping)
    course = ctx.courses.create_course(
        CourseDetails("Introduction to Artificial Intelligence", "1", "Summer", "2025/2026"),
        roster,
        master,
    )
    for path in weekly[:-1]:
        lf = load_file(path)
        preview = ctx.attendance.build_preview(course.id, lf, lf.detection.mapping)
        ctx.attendance.save_session(
            preview, title=preview.suggested_title, session_date=preview.detected_date
        )
    window.state.select_course(course.id)
    window.state.notify_changed()

    for key in ("dashboard", "courses", "sessions", "students", "reports", "settings", "backup"):
        window.navigate(key)
        shot(window, f"page-{key}")
    window.resize(1000, 700)
    window.navigate("dashboard")
    shot(window, "page-dashboard-narrow", (1000, 700))

    dialog = AddAttendanceDialog(ctx, course.id, window)
    shot(dialog, "dialog-add-attendance-drop", (1040, 760))
    lf = load_file(weekly[-1])
    dialog._build(lf, lf.detection.mapping)
    shot(dialog, "dialog-add-attendance-review", (1040, 760))
    dup = load_file(weekly[0])
    dialog._build(dup, dup.detection.mapping)
    shot(dialog, "dialog-add-attendance-duplicate", (1040, 760))

    stats = ctx.statistics.course_statistics(course.id)
    risky = (
        stats.dashboard.at_risk_students[0]
        if stats.dashboard.at_risk_students
        else stats.students[0]
    )
    shot(StudentDetailDialog(ctx, risky, stats.sessions, window), "dialog-student", (900, 820))
    shot(
        SessionDetailDialog(ctx, stats.sessions[0].session.id, window),
        "dialog-session",
        (1000, 760),
    )
    headerless = next((p for p in weekly if p.stem == "33"), weekly[0])
    lf = load_file(headerless)
    shot(
        ColumnMappingDialog(window, lf.workbook, lf.detection, "with the master list"),
        "dialog-columns",
        (980, 640),
    )
    cd = CourseDialog(ctx, window)
    cd.name.setText("Data Structures")
    cd.section.setText("2")
    shot(cd, "dialog-course-1", (980, 700))
    cd._go(1)
    lf = load_file(master)
    cd._build(lf, lf.detection.mapping)
    shot(cd, "dialog-course-2", (980, 700))
    ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
