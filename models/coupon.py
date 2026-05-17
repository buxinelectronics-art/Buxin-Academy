from datetime import datetime
import secrets
import string

from models import db


def generate_coupon_code(length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Coupon(db.Model):
    __tablename__ = "coupons"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    class_type = db.Column(db.String(20), nullable=False)  # group | individual
    discount_percent = db.Column(db.Integer, nullable=False)  # 100 = free
    used_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    used_at = db.Column(db.DateTime)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"))
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(200))

    used_by = db.relationship("User", foreign_keys=[used_by_user_id])
    creator = db.relationship("User", foreign_keys=[created_by_admin_id])

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "class_type": self.class_type,
            "discount_percent": self.discount_percent,
            "is_full": self.discount_percent >= 100,
            "is_used": self.is_used,
            "used_by_user_id": self.used_by_user_id,
            "used_by_name": self.used_by.full_name if self.used_by else None,
            "used_at": self.used_at.isoformat() if self.used_at else None,
            "payment_id": self.payment_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "notes": self.notes,
        }
