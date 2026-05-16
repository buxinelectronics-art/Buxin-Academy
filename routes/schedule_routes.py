from flask import Blueprint, g, jsonify, request

from middlewares.auth import active_student_required, admin_required, token_required
from models import db
from models.schedule import Schedule, StudentSchedule
from services.schedule_slots import SCHEDULE_RULES, ordered_available_slots

schedule_bp = Blueprint("schedules", __name__, url_prefix="/api/schedules")


@schedule_bp.route("", methods=["GET"])
def list_schedules():
    slots = ordered_available_slots()
    return jsonify({
        "schedules": [s.to_dict() for s in slots],
        "timezone": SCHEDULE_RULES["timezone"],
        "rules": SCHEDULE_RULES,
    })


@schedule_bp.route("", methods=["POST"])
@admin_required
def create_schedule():
    data = request.get_json() or {}
    slot = Schedule(
        day_of_week=data["day_of_week"],
        time_slot=data["time_slot"],
        is_available=True,
        created_by=g.current_user.id,
    )
    db.session.add(slot)
    db.session.commit()
    return jsonify({"schedule": slot.to_dict()}), 201


@schedule_bp.route("/select", methods=["POST"])
@token_required
def select_schedules():
    data = request.get_json() or {}
    schedule_ids = data.get("schedule_ids", [])
    if len(schedule_ids) != 2:
        return jsonify({
            "error": "Select exactly 2 time slots per week (2 hours, IST). "
            "Two different days or 2 slots on the same day.",
        }), 400

    found = Schedule.query.filter(
        Schedule.id.in_(schedule_ids), Schedule.is_available.is_(True)
    ).count()
    if found != 2:
        return jsonify({"error": "Invalid or unavailable time slot"}), 400

    StudentSchedule.query.filter_by(student_id=g.current_user.id).delete()
    for i, sid in enumerate(schedule_ids[:2]):
        db.session.add(
            StudentSchedule(
                student_id=g.current_user.id,
                schedule_id=sid,
                preference_order=i + 1,
            )
        )
    db.session.commit()
    selections = StudentSchedule.query.filter_by(student_id=g.current_user.id).all()
    return jsonify({"schedules": [s.to_dict() for s in selections]})


@schedule_bp.route("/my", methods=["GET"])
@active_student_required
def my_schedules():
    selections = StudentSchedule.query.filter_by(student_id=g.current_user.id).all()
    return jsonify({"schedules": [s.to_dict() for s in selections]})
