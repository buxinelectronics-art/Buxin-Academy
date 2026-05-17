from datetime import datetime

from models import db
from models.academy_settings import AcademySettings


def get_academy_settings() -> AcademySettings:
    row = db.session.get(AcademySettings, 1)
    if not row:
        row = AcademySettings(id=1)
        db.session.add(row)
        db.session.commit()
    return row


def get_class_period_started_at() -> datetime | None:
    return get_academy_settings().class_period_started_at


def is_class_period_started() -> bool:
    return get_class_period_started_at() is not None
