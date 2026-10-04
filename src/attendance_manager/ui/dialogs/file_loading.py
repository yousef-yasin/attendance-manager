from __future__ import annotations

from PySide6.QtWidgets import QDialog, QWidget

from attendance_manager.importing.detection import ColumnMapping
from attendance_manager.importing.importer import LoadedFile
from attendance_manager.ui.dialogs.column_mapping import ColumnMappingDialog


def resolve_mapping(
    parent: QWidget,
    loaded: LoadedFile,
    purpose: str,
    force: bool = False,
    current: ColumnMapping | None = None,
) -> ColumnMapping | None:
    """Use the detected columns, or ask the instructor when detection is uncertain."""
    if not force and not loaded.needs_confirmation:
        return loaded.detection.mapping
    detection = loaded.detection
    if current is not None:
        detection = type(detection)(mapping=current, confidence=detection.confidence, notes=[])
    dialog = ColumnMappingDialog(parent, loaded.workbook, detection, purpose)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.mapping()
