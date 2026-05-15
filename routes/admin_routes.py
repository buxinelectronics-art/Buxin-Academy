from flask import Blueprint, g, jsonify, request

from middlewares.auth import admin_required
from models import db
from models.class_model import ClassSession
from models.notification import Notification
from models.user import User

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.route("/students", methods=["GET"])
@admin_required
def list_students():
    status = request.args.get("status")
    country = request.args.get("country")
    class_type = request.args.get("class_type")
    search = request.args.get("search", "").strip()
    query = User.query.filter_by(role="student")
    if status:
        query = query.filter(User.status == status)
    if country:
        query = query.filter(User.country_code == country.upper())
    if class_type:
        query = query.filter(User.class_type == class_type)
    if search:
        query = query.filter(
            db.or_(
                User.full_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
            )
        )
    students = query.order_by(User.created_at.desc()).all()
    return jsonify({"students": [s.to_dict() for s in students]})


@admin_bp.route("/students/<int:user_id>/status", methods=["PATCH"])
@admin_required
def update_student_status(user_id):
    data = request.get_json() or {}
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Student not found"}), 404
    user.status = data.get("status", user.status)
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@admin_bp.route("/classes", methods=["GET"])
@admin_required
def list_classes():
    sessions = ClassSession.query.order_by(ClassSession.scheduled_at.desc()).all()
    return jsonify({"classes": [c.to_dict() for c in sessions]})


@admin_bp.route("/classes", methods=["POST"])
@admin_required
def create_class():
    from datetime import datetime

    data = request.get_json() or {}
    scheduled = None
    if data.get("scheduled_at"):
        scheduled = datetime.fromisoformat(data["scheduled_at"].replace("Z", ""))
    session = ClassSession(
        title=data.get("title", "Robotics Class"),
        class_type=data.get("class_type", "group"),
        meet_link=data.get("meet_link"),
        zoom_link=data.get("zoom_link"),
        scheduled_at=scheduled,
        is_live=data.get("is_live", False),
        created_by=g.current_user.id,
    )
    db.session.add(session)
    db.session.commit()

    students = User.query.filter_by(role="student", status="active").all()
    for s in students:
        db.session.add(
            Notification(
                user_id=s.id,
                title="New Class Scheduled",
                message=f"{session.title} — check your dashboard to join.",
            )
        )
    db.session.commit()
    return jsonify({"class": session.to_dict()}), 201


@admin_bp.route("/announcements", methods=["POST"])
@admin_required
def send_announcement():
    data = request.get_json() or {}
    students = User.query.filter_by(role="student", status="active").all()
    for s in students:
        db.session.add(
            Notification(
                user_id=s.id,
                title=data.get("title", "Announcement"),
                message=data.get("message", ""),
            )
        )
    db.session.commit()
    return jsonify({"message": f"Sent to {len(students)} students"})


@admin_bp.route("/stats", methods=["GET"])
@admin_required
def stats():
    from models.payment import Payment

    return jsonify({
        "total_students": User.query.filter_by(role="student").count(),
        "active_students": User.query.filter_by(role="student", status="active").count(),
        "pending_payments": Payment.query.filter_by(status="pending").count(),
        "pending_students": User.query.filter_by(role="student", status="pending").count(),
    })
