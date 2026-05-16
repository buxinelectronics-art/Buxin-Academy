from datetime import datetime

from models import db


class ClassSession(db.Model):
    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    class_type = db.Column(db.String(20))  # group | individual
    meet_link = db.Column(db.String(500))
    zoom_link = db.Column(db.String(500))
    scheduled_at = db.Column(db.DateTime)
    is_live = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "class_type": self.class_type,
            "meet_link": self.meet_link,
            "zoom_link": self.zoom_link,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "is_live": self.is_live,
        }
