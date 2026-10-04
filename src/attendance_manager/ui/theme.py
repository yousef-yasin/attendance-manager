"""Design tokens and the application style sheet."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from attendance_manager.domain.models import StudentStanding
from attendance_manager.paths import resource_path

_CHEVRON_DOWN = resource_path("ui/assets/chevron-down.svg").as_posix()
_CHEVRON_UP = resource_path("ui/assets/chevron-up.svg").as_posix()

# Surfaces & ink
BG = "#F4F5F7"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F8F9FB"
SIDEBAR = "#101B2D"
SIDEBAR_HOVER = "#18263D"
SIDEBAR_ACTIVE = "#1E3050"
SIDEBAR_TEXT = "#AEB9CB"
SIDEBAR_TEXT_ACTIVE = "#FFFFFF"
INK = "#111827"
INK_2 = "#4B5563"
MUTED = "#8A8F98"
BORDER = "#E3E6EB"
BORDER_STRONG = "#CDD2DA"
GRID = "#E1E0D9"

# Brand / data
ACCENT = "#2A78D6"
ACCENT_HOVER = "#256ABF"
ACCENT_PRESSED = "#1C5CAB"
ACCENT_SOFT = "#E8F1FC"

# Status palette (reserved; always paired with a label)
GOOD = "#0CA30C"
GOOD_TEXT = "#0A7A0A"
GOOD_SOFT = "#E3F5E3"
WARNING = "#FAB219"
WARNING_TEXT = "#8A5A00"
WARNING_SOFT = "#FFF4D9"
SERIOUS = "#EC835A"
CRITICAL = "#D03B3B"
CRITICAL_TEXT = "#B42323"
CRITICAL_SOFT = "#FCE6E6"
NEUTRAL_SOFT = "#EEF0F3"

STANDING_COLORS: dict[StudentStanding, tuple[str, str]] = {
    # standing: (dot, soft background)
    StudentStanding.PERFECT: (GOOD, GOOD_SOFT),
    StudentStanding.GOOD: (ACCENT, ACCENT_SOFT),
    StudentStanding.WARNING: (WARNING, WARNING_SOFT),
    StudentStanding.AT_RISK: (CRITICAL, CRITICAL_SOFT),
    StudentStanding.NO_SESSIONS: (MUTED, NEUTRAL_SOFT),
}

FONT_FAMILY = "Segoe UI"


def base_font(point_size: float = 9.5) -> QFont:
    font = QFont(FONT_FAMILY)
    font.setPointSizeF(point_size)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    families = set(QFontDatabase.families())
    global FONT_FAMILY
    for candidate in ("Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "Arial"):
        if candidate in families:
            FONT_FAMILY = candidate
            break
    app.setFont(base_font())

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_ALT))
    palette.setColor(QPalette.ColorRole.Text, QColor(INK))
    palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_SOFT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(INK))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(INK))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
    palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(MUTED))
    app.setPalette(palette)
    app.setStyleSheet(STYLE_SHEET)


STYLE_SHEET = f"""
QWidget {{ color: {INK}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {INK}; color: white; border: none; padding: 6px 8px; border-radius: 6px; }}

/* ---------- sidebar ---------- */
#Sidebar {{ background: {SIDEBAR}; }}
#Sidebar QLabel {{ color: {SIDEBAR_TEXT}; }}
#AppTitle {{ color: white; font-size: 15px; font-weight: 600; }}
#AppSubtitle {{ color: {SIDEBAR_TEXT}; font-size: 11px; }}
#NavButton {{
    text-align: left; padding: 9px 14px; border: none; border-radius: 8px;
    color: {SIDEBAR_TEXT}; background: transparent; font-size: 13px;
}}
#NavButton:hover {{ background: {SIDEBAR_HOVER}; color: white; }}
#NavButton:checked {{ background: {SIDEBAR_ACTIVE}; color: {SIDEBAR_TEXT_ACTIVE}; font-weight: 600; }}
#NavButton:focus {{ outline: none; border: 1px solid #3B5A86; }}
#SidebarFooter {{ color: {SIDEBAR_TEXT}; font-size: 11px; }}

/* ---------- header ---------- */
#TopBar {{ background: {BG}; }}
#PageTitle {{ font-size: 22px; font-weight: 600; color: {INK}; }}
#PageSubtitle {{ font-size: 12.5px; color: {INK_2}; }}

/* ---------- cards ---------- */
#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
#Card[selected="true"] {{ border: 2px solid {ACCENT}; }}
#CardTitle {{ font-size: 14px; font-weight: 600; color: {INK}; }}
#CardSubtitle {{ font-size: 12px; color: {INK_2}; }}
#StatLabel {{ font-size: 12px; color: {INK_2}; }}
#StatValue {{ font-size: 26px; font-weight: 600; color: {INK}; }}
#StatValueSmall {{ font-size: 18px; font-weight: 600; color: {INK}; }}
#StatHint {{ font-size: 11.5px; color: {MUTED}; }}
#Muted {{ color: {MUTED}; }}
#Secondary {{ color: {INK_2}; }}
#SectionTitle {{ font-size: 15px; font-weight: 600; }}
#EmptyTitle {{ font-size: 18px; font-weight: 600; }}
#EmptyText {{ font-size: 13px; color: {INK_2}; }}
#StepLabel {{ color: {MUTED}; font-size: 12px; }}
#StepLabel[active="true"] {{ color: {ACCENT}; font-weight: 600; }}
#FieldLabel {{ color: {INK_2}; font-weight: 600; font-size: 12px; }}
#InfoKey {{ color: {INK_2}; font-size: 12px; }}
#InfoValue {{ color: {INK}; font-size: 13px; }}

/* ---------- buttons ---------- */
QPushButton {{
    background: {SURFACE}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
    padding: 7px 14px; font-size: 13px; color: {INK}; min-height: 20px;
}}
QPushButton:hover {{ background: {SURFACE_ALT}; border-color: #B8BFCA; }}
QPushButton:pressed {{ background: {NEUTRAL_SOFT}; }}
QPushButton:focus {{ border: 1px solid {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; background: {SURFACE_ALT}; border-color: {BORDER}; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: white; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton[kind="primary"]:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton[kind="primary"]:focus {{ border: 2px solid #9EC5F4; }}
QPushButton[kind="primary"]:disabled {{ background: #A9C8EE; border-color: #A9C8EE; color: #F4F8FD; }}
QPushButton[kind="danger"] {{ background: {CRITICAL}; border: 1px solid {CRITICAL}; color: white; font-weight: 600; }}
QPushButton[kind="danger"]:hover {{ background: #B93232; }}
QPushButton[kind="danger"]:disabled {{ background: #E9AAAA; border-color: #E9AAAA; }}
QPushButton[kind="ghost"] {{ background: transparent; border: none; color: {ACCENT}; padding: 6px 8px; }}
QPushButton[kind="ghost"]:hover {{ background: {ACCENT_SOFT}; }}
QPushButton[kind="subtle"] {{ background: transparent; border: 1px solid transparent; padding: 6px 8px; }}
QPushButton[kind="subtle"]:hover {{ background: {NEUTRAL_SOFT}; }}
QPushButton::menu-indicator {{ width: 0; }}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit, QTextEdit {{
    background: {SURFACE}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
    padding: 6px 10px; font-size: 13px; selection-background-color: {ACCENT}; selection-color: white;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus,
QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit[invalid="true"] {{ border: 1px solid {CRITICAL}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({_CHEVRON_DOWN}); width: 12px; height: 12px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 24px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; margin-top: 3px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; margin-bottom: 3px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({_CHEVRON_UP}); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({_CHEVRON_DOWN}); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_SOFT};
    selection-color: {INK}; padding: 4px; outline: none;
}}
#CourseSelector {{ min-width: 260px; font-weight: 600; }}
QCheckBox {{ spacing: 8px; font-size: 13px; }}

/* ---------- tables ---------- */
QTableView {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;
    gridline-color: transparent; selection-background-color: {ACCENT_SOFT}; selection-color: {INK};
    alternate-background-color: {SURFACE_ALT}; font-size: 13px; outline: none;
}}
QTableView::item {{ padding: 0 8px; border-bottom: 1px solid #EEF0F3; }}
QTableView::item:selected {{ background: {ACCENT_SOFT}; color: {INK}; }}
QHeaderView::section {{
    background: {SURFACE}; color: {INK_2}; font-weight: 600; font-size: 12px;
    border: none; border-bottom: 1px solid {BORDER}; padding: 8px 8px;
}}
QHeaderView::section:hover {{ color: {INK}; }}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

/* ---------- tabs ---------- */
QTabWidget::pane {{ border: none; top: -1px; }}
QTabBar::tab {{
    background: transparent; padding: 8px 14px; margin-right: 4px; color: {INK_2};
    border: none; border-bottom: 2px solid transparent; font-size: 13px;
}}
QTabBar::tab:selected {{ color: {INK}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {INK}; }}

/* ---------- scroll ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C9CED6; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #AEB5C0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #C9CED6; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- menus ---------- */
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px 7px 12px; border-radius: 6px; font-size: 13px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {INK}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QMenu::icon {{ padding-left: 8px; }}

/* ---------- banners ---------- */
#Banner {{ border-radius: 10px; }}
#Banner[severity="danger"] {{ background: {CRITICAL_SOFT}; border: 1px solid #F2B8B8; }}
#Banner[severity="warning"] {{ background: {WARNING_SOFT}; border: 1px solid #F4D9A0; }}
#Banner[severity="info"] {{ background: {ACCENT_SOFT}; border: 1px solid #C6DCF6; }}
#Banner[severity="success"] {{ background: {GOOD_SOFT}; border: 1px solid #B9E3B9; }}
#Banner QLabel {{ font-size: 12.5px; }}

/* ---------- drop zone ---------- */
#DropZone {{ background: {SURFACE}; border: 2px dashed {BORDER_STRONG}; border-radius: 14px; }}
#DropZone[hover="true"] {{ border-color: {ACCENT}; background: {ACCENT_SOFT}; }}
#DropTitle {{ font-size: 15px; font-weight: 600; }}

QMessageBox QLabel {{ font-size: 13px; }}
"""
