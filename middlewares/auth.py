from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from models import db
from models.user import User


def create_token(user_id: int, role: str) -> str:
    from datetime import datetime, timedelta

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow()
        + timedelta(hours=current_app.config["JWT_EXPIRY_HOURS"]),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def decode_token(token: str):
    return jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authentication required"}), 401
        try:
            token = auth_header.split(" ", 1)[1]
            payload = decode_token(token)
            try:
                user_id = int(payload["sub"])
            except (KeyError, TypeError, ValueError):
                return jsonify({"error": "Invalid token"}), 401
            user = db.session.get(User, user_id)
            if not user:
                return jsonify({"error": "User not found"}), 401
            g.current_user = user
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        if g.current_user.role != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)

    return decorated


def active_student_required(f):
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        from services.subscription_service import has_app_access, sync_subscription_status

        user = g.current_user
        if user.role == "admin":
            return f(*args, **kwargs)
        sync_subscription_status(user)
        if user.status == "pending":
            return jsonify({"error": "Account not yet approved", "status": user.status}), 403
        if not has_app_access(user):
            return jsonify(
                {
                    "error": (
                        "Your class access period has ended. Renew with payment "
                        "or a new coupon to continue."
                    ),
                    "status": user.status,
                    "subscription_expired": True,
                    "needs_renewal": True,
                }
            ), 403
        return f(*args, **kwargs)

    return decorated
