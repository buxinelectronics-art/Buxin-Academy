from flask import Blueprint, g, jsonify

from middlewares.auth import active_student_required
from models import db
from models.class_model import ClassSession

class_bp = Blueprint("classes", __name__, url_prefix="/api/classes")


@class_bp.route("", methods=["GET"])
@active_student_required
def list_classes():
    class_type = g.current_user.class_type
    query = ClassSession.query
    if class_type and g.current_user.role == "student":
        query = query.filter(
            db.or_(
                ClassSession.class_type == class_type,
                ClassSession.class_type.is_(None),
            )
        )
    sessions = query.order_by(ClassSession.scheduled_at.desc()).limit(10).all()
    return jsonify({"classes": [c.to_dict() for c in sessions]})
