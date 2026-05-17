from datetime import datetime

from models import db


class AcademySettings(db.Model):
    """Singleton (id=1) — global class / 30-day period control."""

    __tablename__ = "academy_settings"

    id = db.Column(db.Integer, primary_key=True)
    class_period_started_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "class_period_started": self.class_period_started_at is not None,
            "class_period_started_at": (
                self.class_period_started_at.isoformat()
                if self.class_period_started_at
                else None
            ),
        }
