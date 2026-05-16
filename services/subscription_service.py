"""Monthly subscription access for students (30-day periods)."""
from datetime import datetime, timedelta

from models import db
from models.payment import Payment

SUBSCRIPTION_DAYS = 30


def subscription_period_end(from_dt: datetime | None = None) -> datetime:
    return (from_dt or datetime.utcnow()) + timedelta(days=SUBSCRIPTION_DAYS)


def is_subscription_active(user) -> bool:
    if not user or user.role == "admin":
        return True
    if user.status != "active":
        return False
    if not user.subscription_expires_at:
        return True
    return user.subscription_expires_at > datetime.utcnow()


def backfill_subscription_expiry(user) -> None:
    """Set 30-day window from last approved payment for legacy active accounts."""
    if user.role != "student" or user.subscription_expires_at:
        return
    latest = (
        Payment.query.filter_by(user_id=user.id, status="approved")
        .order_by(Payment.reviewed_at.desc(), Payment.created_at.desc())
        .first()
    )
    if latest and latest.reviewed_at:
        user.subscription_started_at = latest.reviewed_at
        user.subscription_expires_at = subscription_period_end(latest.reviewed_at)
    elif user.status == "active":
        started = user.created_at or datetime.utcnow()
        user.subscription_started_at = started
        user.subscription_expires_at = subscription_period_end(started)


def sync_subscription_status(user, *, commit: bool = True) -> None:
    """Mark students as expired when their paid month has ended."""
    if user.role != "student":
        return
    backfill_subscription_expiry(user)
    if user.status != "active":
        return
    if user.subscription_expires_at and user.subscription_expires_at <= datetime.utcnow():
        user.status = "expired"
        if commit:
            db.session.commit()


def extend_subscription_on_payment(user, approved_at: datetime | None = None) -> datetime:
    """Start or stack a 30-day access period from approval."""
    now = approved_at or datetime.utcnow()
    if user.subscription_expires_at and user.subscription_expires_at > now:
        started = user.subscription_expires_at
        expires = user.subscription_expires_at + timedelta(days=SUBSCRIPTION_DAYS)
    else:
        started = now
        expires = subscription_period_end(now)
    user.subscription_started_at = started
    user.subscription_expires_at = expires
    user.status = "active"
    return expires


def subscription_day_info(user) -> dict:
    """Day 1–30 progress for dashboard (UTC)."""
    if not user or user.role == "admin":
        return {
            "subscription_days_total": SUBSCRIPTION_DAYS,
            "subscription_day": None,
            "subscription_days_left": None,
            "subscription_expiring_soon": False,
        }
    now = datetime.utcnow()
    expires = user.subscription_expires_at
    started = user.subscription_started_at
    if not expires or not is_subscription_active(user):
        return {
            "subscription_days_total": SUBSCRIPTION_DAYS,
            "subscription_day": None,
            "subscription_days_left": 0,
            "subscription_expiring_soon": False,
        }
    if not started:
        started = expires - timedelta(days=SUBSCRIPTION_DAYS)
    elapsed = max(0, (now - started).days)
    day = min(SUBSCRIPTION_DAYS, elapsed + 1)
    days_left = max(0, (expires - now).days)
    if expires > now and days_left == 0:
        days_left = 1
    return {
        "subscription_days_total": SUBSCRIPTION_DAYS,
        "subscription_day": day,
        "subscription_days_left": days_left,
        "subscription_expiring_soon": 0 < days_left <= 7,
    }
