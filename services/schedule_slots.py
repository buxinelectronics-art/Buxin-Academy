"""Individual class time slots — Indian Standard Time (IST)."""
from models import db
from models.schedule import Schedule

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

HOURLY_SLOTS = (
    "10:00 AM – 11:00 AM",
    "11:00 AM – 12:00 PM",
    "12:00 PM – 1:00 PM",
    "1:00 PM – 2:00 PM",
    "2:00 PM – 3:00 PM",
    "3:00 PM – 4:00 PM",
    "4:00 PM – 5:00 PM",
    "5:00 PM – 6:00 PM",
    "6:00 PM – 7:00 PM",
    "7:00 PM – 8:00 PM",
    "8:00 PM – 9:00 PM",
    "9:00 PM – 10:00 PM",
)

IST_SCHEDULE_SLOTS = [(day, slot) for day in DAYS for slot in HOURLY_SLOTS]

SCHEDULE_RULES = {
    "timezone": "Asia/Kolkata (IST)",
    "class_duration_hours": 1,
    "hours_per_week": 2,
    "slots_to_select": 2,
    "allow_same_day": True,
    "summary": (
        "Each class is 1 hour. Pick exactly 2 slots per week (2 hours total). "
        "You may choose 2 different days or 2 slots on the same day."
    ),
}


def sync_ist_schedule_slots() -> int:
    canonical = set(IST_SCHEDULE_SLOTS)
    added = 0
    for day, time_slot in IST_SCHEDULE_SLOTS:
        row = Schedule.query.filter_by(day_of_week=day, time_slot=time_slot).first()
        if not row:
            db.session.add(Schedule(day_of_week=day, time_slot=time_slot, is_available=True))
            added += 1
        elif not row.is_available:
            row.is_available = True
    for row in Schedule.query.all():
        if (row.day_of_week, row.time_slot) not in canonical:
            row.is_available = False
    db.session.commit()
    return added


def ordered_available_slots():
    by_key = {(s.day_of_week, s.time_slot): s for s in Schedule.query.filter_by(is_available=True).all()}
    return [by_key[key] for key in IST_SCHEDULE_SLOTS if key in by_key]
