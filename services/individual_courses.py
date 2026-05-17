"""Individual mentorship tracks (6-month programs)."""

INDIVIDUAL_COURSES = [
    {"id": "robotics", "name": "Robotics"},
    {"id": "iot", "name": "IoT (Internet of Things)"},
    {"id": "python", "name": "Python Programming"},
    {"id": "c_programming", "name": "C Programming"},
    {"id": "cpp", "name": "C++"},
    {"id": "arduino", "name": "Arduino Programming"},
    {"id": "frontend", "name": "Front-End Development"},
    {"id": "backend", "name": "Back-End Development"},
    {"id": "fullstack", "name": "Full Stack Development"},
    {"id": "ai_automation", "name": "AI & Automation"},
]

INDIVIDUAL_SUBSCRIPTION_DAYS = 180  # 6 months
GROUP_SUBSCRIPTION_DAYS = 30

_COURSE_BY_ID = {c["id"]: c for c in INDIVIDUAL_COURSES}


def list_individual_courses():
    return list(INDIVIDUAL_COURSES)


def is_valid_course_id(course_id: str) -> bool:
    return course_id in _COURSE_BY_ID


def course_name(course_id: str | None) -> str | None:
    if not course_id:
        return None
    entry = _COURSE_BY_ID.get(course_id)
    return entry["name"] if entry else None


def subscription_days_for_class_type(class_type: str | None) -> int:
    if class_type == "individual":
        return INDIVIDUAL_SUBSCRIPTION_DAYS
    return GROUP_SUBSCRIPTION_DAYS
