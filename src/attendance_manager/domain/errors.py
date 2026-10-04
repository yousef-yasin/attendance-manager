from __future__ import annotations


class AttendanceError(Exception):
    """Base class for errors that carry a user-facing message."""

    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ImportFileError(AttendanceError):
    """An uploaded file cannot be read or does not contain a usable table."""


class ValidationError(AttendanceError):
    """User input is invalid."""


class NotFoundError(AttendanceError):
    """A requested record does not exist."""


class BackupError(AttendanceError):
    """A backup could not be created or restored."""
