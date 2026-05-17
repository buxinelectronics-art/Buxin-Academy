from datetime import datetime

from flask import Blueprint, current_app, g, jsonify, request

from middlewares.auth import admin_required, token_required
from models import db
from models.admin_action import AdminAction
from models.notification import Notification
from models.coupon import Coupon
from models.payment import Payment
from models.user import User
from services.cloudinary_service import PLACEHOLDER_RECEIPT, upload_image
from services.coupon_service import (
    CouponError,
    apply_coupon_to_payment,
    mark_coupon_used,
    validate_coupon_for_user,
)
from services.currency_service import get_class_prices
from services.modempay_service import (
    ModemPayError,
    create_checkout_payment_link,
    is_configured,
    parse_webhook_event,
    retrieve_transaction,
)

payment_bp = Blueprint("payments", __name__, url_prefix="/api/payments")

MODEMPAY_INSTANT_METHODS = frozenset({
    "Wave",
    "AfriMoney",
    "APS Wallet",
    "Mobile Wallet",
})
MODEMPAY_COUNTRIES = frozenset({"GM"})


def _finalize_coupon_on_approval(payment: Payment) -> None:
    if not payment.coupon_id:
        return
    coupon = db.session.get(Coupon, payment.coupon_id)
    if coupon and not coupon.is_used:
        mark_coupon_used(coupon, payment.user_id, payment.id)


def _activate_student_payment(payment, *, admin_id=None, details=""):
    """Approve payment and unlock student dashboard."""
    from services.academy_settings_service import is_class_period_started
    from services.subscription_service import activate_student_on_payment

    payment.status = "approved"
    payment.reviewed_at = datetime.utcnow()
    user = payment.user
    activate_student_on_payment(user, payment.reviewed_at)
    _finalize_coupon_on_approval(payment)
    class_started = is_class_period_started()
    Payment.query.filter(
        Payment.user_id == user.id,
        Payment.id != payment.id,
        Payment.status == "pending",
    ).update({"status": "rejected"})
    if admin_id:
        db.session.add(
            AdminAction(
                admin_id=admin_id,
                action_type="approve_payment",
                target_user_id=user.id,
                details=details or f"Payment #{payment.id} approved",
            )
        )
    coupon_note = ""
    if payment.coupon_id and payment.discount_percent:
        if payment.discount_percent >= 100:
            coupon_note = " Your free-access coupon has been applied."
        else:
            coupon_note = f" Your {payment.discount_percent}% coupon has been applied."
    db.session.add(
        Notification(
            user_id=user.id,
            title="Payment Approved!",
            message=(
                "Payment approved! Your class period starts now (Day 1). "
                "Classes and community are unlocked."
                + coupon_note
                if class_started
                else "Payment approved! You are registered. Day 1 will begin when your instructor starts the class period."
                + coupon_note
            ),
        )
    )
    db.session.commit()
    from flask import current_app

    current_app.extensions["socketio"].emit(
        "notification",
        {
            "title": "Payment Approved!",
            "message": "Your account is now active.",
            "status": "active",
            "user_status": "active",
        },
        room=f"user_{user.id}",
    )
    return user


def _metadata_payment_id(metadata) -> int | None:
    if not metadata or not isinstance(metadata, dict):
        return None
    raw = metadata.get("payment_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _client_transaction_ok(txn: dict, payment: Payment, transaction_id: str) -> bool:
    """Fallback when Modem Pay secret API is unreachable from the server."""
    if not txn or not isinstance(txn, dict):
        return False
    tx_id = str(
        txn.get("id")
        or txn.get("transaction_id")
        or txn.get("transaction_reference")
        or ""
    )
    if tx_id and tx_id != str(transaction_id):
        return False
    status = (txn.get("status") or "").lower()
    if status not in ("completed", "succeeded", "success"):
        return False
    if not _amount_matches(payment, txn.get("amount")):
        return False
    meta_pid = _metadata_payment_id(txn.get("metadata"))
    if meta_pid is not None and meta_pid != payment.id:
        return False
    return True


def _amount_matches(payment: Payment, paid_amount) -> bool:
    try:
        paid = float(paid_amount)
        expected = float(payment.amount_local)
        if paid >= expected * 50:
            paid = paid / 100
        return abs(paid - expected) <= max(2.0, expected * 0.03)
    except (TypeError, ValueError):
        return False


def _complete_modempay_payment(payment: Payment, transaction_id: str, txn: dict):
    if payment.status == "approved":
        return payment.user
    status = (txn.get("status") or "").lower()
    if status not in ("completed", "succeeded", "success"):
        raise ModemPayError("Payment not completed yet")
    if not _amount_matches(payment, txn.get("amount")):
        raise ModemPayError("Payment amount does not match")
    payment.modem_transaction_id = transaction_id
    payment.payment_channel = "modempay"
    payment.receipt_url = payment.receipt_url or f"modempay://{transaction_id}"
    return _activate_student_payment(
        payment,
        details=f"Modem Pay auto-approved ({transaction_id})",
    )


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
        original_amount_usd=price["usd"],
        original_amount_local=price["local"],
        currency=price["currency"],
        payment_method=method,
        class_type=class_type,
        status="pending",
    )
    db.session.add(payment)
    db.session.flush()
    return payment


def _payment_pricing_payload(payment: Payment, user: User) -> dict:
    return {
        "payment": payment.to_dict(),
        "user": user.to_dict(),
        "original_amount_local": payment.original_amount_local or payment.amount_local,
        "original_amount_usd": payment.original_amount_usd or payment.amount_usd,
        "discount_percent": payment.discount_percent,
        "is_free": (payment.amount_local or 0) <= 0.01,
    }


@payment_bp.route("/validate-coupon", methods=["POST"])
@token_required
def validate_coupon():
    """Check a coupon without applying it."""
    data = request.get_json() or {}
    user = g.current_user
    class_type = data.get("class_type") or user.class_type or "group"
    code = data.get("code") or data.get("coupon_code") or ""
    try:
        coupon = validate_coupon_for_user(code, class_type, user.id)
    except CouponError as exc:
        return jsonify({"valid": False, "error": exc.message}), exc.status

    prices = get_class_prices(user.country_code)
    price = prices["group"] if class_type == "group" else prices["individual"]
    from services.coupon_service import discounted_amounts

    final_usd, final_local = discounted_amounts(
        price["usd"], price["local"], coupon.discount_percent
    )
    return jsonify(
        {
            "valid": True,
            "code": coupon.code,
            "class_type": coupon.class_type,
            "discount_percent": coupon.discount_percent,
            "is_full": coupon.discount_percent >= 100,
            "original_amount_local": price["local"],
            "original_amount_usd": price["usd"],
            "final_amount_local": final_local,
            "final_amount_usd": final_usd,
            "currency": price["currency"],
        }
    )


@payment_bp.route("/apply-coupon", methods=["POST"])
@token_required
def apply_coupon_route():
    """Apply coupon to checkout; 100% coupons activate the student immediately."""
    data = request.get_json() or {}
    user = g.current_user
    class_type = data.get("class_type") or user.class_type or "group"
    code = data.get("code") or data.get("coupon_code") or ""

    try:
        coupon = validate_coupon_for_user(code, class_type, user.id)
    except CouponError as exc:
        return jsonify({"error": exc.message}), exc.status

    if user.class_type != class_type:
        user.class_type = class_type

    try:
        payment = _get_or_create_pending_payment(user, class_type, "Coupon")
        apply_coupon_to_payment(payment, coupon)
        db.session.flush()

        if (payment.amount_local or 0) <= 0.01 or coupon.discount_percent >= 100:
            payment.payment_method = "Coupon (100% off)"
            payment.receipt_url = payment.receipt_url or "coupon:free"
            activated_user = _activate_student_payment(
                payment,
                details=f"Free coupon {coupon.code}",
            )
            db.session.commit()
            period = (
                "6-month course period"
                if class_type == "individual"
                else "30-day class month"
            )
            return jsonify(
                {
                    "activated": True,
                    "message": (
                        f"Coupon applied for this {period}. When it ends, renew with payment "
                        "or a new coupon for the next period."
                    ),
                    **_payment_pricing_payload(payment, activated_user),
                }
            )

        db.session.commit()
        return jsonify(
            {
                "activated": False,
                "message": (
                    f"Coupon applied: {coupon.discount_percent}% off this period only. "
                    "When your access ends, pay or use a new coupon to continue."
                ),
                **_payment_pricing_payload(payment, user),
            }
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("apply_coupon failed")
        return jsonify({"error": str(exc)}), 500


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

    if user.class_type != class_type:
        user.class_type = class_type

    try:
        payment = _get_or_create_pending_payment(user, class_type, method)
        if (payment.amount_local or 0) <= 0.01:
            payment.payment_method = method or "Coupon"
            activated_user = _activate_student_payment(
                payment,
                details="Zero-balance checkout",
            )
            if payment.coupon_id:
                coupon = db.session.get(Coupon, payment.coupon_id)
                if coupon and not coupon.is_used:
                    mark_coupon_used(coupon, user.id, payment.id)
            db.session.commit()
            return jsonify(
                {
                    "payment": payment.to_dict(),
                    "user": activated_user.to_dict(),
                    "activated": True,
                    "message": "Your account is now active.",
                }
            ), 201

        if not method:
            return jsonify({"error": "Select a payment method"}), 400
        has_file = file and file.filename
        if not _valid_receipt_b64(receipt_base64) and not has_file:
            return jsonify({"error": "Payment receipt image is required"}), 400

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


@payment_bp.route("/modempay/config", methods=["GET"])
def modempay_config():
    """Public Modem Pay settings (public key only)."""
    enabled = is_configured()
    return jsonify(
        {
            "enabled": enabled,
            "public_key": current_app.config.get("MODEMPAY_PUBLIC_KEY", "") if enabled else "",
            "instant_methods": sorted(MODEMPAY_INSTANT_METHODS),
            "countries": sorted(MODEMPAY_COUNTRIES),
        }
    )


@payment_bp.route("/modempay/session", methods=["POST"])
@token_required
def modempay_session():
    """Start Wave / AfriMoney checkout via Modem Pay."""
    if not is_configured():
        return jsonify({"error": "Modem Pay is not configured on the server"}), 503

    user = g.current_user
    if user.country_code.upper() not in MODEMPAY_COUNTRIES:
        return jsonify({"error": "Modem Pay is only available in The Gambia"}), 400

    data = request.get_json() or {}
    class_type = data.get("class_type") or user.class_type or "group"
    method = data.get("payment_method", "")
    if method not in MODEMPAY_INSTANT_METHODS:
        return jsonify({"error": "Invalid instant payment method"}), 400

    if user.class_type != class_type:
        user.class_type = class_type

    payment = _get_or_create_pending_payment(user, class_type, method)
    if (payment.amount_local or 0) <= 0.01:
        return jsonify(
            {"error": "Nothing to pay — apply a full coupon or complete checkout first."}
        ), 400

    amount_gmd = int(round(payment.amount_local))
    price = {"currency": payment.currency or "GMD", "local": payment.amount_local}

    payment.payment_channel = "modempay"
    db.session.flush()

    frontend = current_app.config["FRONTEND_URL"]
    reference = f"academy-{payment.id}"
    return_url = (
        f"{frontend}/payment-success.html"
        f"?payment_id={payment.id}&reference={reference}&class_type={class_type}"
    )
    cancel_url = f"{frontend}/payment.html?type={class_type}"

    try:
        checkout = create_checkout_payment_link(
            amount_gmd,
            reference=reference,
            customer_name=user.full_name,
            customer_email=user.email,
            customer_phone=user.phone,
            return_url=return_url,
            cancel_url=cancel_url,
            metadata={
                "payment_id": payment.id,
                "user_id": user.id,
                "class_type": class_type,
                "payment_method": method,
                "source": "buxin-academy",
            },
        )
    except ModemPayError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 502

    payment.modem_intent_id = checkout.get("intent_id")
    db.session.commit()

    return jsonify(
        {
            "payment_id": payment.id,
            "amount": amount_gmd,
            "currency": price["currency"],
            "public_key": current_app.config["MODEMPAY_PUBLIC_KEY"],
            "payment_url": checkout["payment_url"],
            "class_type": class_type,
            "payment_method": method,
        }
    )


@payment_bp.route("/modempay/verify", methods=["POST"])
@token_required
def modempay_verify():
    """Verify Modem Pay transaction after checkout modal; unlock student immediately."""
    if not is_configured():
        return jsonify({"error": "Modem Pay is not configured"}), 503

    data = request.get_json() or {}
    transaction_id = data.get("transaction_id") or data.get("id")
    payment_id = data.get("payment_id")
    client_txn = data.get("transaction")
    if not transaction_id or not payment_id:
        return jsonify({"error": "transaction_id and payment_id are required"}), 400

    payment = db.session.get(Payment, int(payment_id))
    if not payment or payment.user_id != g.current_user.id:
        return jsonify({"error": "Payment not found"}), 404

    if payment.status == "approved":
        return jsonify(
            {
                "payment": payment.to_dict(),
                "user": payment.user.to_dict(),
                "message": "Payment already approved.",
            }
        )

    txn = None
    try:
        txn = retrieve_transaction(transaction_id)
    except ModemPayError as exc:
        current_app.logger.warning(
            "Modem Pay retrieve failed for %s: %s", transaction_id, exc
        )
        if isinstance(client_txn, dict) and _client_transaction_ok(
            client_txn, payment, str(transaction_id)
        ):
            txn = client_txn
        else:
            return jsonify(
                {
                    "error": (
                        "Could not verify payment with Modem Pay yet. "
                        "If you completed payment, wait a moment and refresh — "
                        "or contact support with your transaction reference."
                    )
                }
            ), 502

    try:
        user = _complete_modempay_payment(payment, str(transaction_id), txn)
        return jsonify(
            {
                "payment": payment.to_dict(),
                "user": user.to_dict(),
                "message": "Payment successful! Your account is now active.",
            }
        )
    except ModemPayError as exc:
        return jsonify({"error": str(exc)}), 400


@payment_bp.route("/modempay/webhook", methods=["POST"])
def modempay_webhook():
    """Modem Pay charge.succeeded → auto-approve student."""
    raw = request.get_data()
    signature = request.headers.get("x-modem-signature", "")
    event = parse_webhook_event(raw, signature)
    if not event:
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event.get("event", "")
    payload = event.get("payload") or {}
    if event_type != "charge.succeeded":
        return jsonify({"received": True}), 200

    metadata = payload.get("metadata") or {}
    payment_id = metadata.get("payment_id")
    transaction_id = payload.get("id")
    if not payment_id or not transaction_id:
        return jsonify({"received": True}), 200

    payment = db.session.get(Payment, int(payment_id))
    if not payment:
        return jsonify({"received": True}), 200

    try:
        _complete_modempay_payment(payment, transaction_id, payload)
    except ModemPayError as exc:
        current_app.logger.warning("Modem Pay webhook: %s", exc)

    return jsonify({"received": True}), 200


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
    user = _activate_student_payment(
        payment,
        admin_id=g.current_user.id,
        details=f"Payment #{payment_id} approved",
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
    if payment.coupon_id:
        coupon = db.session.get(Coupon, payment.coupon_id)
        if coupon and not coupon.is_used:
            if payment.original_amount_local is not None:
                payment.amount_local = payment.original_amount_local
                payment.amount_usd = payment.original_amount_usd or payment.amount_usd
            payment.coupon_id = None
            payment.discount_percent = None
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
