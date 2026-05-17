from flask import Blueprint, g, jsonify, request

from middlewares.auth import create_token, token_required
from models import db
from models.notification import Notification
from models.user import User
from services.cloudinary_service import upload_image
from services.subscription_service import is_subscription_active, sync_subscription_status

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _parse_country_fields(data):
    code = str(data.get("country_code") or "").upper().strip()
    if not code:
        return None, None, (jsonify({"error": "country_code is required"}), 400)
    name = str(data.get("country_name") or "").strip()
    if code == "OTHER":
        if len(name) < 2:
            return None, None, (
                jsonify({"error": "Please enter your country name"}),
                400,
            )
        return code, name[:80], None
    return code, None, None


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    required = ["email", "password", "full_name", "country_code", "class_type"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    country_code, country_name, country_err = _parse_country_fields(data)
    if country_err:
        return country_err

    email_norm = data["email"].lower().strip()
    existing = User.query.filter_by(email=email_norm).first()

    if existing:
        if existing.role != "student":
            return jsonify({"error": "Email already registered"}), 409
        sync_subscription_status(existing, commit=False)
        if existing.status == "active" and is_subscription_active(existing):
            return jsonify({"error": "Email already registered"}), 409
        if existing.status in ("active", "expired"):
            return jsonify(
                {
                    "error": "Account already exists. Log in to renew your monthly payment.",
                }
            ), 409
        existing.full_name = data["full_name"].strip()
        existing.phone = data.get("phone", "") or ""
        existing.country_code = country_code
        existing.country_name = country_name
        existing.city = data.get("city", "") or ""
        existing.class_type = data["class_type"]
        existing.experience_level = data.get("experience_level", "") or ""
        existing.learning_goals = data.get("learning_goals", "") or ""
        existing.status = "pending"
        existing.set_password(data["password"])

        if data.get("profile_picture_base64"):
            try:
                result = upload_image(
                    data["profile_picture_base64"], folder="buxinev/profiles"
                )
                existing.profile_picture = result["url"]
            except Exception:
                pass

        db.session.commit()
        token = create_token(existing.id, existing.role)
        return jsonify({"token": token, "user": existing.to_dict()}), 201

    user = User(
        email=email_norm,
        full_name=data["full_name"].strip(),
        phone=data.get("phone", ""),
        country_code=country_code,
        country_name=country_name,
        city=data.get("city", ""),
        class_type=data["class_type"],
        experience_level=data.get("experience_level", ""),
        learning_goals=data.get("learning_goals", ""),
        status="pending",
        role="student",
    )
    user.set_password(data["password"])

    if data.get("profile_picture_base64"):
        try:
            result = upload_image(data["profile_picture_base64"], folder="buxinev/profiles")
            user.profile_picture = result["url"]
        except Exception:
            pass

    db.session.add(user)
    db.session.commit()

    token = create_token(user.id, user.role)
    return jsonify({"token": token, "user": user.to_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = (data.get("email") or "").lower().strip()
    password = data.get("password", "")

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401

    if user.role == "student":
        sync_subscription_status(user)
    token = create_token(user.id, user.role)
    return jsonify({"token": token, "user": user.to_dict()})


@auth_bp.route("/me", methods=["GET"])
@token_required
def me():
    user = g.current_user
    if user.role == "student":
        sync_subscription_status(user)
    return jsonify({"user": user.to_dict()})


@auth_bp.route("/password-reset-request", methods=["POST"])
def password_reset_request():
    data = request.get_json() or {}
    email = (data.get("email") or "").lower().strip()
    user = User.query.filter_by(email=email).first()
    if user:
        Notification(
            user_id=user.id,
            title="Password Reset",
            message="Contact support at academy@buxinev.com to reset your password.",
        )
        db.session.commit()
    return jsonify({"message": "If the email exists, instructions have been sent."})


@auth_bp.route("/logout", methods=["POST"])
@token_required
def logout():
    return jsonify({"message": "Logged out successfully"})
