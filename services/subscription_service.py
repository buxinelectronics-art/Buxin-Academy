"""Subscription access: 30-day group classes, 6-month individual courses."""
from datetime import datetime, timedelta

from models import db
from models.payment import Payment
from models.user import User
from services.academy_settings_service import get_class_period_started_at, is_class_period_started
from services.individual_courses import subscription_days_for_class_type


def subscription_period_end(from_dt: datetime | None = None, user: User | None = None) -> datetime:
    days = subscription_days_for_class_type(user.class_type if user else None)
    return (from_dt or datetime.utcnow()) + timedelta(days=days)


def is_subscription_active(user) -> bool:
    """True when the class period is running for this student."""
    if not user or user.role == "admin":
        return True
    if user.status != "active":
        return False
    if not is_class_period_started():
        return False
    if not user.subscription_expires_at:
        return False
    return user.subscription_expires_at > datetime.utcnow()


def has_app_access(user) -> bool:
    """Paid & approved with a current access period (not after Day 1–30 / 6-month end)."""
    if not user or user.role == "admin":
        return True
    if user.status != "active":
        return False
    if needs_renewal(user):
        return False
    return True


def awaiting_class_start(user) -> bool:
    """Paid & active, but admin has not started the global class period yet."""
    if not user or user.role != "student":
        return False
    return user.status == "active" and not is_class_period_started()


def needs_renewal(user) -> bool:
    """Class period has started and access ended — pay again to unlock."""
    if not user or user.role != "student":
        return False
    if user.status == "expired":
        return True
    if not is_class_period_started():
        return False
    if user.status == "active" and not is_subscription_active(user):
        return True
    return False


def backfill_subscription_expiry(user) -> None:
    """Set access window only after admin has started the class period."""
    if user.role != "student" or user.subscription_expires_at:
        return
    if not is_class_period_started():
        return
    latest = (
        Payment.query.filter_by(user_id=user.id, status="approved")
        .order_by(Payment.reviewed_at.desc(), Payment.created_at.desc())
        .first()
    )
    started_at = get_class_period_started_at() or datetime.utcnow()
    if latest and latest.reviewed_at:
        anchor = max(latest.reviewed_at, started_at)
        user.subscription_started_at = anchor
        user.subscription_expires_at = subscription_period_end(anchor, user)
    elif user.status == "active":
        user.subscription_started_at = started_at
        user.subscription_expires_at = subscription_period_end(started_at, user)


def sync_subscription_status(user, *, commit: bool = True) -> None:
    """Mark students as expired when their paid period has ended."""
    if user.role != "student":
        return
    if not is_class_period_started():
        return
    backfill_subscription_expiry(user)
    if user.status != "active":
        return
    if user.subscription_expires_at and user.subscription_expires_at <= datetime.utcnow():
        user.status = "expired"
        if commit:
            db.session.commit()


def activate_student_on_payment(user, approved_at: datetime | None = None) -> None:
    """Approve payment; start timer only if class period already started."""
    now = approved_at or datetime.utcnow()
    user.status = "active"
    if is_class_period_started():
        extend_subscription_on_payment(user, now, set_status=False)
    else:
        user.subscription_started_at = None
        user.subscription_expires_at = None


def extend_subscription_on_payment(
    user, approved_at: datetime | None = None, *, set_status: bool = True
) -> datetime:
    """Start or stack an access period from approval (30 or 180 days by class type)."""
    now = approved_at or datetime.utcnow()
    days = subscription_days_for_class_type(user.class_type)
    if user.subscription_expires_at and user.subscription_expires_at > now:
        started = user.subscription_expires_at
        expires = user.subscription_expires_at + timedelta(days=days)
    else:
        started = now
        expires = subscription_period_end(now, user)
    user.subscription_started_at = started
    user.subscription_expires_at = expires
    if set_status:
        user.status = "active"
    return expires


def start_class_period_for_all_active() -> dict:
    """Admin: begin Day 1 for every active student without a running period."""
    from models.academy_settings import AcademySettings

    settings = db.session.get(AcademySettings, 1)
    if not settings:
        settings = AcademySettings(id=1)
        db.session.add(settings)
    if settings.class_period_started_at:
        return {
            "already_started": True,
            "started_at": settings.class_period_started_at,
            "students_started": 0,
        }

    now = datetime.utcnow()
    settings.class_period_started_at = now

    students = User.query.filter_by(role="student", status="active").all()
    count = 0
    for user in students:
        user.subscription_started_at = now
        user.subscription_expires_at = subscription_period_end(now, user)
        count += 1

    return {
        "already_started": False,
        "started_at": now,
        "students_started": count,
    }


def subscription_day_info(user) -> dict:
    """Day progress for dashboard (UTC)."""
    total_days = subscription_days_for_class_type(
        user.class_type if user and user.role == "student" else None
    )
    base = {
        "subscription_days_total": total_days,
        "subscription_day": None,
        "subscription_days_left": None,
        "subscription_expiring_soon": False,
        "class_period_started": is_class_period_started(),
        "awaiting_class_start": awaiting_class_start(user),
        "subscription_active": is_subscription_active(user),
        "has_app_access": has_app_access(user),
        "needs_renewal": needs_renewal(user),
    }
    if not user or user.role == "admin":
        return base
    if awaiting_class_start(user):
        return base
    now = datetime.utcnow()
    expires = user.subscription_expires_at
    started = user.subscription_started_at
    if not expires or not is_subscription_active(user):
        return {
            **base,
            "subscription_days_left": 0,
        }
    if not started:
        started = expires - timedelta(days=total_days)
    elapsed = max(0, (now - started).days)
    day = min(total_days, elapsed + 1)
    days_left = max(0, (expires - now).days)
    if expires > now and days_left == 0:
        days_left = 1
    warn_window = 14 if user.class_type == "individual" else 7
    return {
        **base,
        "subscription_day": day,
        "subscription_days_left": days_left,
        "subscription_expiring_soon": 0 < days_left <= warn_window,
    }
