from datetime import datetime

from flask import Blueprint, g, jsonify, request

from middlewares.auth import admin_required, token_required
from models import db
from models.admin_action import AdminAction
from models.notification import Notification
from models.payment import Payment
from models.user import User
from services.cloudinary_service import upload_image
from services.currency_service import get_class_prices

payment_bp = Blueprint("payments", __name__, url_prefix="/api/payments")


@payment_bp.route("", methods=["POST"])
@token_required
def create_payment():
    user = g.current_user
    data = request.get_json() or {}
    class_type = data.get("class_type") or user.class_type or "group"
    method = data.get("payment_method", "")

    prices = get_class_prices(user.country_code)
    price = prices["group"] if class_type == "group" else prices["individual"]

    payment = Payment(
        user_id=user.id,
        amount_usd=price["usd"],
        amount_local=price["local"],
        currency=price["currency"],
        payment_method=method,
        class_type=class_type,
        status="pending",
    )
    db.session.add(payment)
    db.session.commit()
    return jsonify({"payment": payment.to_dict()}), 201


@payment_bp.route("/upload-receipt", methods=["POST"])
@token_required
def upload_receipt():
    user = g.current_user
    payment = (
        Payment.query.filter_by(user_id=user.id, status="pending")
        .order_by(Payment.created_at.desc())
        .first()
    )
    if not payment:
        return jsonify({"error": "No pending payment found"}), 404

    file = request.files.get("receipt")
    if file:
        try:
            result = upload_image(file, folder="buxinev/receipts")
            payment.receipt_url = result["url"]
        except Exception as e:
            return jsonify({"error": f"Upload failed: {str(e)}"}), 500
    elif request.get_json() and request.get_json().get("receipt_url"):
        payment.receipt_url = request.get_json()["receipt_url"]
    else:
        return jsonify({"error": "Receipt file required"}), 400

    db.session.commit()
    Notification(
        user_id=user.id,
        title="Receipt Uploaded",
        message="Your payment receipt is under review. We'll notify you once approved.",
    )
    db.session.commit()
    return jsonify({"payment": payment.to_dict()})


@payment_bp.route("/my", methods=["GET"])
@token_required
def my_payments():
    payments = (
        Payment.query.filter_by(user_id=g.current_user.id)
        .order_by(Payment.created_at.desc())
        .all()
    )
    return jsonify({"payments": [p.to_dict() for p in payments]})


@payment_bp.route("/admin/all", methods=["GET"])
@admin_required
def admin_payments():
    status = request.args.get("status")
    country = request.args.get("country")
    query = Payment.query.join(User)
    if status:
        query = query.filter(Payment.status == status)
    if country:
        query = query.filter(User.country_code == country.upper())
    payments = query.order_by(Payment.created_at.desc()).all()
    result = []
    for p in payments:
        item = p.to_dict()
        item["student_name"] = p.user.full_name
        item["email"] = p.user.email
        item["country_code"] = p.user.country_code
        result.append(item)
    return jsonify({"payments": result})


@payment_bp.route("/admin/<int:payment_id>/approve", methods=["POST"])
@admin_required
def approve_payment(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        return jsonify({"error": "Payment not found"}), 404
    payment.status = "approved"
    payment.reviewed_at = datetime.utcnow()
    user = payment.user
    user.status = "active"
    db.session.add(
        AdminAction(
            admin_id=g.current_user.id,
            action_type="approve_payment",
            target_user_id=user.id,
            details=f"Payment #{payment_id} approved",
        )
    )
    db.session.add(
        Notification(
            user_id=user.id,
            title="Payment Approved!",
            message="Welcome to Buxin Academy! Your dashboard and community are now unlocked.",
        )
    )
    db.session.commit()
    from flask import current_app

    current_app.extensions["socketio"].emit(
        "notification",
        {"title": "Payment Approved!", "message": "Your account is now active."},
        room=f"user_{user.id}",
    )
    return jsonify({"payment": payment.to_dict(), "user": user.to_dict()})


@payment_bp.route("/admin/<int:payment_id>/reject", methods=["POST"])
@admin_required
def reject_payment(payment_id):
    data = request.get_json() or {}
    payment = db.session.get(Payment, payment_id)
    if not payment:
        return jsonify({"error": "Payment not found"}), 404
    payment.status = "rejected"
    payment.reviewed_at = datetime.utcnow()
    reason = data.get("reason", "Payment could not be verified.")
    db.session.add(
        AdminAction(
            admin_id=g.current_user.id,
            action_type="reject_payment",
            target_user_id=payment.user_id,
            details=reason,
        )
    )
    db.session.add(
        Notification(
            user_id=payment.user_id,
            title="Payment Rejected",
            message=reason,
        )
    )
    db.session.commit()
    return jsonify({"payment": payment.to_dict()})

