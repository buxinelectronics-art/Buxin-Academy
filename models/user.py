from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from models import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))
    country_code = db.Column(db.String(5), nullable=False)
    city = db.Column(db.String(80))
    role = db.Column(db.String(20), default="student")  # student | admin
    class_type = db.Column(db.String(20))  # group | individual
    experience_level = db.Column(db.String(50))
    learning_goals = db.Column(db.Text)
    profile_picture = db.Column(db.String(500))
    status = db.Column(db.String(20), default="pending")  # pending | active | expired | rejected
    subscription_started_at = db.Column(db.DateTime)
    subscription_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payments = db.relationship("Payment", backref="user", lazy=True)
    notifications = db.relationship("Notification", backref="user", lazy=True)
    posts = db.relationship("CommunityPost", backref="author", lazy=True)
    schedules = db.relationship("StudentSchedule", backref="student", lazy=True)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self, include_sensitive=False):
        from services.subscription_service import is_subscription_active, subscription_day_info

        data = {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "phone": self.phone,
            "country_code": self.country_code,
            "city": self.city,
            "role": self.role,
            "class_type": self.class_type,
            "experience_level": self.experience_level,
            "learning_goals": self.learning_goals,
            "profile_picture": self.profile_picture,
            "status": self.status,
            "subscription_started_at": (
                self.subscription_started_at.isoformat() if self.subscription_started_at else None
            ),
            "subscription_expires_at": (
                self.subscription_expires_at.isoformat() if self.subscription_expires_at else None
            ),
            "subscription_active": is_subscription_active(self),
            **subscription_day_info(self),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        return data
