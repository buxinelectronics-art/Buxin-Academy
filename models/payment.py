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
    payment_channel = db.Column(db.String(20), default="manual")  # manual | modempay
    modem_transaction_id = db.Column(db.String(120))
    modem_intent_id = db.Column(db.String(120))
    status = db.Column(db.String(20), default="pending")  # pending | approved | rejected
    class_type = db.Column(db.String(20))
    coupon_id = db.Column(db.Integer, db.ForeignKey("coupons.id"))
    discount_percent = db.Column(db.Integer)
    original_amount_usd = db.Column(db.Float)
    original_amount_local = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)

    coupon = db.relationship("Coupon", foreign_keys=[coupon_id])

    def to_dict(self):
        coupon_code = None
        if self.coupon_id and self.coupon:
            coupon_code = self.coupon.code
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount_usd": self.amount_usd,
            "amount_local": self.amount_local,
            "original_amount_usd": self.original_amount_usd,
            "original_amount_local": self.original_amount_local,
            "discount_percent": self.discount_percent,
            "coupon_id": self.coupon_id,
            "coupon_code": coupon_code,
            "currency": self.currency,
            "payment_method": self.payment_method,
            "receipt_url": self.receipt_url,
            "payment_channel": self.payment_channel or "manual",
            "modem_transaction_id": self.modem_transaction_id,
            "status": self.status,
            "class_type": self.class_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }
