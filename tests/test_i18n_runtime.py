"""Language persistence across real application restarts.

Each launch runs the real ``attendance_manager.app.main()`` in its own Python
process (as the installed app does), sharing one data folder. A small driver
clicks the header language switch, records what the window shows, and quits.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

DRIVER = textwrap.dedent(
    """
    import json, sys
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from attendance_manager import app
    from attendance_manager.i18n import get_language, strip_bidi
    from attendance_manager.ui.main_window import MainWindow

    result_file, click = sys.argv[1], sys.argv[2]
    original_show = MainWindow.show

    def record(win, out):
        qapp = QApplication.instance()
        out.update(
            language=get_language(),
            app_rtl=qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft,
            window_rtl=win.isRightToLeft(),
            title=win.windowTitle(),
            nav_students=strip_bidi(win.nav_buttons["students"].text()).strip(),
            checked=[c for c, b in win.language_switch.buttons.items() if b.isChecked()],
        )

    def drive(win):
        out = {}
        record(win, out)
        out["at_start"] = dict(out)
        if click != "none":
            # A real mouse click on the header switch; the switch is rebuilt afterwards.
            QTest.mouseClick(win.language_switch.buttons[click], Qt.MouseButton.LeftButton)
            for _ in range(100):
                QApplication.processEvents()
                if get_language() == click:
                    break
                QTest.qWait(20)
            QTest.qWait(50)
            record(win, out)
        with open(result_file, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False)
        win.close()  # last window closed -> app.exec() returns -> ctx.close()

    def show(self):
        original_show(self)
        QTimer.singleShot(300, lambda: drive(self))

    MainWindow.show = show
    sys.exit(app.main(["AttendanceManager"]))
    """
)


def _launch(data_dir: Path, tmp_path: Path, click: str, run: int) -> dict:
    result = tmp_path / f"run{run}.json"
    env = {
        **os.environ,
        "ATTENDANCE_MANAGER_DATA_DIR": str(data_dir),
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONPATH": os.pathsep.join([str(SRC), os.environ.get("PYTHONPATH", "")]),
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.run(
        [sys.executable, "-c", DRIVER, str(result), click],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert result.exists(), proc.stderr[-3000:]
    return json.loads(result.read_text(encoding="utf-8"))


def test_language_and_direction_survive_real_restarts(tmp_path):
    data_dir = tmp_path / "data"

    # 1st launch: fresh install starts in English / LTR; switch to Arabic.
    first = _launch(data_dir, tmp_path, "ar", 1)
    assert first["at_start"]["language"] == "en"
    assert not first["at_start"]["app_rtl"]
    assert first["at_start"]["checked"] == ["en"]
    assert first["language"] == "ar" and first["window_rtl"]
    assert first["checked"] == ["ar"]

    # 2nd launch: comes up directly in Arabic, right-to-left.
    second = _launch(data_dir, tmp_path, "en", 2)
    start = second["at_start"]
    assert start["language"] == "ar"
    assert start["app_rtl"] and start["window_rtl"]
    assert start["title"] == "مدير الحضور"
    assert start["nav_students"] == "الطلاب"
    assert start["checked"] == ["ar"]
    # ... and switching back to English in that process takes effect at once.
    assert second["language"] == "en" and not second["window_rtl"]

    # 3rd launch: English / left-to-right was persisted too.
    third = _launch(data_dir, tmp_path, "none", 3)["at_start"]
    assert third["language"] == "en"
    assert not third["app_rtl"] and not third["window_rtl"]
    assert third["title"] == "Attendance Manager"
    assert third["nav_students"] == "Students"
    assert third["checked"] == ["en"]


def test_unknown_saved_language_falls_back_to_english(tmp_path):
    from attendance_manager.paths import AppPaths
    from attendance_manager.services.context import AppContext
    from attendance_manager.ui.language import SETTING_KEY

    data_dir = tmp_path / "data"
    ctx = AppContext(AppPaths(data_dir))
    try:
        ctx.settings.set_value(SETTING_KEY, "fr")  # e.g. written by a future version
    finally:
        ctx.close()
    start = _launch(data_dir, tmp_path, "none", 1)["at_start"]
    assert start["language"] == "en" and not start["window_rtl"]
