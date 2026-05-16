from datetime import datetime

from flask import Blueprint, g, jsonify, request

from middlewares.auth import admin_required
from models import db
from models.admin_action import AdminAction
from models.class_model import ClassSession
from models.community import Comment, CommunityPost, PostLike
from models.notification import Notification
from models.payment import Payment
from models.schedule import StudentSchedule
from models.user import User

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _delete_student_record(user: User) -> None:
    uid = user.id
    AdminAction.query.filter_by(target_user_id=uid).delete(synchronize_session=False)
    Payment.query.filter_by(user_id=uid).delete(synchronize_session=False)
    Notification.query.filter_by(user_id=uid).delete(synchronize_session=False)
    StudentSchedule.query.filter_by(student_id=uid).delete(synchronize_session=False)
    PostLike.query.filter_by(user_id=uid).delete(synchronize_session=False)
    Comment.query.filter_by(user_id=uid).delete(synchronize_session=False)
    for post in CommunityPost.query.filter_by(user_id=uid).all():
        db.session.delete(post)
    db.session.delete(user)


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


@admin_bp.route("/students/<int:user_id>", methods=["GET"])
@admin_required
def get_student(user_id):
    user = db.session.get(User, user_id)
    if not user or user.role != "student":
        return jsonify({"error": "Student not found"}), 404
    return jsonify({"student": user.to_dict()})


ALLOWED_STUDENT_STATUS = frozenset({"pending", "active", "rejected"})


@admin_bp.route("/students/<int:user_id>", methods=["PATCH"])
@admin_required
def update_student(user_id):
    data = request.get_json() or {}
    user = db.session.get(User, user_id)
    if not user or user.role != "student":
        return jsonify({"error": "Student not found"}), 404

    if "full_name" in data and data["full_name"]:
        user.full_name = str(data["full_name"]).strip()
    if "phone" in data:
        user.phone = str(data.get("phone") or "")
    if "city" in data:
        user.city = str(data.get("city") or "")
    if "country_code" in data and data["country_code"]:
        user.country_code = str(data["country_code"]).upper().strip()
    if "class_type" in data and data["class_type"] in ("group", "individual"):
        user.class_type = data["class_type"]
    if "experience_level" in data:
        user.experience_level = str(data.get("experience_level") or "")
    if "learning_goals" in data:
        user.learning_goals = str(data.get("learning_goals") or "")
    if "status" in data:
        st = data["status"]
        if st not in ALLOWED_STUDENT_STATUS:
            return jsonify({"error": "Invalid status"}), 400
        user.status = st
    new_pw = data.get("new_password") or data.get("password")
    if new_pw:
        if len(str(new_pw)) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400
        user.set_password(str(new_pw))

    db.session.commit()
    return jsonify({"user": user.to_dict()})


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


@admin_bp.route("/students/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_student(user_id):
    user = db.session.get(User, user_id)
    if not user or user.role != "student":
        return jsonify({"error": "Student not found"}), 404
    _delete_student_record(user)
    db.session.commit()
    return jsonify({"message": "Student removed"}), 200


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


@admin_bp.route("/classes/<int:class_id>", methods=["DELETE"])
@admin_required
def delete_class(class_id):
    session = db.session.get(ClassSession, class_id)
    if not session:
        return jsonify({"error": "Class not found"}), 404
    db.session.delete(session)
    db.session.commit()
    return jsonify({"message": "Class removed"})


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
        "active_students": User.query.filter(
            User.role == "student",
            User.status == "active",
            User.subscription_expires_at > datetime.utcnow(),
        ).count(),
        "pending_payments": Payment.query.filter_by(status="pending").count(),
        "pending_students": User.query.filter_by(role="student", status="pending").count(),
    })
