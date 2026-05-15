from flask import Blueprint, g, jsonify, request

from middlewares.auth import token_required
from models import db
from models.notification import Notification

notification_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@notification_bp.route("", methods=["GET"])
@token_required
def list_notifications():
    notes = (
        Notification.query.filter_by(user_id=g.current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(30)
        .all()
    )
    return jsonify({"notifications": [n.to_dict() for n in notes]})


@notification_bp.route("/<int:note_id>/read", methods=["POST"])
@token_required
def mark_read(note_id):
    note = db.session.get(Notification, note_id)
    if note and note.user_id == g.current_user.id:
        note.is_read = True
        db.session.commit()
    return jsonify({"success": True})


@notification_bp.route("/read-all", methods=["POST"])
@token_required
def mark_all_read():
    Notification.query.filter_by(user_id=g.current_user.id, is_read=False).update(
        {"is_read": True}
    )
    db.session.commit()
    return jsonify({"success": True})
