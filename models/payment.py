from datetime import datetime

from models import db


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount_usd = db.Column(db.Float, nullable=False)
    amount_local = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10))
    payment_method = db.Column(db.String(50))
    receipt_url = db.Column(db.String(500))
    status = db.Column(db.String(20), default="pending")  # pending | approved | rejected
    class_type = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount_usd": self.amount_usd,
            "amount_local": self.amount_local,
            "currency": self.currency,
            "payment_method": self.payment_method,
            "receipt_url": self.receipt_url,
            "status": self.status,
            "class_type": self.class_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }
