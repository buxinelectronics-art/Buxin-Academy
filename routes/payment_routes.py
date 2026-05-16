from datetime import datetime

from flask import Blueprint, current_app, g, jsonify, request

from middlewares.auth import admin_required, token_required
from models import db
from models.admin_action import AdminAction
from models.notification import Notification
from models.payment import Payment
from models.user import User
from services.cloudinary_service import PLACEHOLDER_RECEIPT, upload_image
from services.currency_service import get_class_prices

payment_bp = Blueprint("payments", __name__, url_prefix="/api/payments")


def _valid_receipt_b64(value) -> bool:
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    return len(s) > 80 and (s.startswith("data:image/") or s.startswith("data:application/"))


def _save_receipt(payment, file=None, receipt_base64=None):
    """Upload receipt; on Cloudinary failure keep payment row with placeholder."""
    try:
        if _valid_receipt_b64(receipt_base64):
            result = upload_image(receipt_base64.strip(), folder="buxinev/receipts")
        elif file and file.filename:
            result = upload_image(file, folder="buxinev/receipts")
        else:
            return False, "Payment receipt image is required"
        payment.receipt_url = result["url"]
        return True, None
    except Exception as exc:
        current_app.logger.error("Receipt upload for payment user_id=%s: %s", payment.user_id, exc)
        payment.receipt_url = PLACEHOLDER_RECEIPT
        return True, str(exc)


def _get_or_create_pending_payment(user, class_type, method):
    """One open pending payment per student — avoids duplicate rows on double-click."""
    Payment.query.filter(
        Payment.user_id == user.id,
        Payment.status == "pending",
        Payment.receipt_url.is_(None),
    ).delete(synchronize_session=False)

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
    db.session.flush()
    return payment


@payment_bp.route("/submit", methods=["POST"])
@token_required
def submit_payment():
    """Payment + receipt: JSON {receipt_base64} or multipart form."""
    user = g.current_user

    # force=True: some clients/proxies drop Content-Type; still parse JSON body
    data = request.get_json(silent=True, force=True) or {}
    file = request.files.get("receipt")
    class_type = (
        data.get("class_type")
        or request.form.get("class_type")
        or user.class_type
        or "group"
    )
    method = data.get("payment_method") or request.form.get("payment_method") or ""
    receipt_base64 = data.get("receipt_base64") or data.get("receipt") or ""

    if not method:
        return jsonify({"error": "Select a payment method"}), 400
    has_file = file and file.filename
    if not _valid_receipt_b64(receipt_base64) and not has_file:
        return jsonify({"error": "Payment receipt image is required"}), 400

    if user.class_type != class_type:
        user.class_type = class_type

    try:
        payment = _get_or_create_pending_payment(user, class_type, method)
        ok, upload_note = _save_receipt(payment, file=file, receipt_base64=receipt_base64)
        if not ok:
            db.session.rollback()
            return jsonify({"error": upload_note}), 400

        msg = "Your payment is under review. We'll notify you when approved."
        if upload_note:
            msg += " (Receipt stored; admin may request a clearer image if needed.)"

        db.session.add(
            Notification(
                user_id=user.id,
                title="Receipt Uploaded",
                message=msg,
            )
        )
        db.session.commit()
        payload = {"payment": payment.to_dict(), "user": user.to_dict()}
        if upload_note:
            payload["upload_warning"] = upload_note
        return jsonify(payload), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("submit_payment failed")
        return jsonify({"error": f"Payment could not be saved: {str(e)}"}), 500


@payment_bp.route("", methods=["POST"])
@token_required
def create_payment():
    user = g.current_user
    data = request.get_json() or {}
    class_type = data.get("class_type") or user.class_type or "group"
    method = data.get("payment_method", "")
    payment = _get_or_create_pending_payment(user, class_type, method)
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
    data = request.get_json(silent=True, force=True) or {}
    receipt_base64 = data.get("receipt_base64") or data.get("receipt") or ""
    if _valid_receipt_b64(receipt_base64) or (file and file.filename):
        ok, err = _save_receipt(payment, file=file, receipt_base64=receipt_base64)
        if not ok:
            return jsonify({"error": err}), 400
        if err:
            current_app.logger.warning("upload_receipt partial failure user_id=%s: %s", user.id, err)
    elif request.get_json() and request.get_json().get("receipt_url"):
        payment.receipt_url = request.get_json()["receipt_url"]
    else:
        return jsonify({"error": "Receipt file required"}), 400

    db.session.add(
        Notification(
            user_id=user.id,
            title="Receipt Uploaded",
            message="Your payment receipt is under review.",
        )
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
    class_type = request.args.get("class_type")
    query = Payment.query.join(User)
    if status:
        query = query.filter(Payment.status == status)
    if country:
        query = query.filter(User.country_code == country.upper())
    if class_type:
        query = query.filter(Payment.class_type == class_type)
    payments = query.order_by(Payment.created_at.desc()).all()
    result = []
    for p in payments:
        item = p.to_dict()
        item["student_name"] = p.user.full_name
        item["email"] = p.user.email
        item["country_code"] = p.user.country_code
        item["profile_picture"] = p.user.profile_picture
        item["student_class_type"] = p.user.class_type
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
    Payment.query.filter(
        Payment.user_id == user.id,
        Payment.id != payment.id,
        Payment.status == "pending",
    ).update({"status": "rejected"})
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
