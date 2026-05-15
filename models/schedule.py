from datetime import datetime

from models import db


class Schedule(db.Model):
    __tablename__ = "schedules"

    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.String(20), nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)
    is_available = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "day_of_week": self.day_of_week,
            "time_slot": self.time_slot,
            "is_available": self.is_available,
            "label": f"{self.day_of_week} {self.time_slot}",
        }


class StudentSchedule(db.Model):
    __tablename__ = "student_schedules"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey("schedules.id"), nullable=False)
    preference_order = db.Column(db.Integer, default=1)
    assigned_at = db.Column(db.DateTime)

    schedule = db.relationship("Schedule", backref="student_selections")

    def to_dict(self):
        return {
            "id": self.id,
            "schedule_id": self.schedule_id,
            "preference_order": self.preference_order,
            "schedule": self.schedule.to_dict() if self.schedule else None,
        }
