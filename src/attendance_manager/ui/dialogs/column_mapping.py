"""Manual column mapping when automatic detection is uncertain."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QSpinBox,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from attendance_manager.domain.ids import clean_cell_text, looks_like_student_id
from attendance_manager.i18n import tr, trn
from attendance_manager.importing.detection import (
    ColumnMapping,
    DetectionResult,
    column_letter,
    detect_layout,
)
from attendance_manager.importing.reader import WorkbookData
from attendance_manager.ui import theme
from attendance_manager.ui.widgets.common import Banner, button, label

PREVIEW_ROWS = 150


class _BackgroundDelegate(QStyledItemDelegate):
    """The global ``QTableView::item`` style rule suppresses item backgrounds; paint them here."""

    def paint(self, painter, option, index) -> None:
        brush = index.data(Qt.ItemDataRole.BackgroundRole)
        if isinstance(brush, QBrush):
            painter.fillRect(option.rect, brush)
        super().paint(painter, option, index)


class ColumnMappingDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        workbook: WorkbookData,
        detection: DetectionResult,
        purpose: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("columns.window_title"))
        self.resize(980, 640)
        self.workbook = workbook
        self._updating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(label(tr("columns.title"), "SectionTitle"))
        layout.addWidget(
            label(
                tr(f"columns.intro_{purpose}", file=workbook.path.name),
                "Secondary",
                wrap=True,
            )
        )
        for note in detection.notes:
            layout.addWidget(Banner("info", note))

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        self.sheet = QComboBox()
        for sheet in workbook.sheets:
            self.sheet.addItem(
                tr("columns.sheet_item", sheet=sheet.name, rows=trn("plural.rows", sheet.n_rows))
            )
        self.header = QSpinBox()
        self.header.setSpecialValueText(tr("columns.no_header_row"))
        self.first = QSpinBox()
        self.first.setMinimum(1)
        self.id_col = QComboBox()
        self.name_col = QComboBox()
        for col, (text, widget) in enumerate(
            (
                (tr("columns.sheet"), self.sheet),
                (tr("columns.header_row"), self.header),
                (tr("columns.first_row"), self.first),
                (tr("columns.id_column"), self.id_col),
                (tr("columns.name_column"), self.name_col),
            )
        ):
            form.addWidget(label(text, "FieldLabel"), 0, col)
            form.addWidget(widget, 1, col)
            form.setColumnStretch(col, 2 if col in (0, 3, 4) else 1)
        layout.addLayout(form)

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setItemDelegate(_BackgroundDelegate(self.table))
        layout.addWidget(self.table, 1)

        self.status = label("", wrap=True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(button(tr("actions.cancel"), on_click=self.reject))
        self.ok = button(tr("columns.use"), "primary", "check", self.accept)
        buttons.addWidget(self.ok)
        layout.addLayout(buttons)

        self.sheet.currentIndexChanged.connect(self._sheet_changed)
        self.header.valueChanged.connect(self._header_changed)
        self.first.valueChanged.connect(self._refresh)
        self.id_col.currentIndexChanged.connect(self._refresh)
        self.name_col.currentIndexChanged.connect(self._refresh)

        mapping = detection.mapping
        self._apply(mapping if mapping is not None else ColumnMapping(0, None, 0, 0, None))

    # ------------------------------------------------------------------ state
    def _apply(self, mapping: ColumnMapping) -> None:
        self._updating = True
        self.sheet.setCurrentIndex(mapping.sheet_index)
        self._load_sheet(mapping.sheet_index)
        self.header.setValue(0 if mapping.header_row is None else mapping.header_row + 1)
        self.first.setValue(mapping.first_data_row + 1)
        self.id_col.setCurrentIndex(mapping.id_column)
        self.name_col.setCurrentIndex(0 if mapping.name_column is None else mapping.name_column + 1)
        self._updating = False
        self._refresh()

    def _load_sheet(self, index: int) -> None:
        sheet = self.workbook.sheets[index]
        self.header.setMaximum(sheet.n_rows)
        self.first.setMaximum(max(1, sheet.n_rows))
        self.id_col.clear()
        self.name_col.clear()
        self.name_col.addItem(tr("columns.no_name_column"))
        for c in range(sheet.n_cols):
            name = tr("columns.column", letter=column_letter(c))
            self.id_col.addItem(name)
            self.name_col.addItem(name)
        rows = min(sheet.n_rows, PREVIEW_ROWS)
        self.table.clear()
        self.table.setRowCount(rows)
        self.table.setColumnCount(sheet.n_cols)
        self.table.setHorizontalHeaderLabels([column_letter(c) for c in range(sheet.n_cols)])
        self.table.setVerticalHeaderLabels([str(r + 1) for r in range(rows)])
        for r in range(rows):
            for c in range(sheet.n_cols):
                self.table.setItem(r, c, QTableWidgetItem(clean_cell_text(sheet.cell(r, c))))
        self.table.resizeColumnsToContents()
        for c in range(sheet.n_cols):
            self.table.setColumnWidth(c, min(self.table.columnWidth(c) + 12, 260))

    def _sheet_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        sheet_only = WorkbookData(
            self.workbook.path, self.workbook.file_format, [self.workbook.sheets[index]]
        )
        detected = detect_layout(sheet_only).mapping
        if detected is not None:
            detected = ColumnMapping(
                index,
                detected.header_row,
                detected.first_data_row,
                detected.id_column,
                detected.name_column,
            )
        self._apply(detected or ColumnMapping(index, None, 0, 0, None))

    def _header_changed(self, value: int) -> None:
        if self._updating:
            return
        if value > 0 and self.first.value() <= value:
            self.first.setValue(value + 1)
            return
        self._refresh()

    def mapping(self) -> ColumnMapping:
        header = self.header.value()
        return ColumnMapping(
            sheet_index=self.sheet.currentIndex(),
            header_row=header - 1 if header > 0 else None,
            first_data_row=self.first.value() - 1,
            id_column=max(0, self.id_col.currentIndex()),
            name_column=self.name_col.currentIndex() - 1
            if self.name_col.currentIndex() > 0
            else None,
        )

    def _refresh(self) -> None:
        if self._updating:
            return
        m = self.mapping()
        sheet = self.workbook.sheets[m.sheet_index]
        # Show header names in the column pickers.
        for c in range(sheet.n_cols):
            head = clean_cell_text(sheet.cell(m.header_row, c)) if m.header_row is not None else ""
            text = tr("columns.column", letter=column_letter(c)) + (f" — {head}" if head else "")
            self.id_col.setItemText(c, text)
            self.name_col.setItemText(c + 1, text)
        id_bg = QBrush(QColor(theme.ACCENT_SOFT))
        name_bg = QBrush(QColor(theme.GOOD_SOFT))
        plain = QBrush(QColor(theme.SURFACE))
        muted = QBrush(QColor(theme.MUTED))
        ink = QBrush(QColor(theme.INK))
        bold = QFont(self.table.font())
        bold.setBold(True)
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item is None:
                    continue
                before = r < m.first_data_row and r != m.header_row
                item.setBackground(
                    id_bg if c == m.id_column else name_bg if c == m.name_column else plain
                )
                item.setForeground(muted if before else ink)
                item.setFont(bold if r == m.header_row else self.table.font())
        rows = [
            r
            for r in range(m.first_data_row, sheet.n_rows)
            if clean_cell_text(sheet.cell(r, m.id_column))
        ]
        ids = sum(1 for r in rows if looks_like_student_id(sheet.cell(r, m.id_column)))
        if ids == 0:
            self.status.setText(tr("columns.status_none"))
            self.status.setStyleSheet(f"color: {theme.CRITICAL_TEXT}; font-weight: 600;")
        else:
            self.status.setText(tr("columns.status_found", found=ids, total=len(rows)))
            self.status.setStyleSheet(f"color: {theme.GOOD_TEXT}; font-weight: 600;")
        self.ok.setEnabled(ids > 0)
        target = self.table.item(min(m.first_data_row, max(0, self.table.rowCount() - 1)), 0)
        if target is not None:
            self.table.scrollToItem(target, QAbstractItemView.ScrollHint.PositionAtTop)
