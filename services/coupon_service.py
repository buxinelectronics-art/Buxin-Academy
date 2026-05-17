"""One-time class-specific discount coupons."""
from datetime import datetime

from models import db
from models.coupon import Coupon, generate_coupon_code
from models.payment import Payment


class CouponError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def normalize_code(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "")


def validate_coupon_for_user(code: str, class_type: str, user_id: int | None = None) -> Coupon:
    normalized = normalize_code(code)
    if len(normalized) < 4:
        raise CouponError("Enter a valid coupon code")

    coupon = Coupon.query.filter_by(code=normalized).first()
    if not coupon:
        raise CouponError("Coupon not found")
    if coupon.is_used:
        raise CouponError("This coupon has already been used")
    if coupon.class_type != class_type:
        label = "group class" if coupon.class_type == "group" else "individual class"
        raise CouponError(f"This coupon is only valid for {label}")

    # Block if another open payment already holds this coupon
    reserved = Payment.query.filter(
        Payment.coupon_id == coupon.id,
        Payment.status == "pending",
    ).first()
    if reserved and (user_id is None or reserved.user_id != user_id):
        raise CouponError("This coupon is already applied to another checkout")

    return coupon


def discounted_amounts(amount_usd: float, amount_local: float, discount_percent: int) -> tuple[float, float]:
    pct = max(0, min(100, int(discount_percent)))
    factor = (100 - pct) / 100.0
    return round(amount_usd * factor, 2), round(amount_local * factor, 2)


def apply_coupon_to_payment(payment: Payment, coupon: Coupon) -> None:
    if payment.original_amount_local is None:
        payment.original_amount_usd = payment.amount_usd
        payment.original_amount_local = payment.amount_local
    base_usd = payment.original_amount_usd
    base_local = payment.original_amount_local
    payment.amount_usd, payment.amount_local = discounted_amounts(
        base_usd, base_local, coupon.discount_percent
    )
    payment.coupon_id = coupon.id
    payment.discount_percent = coupon.discount_percent


def mark_coupon_used(coupon: Coupon, user_id: int, payment_id: int) -> None:
    coupon.used_by_user_id = user_id
    coupon.used_at = datetime.utcnow()
    coupon.payment_id = payment_id


def release_coupon_from_payment(payment: Payment) -> None:
    if not payment.coupon_id:
        return
    coupon = db.session.get(Coupon, payment.coupon_id)
    if coupon and not coupon.is_used:
        payment.coupon_id = None
        payment.discount_percent = None


def create_coupon(
    *,
    class_type: str,
    discount_percent: int,
    code: str | None = None,
    admin_id: int | None = None,
    notes: str = "",
) -> Coupon:
    if class_type not in ("group", "individual"):
        raise CouponError("class_type must be group or individual")
    pct = int(discount_percent)
    if not 1 <= pct <= 100:
        raise CouponError("discount_percent must be between 1 and 100")

    normalized = normalize_code(code) if code else ""
    for _ in range(8):
        candidate = normalized or generate_coupon_code()
        if not Coupon.query.filter_by(code=candidate).first():
            normalized = candidate
            break
    else:
        raise CouponError("Could not generate a unique coupon code")

    coupon = Coupon(
        code=normalized,
        class_type=class_type,
        discount_percent=min(100, max(1, pct)),
        created_by_admin_id=admin_id,
        notes=(notes or "")[:200] or None,
    )
    db.session.add(coupon)
    return coupon
