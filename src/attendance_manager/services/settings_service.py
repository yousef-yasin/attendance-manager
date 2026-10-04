from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from attendance_manager.domain.errors import ValidationError
from attendance_manager.domain.statistics import Thresholds
from attendance_manager.i18n import tr

if TYPE_CHECKING:
    from attendance_manager.services.context import AppContext


@dataclass(frozen=True)
class AppSettings:
    instructor_name: str = ""
    at_risk_below: float = 75.0
    warning_below: float = 85.0
    auto_backup: bool = True
    auto_backup_keep: int = 14
    last_course_id: int | None = None

    @property
    def thresholds(self) -> Thresholds:
        return Thresholds(at_risk_below=self.at_risk_below, warning_below=self.warning_below)


class SettingsService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    def load(self) -> AppSettings:
        raw = self.ctx.settings_repo.all()
        defaults = AppSettings()

        def num(key: str, default: float) -> float:
            try:
                return float(raw.get(key, default))
            except ValueError:
                return default

        last = raw.get("last_course_id")
        try:
            return AppSettings(
                instructor_name=raw.get("instructor_name", defaults.instructor_name),
                at_risk_below=num("at_risk_below", defaults.at_risk_below),
                warning_below=num("warning_below", defaults.warning_below),
                auto_backup=raw.get("auto_backup", "1") == "1",
                auto_backup_keep=int(num("auto_backup_keep", defaults.auto_backup_keep)),
                last_course_id=int(last) if last and last.isdigit() else None,
            )
        except ValueError:
            return defaults

    def save(self, settings: AppSettings) -> None:
        try:
            Thresholds(settings.at_risk_below, settings.warning_below)
        except ValueError as exc:
            raise ValidationError(tr("errors.settings.thresholds")) from exc
        if not 1 <= settings.auto_backup_keep <= 365:
            raise ValidationError(tr("errors.settings.keep_range"))
        with self.ctx.db.transaction():
            repo = self.ctx.settings_repo
            repo.set("instructor_name", settings.instructor_name.strip())
            repo.set("at_risk_below", f"{settings.at_risk_below:g}")
            repo.set("warning_below", f"{settings.warning_below:g}")
            repo.set("auto_backup", "1" if settings.auto_backup else "0")
            repo.set("auto_backup_keep", str(settings.auto_backup_keep))
            self.ctx.db.execute(
                "UPDATE instructors SET display_name=? WHERE id=(SELECT MIN(id) FROM instructors)",
                (settings.instructor_name.strip(),),
            )
            self.ctx.audit.log("settings.update", "settings", None)

    def remember_course(self, course_id: int | None) -> None:
        with self.ctx.db.transaction():
            self.ctx.settings_repo.set(
                "last_course_id", "" if course_id is None else str(course_id)
            )

    def get_value(self, key: str, default: str = "") -> str:
        return self.ctx.settings_repo.get(key, default) or default

    def set_value(self, key: str, value: str) -> None:
        with self.ctx.db.transaction():
            self.ctx.settings_repo.set(key, value)
