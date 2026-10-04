"""Toast notifications, busy overlay and background workers."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRectF,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from attendance_manager.i18n import is_rtl, paragraph, tr
from attendance_manager.ui import theme
from attendance_manager.ui.icons import pixmap

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ workers
class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object, str)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # delivered to the UI thread
            self.signals.failed.emit(exc, traceback.format_exc())
        else:
            self.signals.done.emit(result)


_live_tasks: set[_Task] = set()


def run_in_background(
    fn: Callable[[], Any],
    on_done: Callable[[Any], None],
    on_error: Callable[[Exception], None],
) -> None:
    """Run ``fn`` on the thread pool; callbacks are invoked on the UI thread.

    ``fn`` must not touch the database (the SQLite connection belongs to the UI thread).
    """
    task = _Task(fn)
    _live_tasks.add(task)

    def finished_ok(result: Any) -> None:
        _live_tasks.discard(task)
        on_done(result)

    def finished_err(exc: Exception, tb: str) -> None:
        _live_tasks.discard(task)
        log.debug("Background task failed:\n%s", tb)
        on_error(exc)

    task.signals.done.connect(finished_ok, Qt.ConnectionType.QueuedConnection)
    task.signals.failed.connect(finished_err, Qt.ConnectionType.QueuedConnection)
    task.setAutoDelete(False)
    QThreadPool.globalInstance().start(task)


# --------------------------------------------------------------- spinner/busy
class Spinner(QWidget):
    def __init__(self, size: int = 36, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start(16)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(3, 3, self.width() - 6, self.height() - 6)
        p.setPen(QPen(QColor(theme.BORDER), 3.5))
        p.drawEllipse(rect)
        pen = QPen(QColor(theme.ACCENT), 3.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, -self._angle * 16, 100 * 16)
        p.end()


class BusyOverlay(QWidget):
    """Dims its parent and shows a spinner with a message."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(244, 245, 247, 215);")
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        self.spinner = Spinner()
        layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        self.message = QLabel("")
        self.message.setStyleSheet(
            f"background: transparent; color: {theme.INK_2}; font-size: 13px;"
        )
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.message)
        layout.addStretch(1)
        parent.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        parent = self.parentWidget()
        if obj is parent and parent is not None and event.type() == QEvent.Type.Resize:
            self.setGeometry(parent.rect())
        return False

    def show_busy(self, message: str) -> None:
        self.message.setText(message)
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.raise_()
        self.show()
        self.spinner.start()

    def hide_busy(self) -> None:
        self.spinner.stop()
        self.hide()


# --------------------------------------------------------------------- toasts
_TOAST_STYLE = {
    "success": ("check", theme.GOOD),
    "error": ("alert-circle", theme.CRITICAL),
    "warning": ("alert", theme.WARNING),
    "info": ("info", theme.ACCENT),
}


class Toast(QFrame):
    closed = Signal()

    def __init__(
        self,
        parent: QWidget,
        kind: str,
        title: str,
        message: str,
        actions: list[tuple[str, Callable[[], None]]] | None,
        timeout_ms: int,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        name, color = _TOAST_STYLE.get(kind, _TOAST_STYLE["info"])
        self.setStyleSheet(
            f"#Toast {{ background: {theme.INK}; border-radius: 10px; {'border-right' if is_rtl() else 'border-left'}: 4px solid {color}; }}"
            "#Toast QLabel { color: white; background: transparent; }"
            "#Toast QPushButton { background: transparent; color: #9EC5F4; border: none; padding: 2px 6px;"
            " font-weight: 600; } #Toast QPushButton:hover { color: white; }"
        )
        self.setFixedWidth(380)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 10, 12)
        row.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(pixmap(name, color, 18))
        row.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        t = QLabel(paragraph(title))
        t.setStyleSheet("font-weight: 600; font-size: 13px;")
        t.setWordWrap(True)
        texts.addWidget(t)
        if message:
            m = QLabel(paragraph(message))
            m.setWordWrap(True)
            m.setStyleSheet("color: #C9D2E0; font-size: 12px;")
            texts.addWidget(m)
        if actions:
            buttons = QHBoxLayout()
            buttons.setSpacing(4)
            for text, callback in actions:
                b = QPushButton(text)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _=False, cb=callback: self._run_action(cb))
                buttons.addWidget(b)
            buttons.addStretch(1)
            texts.addLayout(buttons)
        row.addLayout(texts, 1)
        close = QPushButton("✕")
        close.setFixedWidth(24)
        close.setToolTip(tr("common.dismiss"))
        close.clicked.connect(self.dismiss)
        row.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._timeout = timeout_ms
        self._closing = False

    def _run_action(self, callback: Callable[[], None]) -> None:
        callback()
        self.dismiss()

    def appear(self) -> None:
        self.show()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        if self._timeout > 0:
            self._timer.start(self._timeout)

    def enterEvent(self, event) -> None:
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._timeout > 0 and not self._closing:
            self._timer.start(2500)
        super().leaveEvent(event)

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._anim.stop()
        self._anim.setStartValue(self._opacity.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._finish)
        self._anim.start()

    def _finish(self) -> None:
        self.hide()
        self.closed.emit()
        self.deleteLater()


class ToastManager(QObject):
    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.host = host
        self.toasts: list[Toast] = []
        host.installEventFilter(self)

    def show(
        self,
        kind: str,
        title: str,
        message: str = "",
        actions: list[tuple[str, Callable[[], None]]] | None = None,
        timeout_ms: int = 5000,
    ) -> None:
        toast = Toast(
            self.host,
            kind,
            title,
            message,
            actions,
            timeout_ms if not actions else max(timeout_ms, 9000),
        )
        toast.closed.connect(lambda t=toast: self._remove(t))
        self.toasts.append(toast)
        toast.adjustSize()
        self._position()
        toast.appear()
        toast.raise_()
        while len(self.toasts) > 4:
            self.toasts[0].dismiss()
            self.toasts.pop(0)

    def _remove(self, toast: Toast) -> None:
        if toast in self.toasts:
            self.toasts.remove(toast)
        self._position()

    def _position(self) -> None:
        margin = 20
        y = self.host.height() - margin
        for toast in reversed(self.toasts):
            toast.adjustSize()
            y -= toast.height()
            # Bottom-trailing corner: bottom-left in right-to-left layouts.
            x = margin if is_rtl() else self.host.width() - toast.width() - margin
            toast.move(x, y)
            y -= 10

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.host and event.type() == QEvent.Type.Resize:
            self._position()
        return False
