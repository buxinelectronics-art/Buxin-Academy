"""Monthly subscription access for students."""
import calendar
from datetime import datetime

from models import db
from models.payment import Payment


def add_one_calendar_month(dt: datetime) -> datetime:
    month = dt.month + 1
    year = dt.year
    if month > 12:
        month = 1
        year += 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day, hour=dt.hour, minute=dt.minute, second=dt.second)


def subscription_period_end(from_dt: datetime | None = None) -> datetime:
    return add_one_calendar_month(from_dt or datetime.utcnow())


def is_subscription_active(user) -> bool:
    if not user or user.role == "admin":
        return True
    if user.status != "active":
        return False
    if not user.subscription_expires_at:
        return True
    return user.subscription_expires_at > datetime.utcnow()


def backfill_subscription_expiry(user) -> None:
    """Set expiry from last approved payment for legacy active accounts."""
    if user.role != "student" or user.subscription_expires_at:
        return
    latest = (
        Payment.query.filter_by(user_id=user.id, status="approved")
        .order_by(Payment.reviewed_at.desc(), Payment.created_at.desc())
        .first()
    )
    if latest and latest.reviewed_at:
        user.subscription_expires_at = subscription_period_end(latest.reviewed_at)
    elif user.status == "active":
        user.subscription_expires_at = subscription_period_end(user.created_at or datetime.utcnow())


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
    """Start or stack one calendar month of access from approval."""
    now = approved_at or datetime.utcnow()
    base = now
    if user.subscription_expires_at and user.subscription_expires_at > base:
        base = user.subscription_expires_at
    expires = subscription_period_end(base)
    user.subscription_expires_at = expires
    user.status = "active"
    return expires
