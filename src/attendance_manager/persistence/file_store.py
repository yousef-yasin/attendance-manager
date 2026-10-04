"""Content-addressed storage for original uploaded files.

Every uploaded spreadsheet is copied into ``files/<aa>/<sha256><ext>`` exactly as
uploaded, verified by hash after copying and marked read-only. Identical
uploads share one blob; the database keeps one ``stored_files`` row per upload
(with its original file name).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from attendance_manager.domain.errors import ImportFileError


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    relative_path: str
    size_bytes: int


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def store(self, source: Path) -> StoredBlob:
        try:
            digest = sha256_of(source)
        except OSError as exc:
            raise ImportFileError(f"“{source.name}” could not be read.", details=str(exc)) from exc
        suffix = source.suffix.lower() if len(source.suffix) <= 6 else ""
        relative = f"{digest[:2]}/{digest}{suffix}"
        target = self.root / relative
        if not target.exists() or sha256_of(target) != digest:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".part")
            shutil.copyfile(source, temp)
            if sha256_of(temp) != digest:
                temp.unlink(missing_ok=True)
                raise ImportFileError(
                    f"Copying “{source.name}” failed verification. Please try again."
                )
            if target.exists():
                os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
                target.unlink()
            temp.replace(target)
            os.chmod(target, stat.S_IREAD)
        return StoredBlob(sha256=digest, relative_path=relative, size_bytes=target.stat().st_size)

    def path_for(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Invalid stored file path")
        return path

    def exists(self, relative_path: str) -> bool:
        return self.path_for(relative_path).exists()

    def verify(self, relative_path: str, expected_sha256: str) -> bool:
        path = self.path_for(relative_path)
        return path.exists() and sha256_of(path) == expected_sha256

    def export_copy(self, relative_path: str, destination: Path) -> Path:
        """Copy a stored original out (writable) so it can be opened without risk."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path_for(relative_path), destination)
        os.chmod(destination, stat.S_IWRITE | stat.S_IREAD)
        return destination
