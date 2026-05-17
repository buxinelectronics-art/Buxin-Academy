import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify
from sqlalchemy import text
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO, emit, join_room

from config import Config
from models import db
from routes.admin_routes import admin_bp
from routes.auth_routes import auth_bp
from routes.class_routes import class_bp
from routes.community_routes import community_bp
from routes.country_routes import country_bp
from routes.notification_routes import notification_bp
from routes.payment_routes import payment_bp
from routes.schedule_routes import schedule_bp
from services.cloudinary_service import init_cloudinary

def _socketio_async_mode():
    """threading works with Render's default `gunicorn app:app`; eventlet needs a custom start command."""
    return os.getenv("SOCKETIO_ASYNC_MODE", "threading")


socketio = SocketIO(cors_allowed_origins="*")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    CORS(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)
    init_cloudinary(app)

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
    )

    socketio.init_app(app, async_mode=_socketio_async_mode(), cors_allowed_origins="*")
    app.extensions["socketio"] = socketio

    app.register_blueprint(auth_bp)
    app.register_blueprint(country_bp)
    app.register_blueprint(payment_bp)
    from routes.payment_routes import modempay_webhook

    limiter.exempt(modempay_webhook)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(class_bp)

    @app.errorhandler(413)
    def request_entity_too_large(_e):
        return jsonify(
            {"error": "Receipt is too large. Use a smaller image or screenshot."}
        ), 413

    @app.route("/api/health")
    @limiter.exempt
    def health():
        return jsonify({"status": "ok", "platform": "Buxin Academy"})

    @app.route("/api/ping")
    @limiter.exempt
    def ping():
        """Instant response so Render starts the process before DB is ready."""
        return jsonify({"status": "ok"})

    @app.route("/api/wake")
    @limiter.exempt
    def wake():
        """SPA calls this on load to wake Render (free tier) and confirm DB with SELECT 1."""
        try:
            n = db.session.execute(text("SELECT 1")).scalar()
            return jsonify({"status": "ok", "db": int(n) if n is not None else None})
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("wake: database ping failed: %s", exc)
            return jsonify({"status": "ok", "db": None}), 200

    @socketio.on("connect")
    def on_connect():
        emit("connected", {"message": "Connected to Buxin Academy"})

    @socketio.on("join")
    def on_join(data):
        room = data.get("room", "community")
        join_room(room)
        emit("joined", {"room": room})

    @socketio.on("join_user")
    def on_join_user(data):
        user_id = data.get("user_id")
        if user_id:
            join_room(f"user_{user_id}")

    with app.app_context():
        try:
            db.create_all()
            _ensure_payment_columns()
            _ensure_community_columns()
            _ensure_user_subscription_column()
            _ensure_user_country_name_column()
            _ensure_user_selected_course_column()
            _ensure_coupon_columns()
            _ensure_academy_settings_table()
            _seed_defaults()
        except Exception as exc:
            app.logger.error("Database init on startup: %s", exc)

    return app


def _ensure_payment_columns():
    """Add Modem Pay columns on existing PostgreSQL deployments."""
    from flask import current_app

    if not db.engine.url.drivername.startswith("postgres"):
        return
    stmts = [
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_channel VARCHAR(20) DEFAULT 'manual'",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS modem_transaction_id VARCHAR(120)",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS modem_intent_id VARCHAR(120)",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS coupon_id INTEGER",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS discount_percent INTEGER",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS original_amount_usd DOUBLE PRECISION",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS original_amount_local DOUBLE PRECISION",
    ]
    for sql in stmts:
        try:
            db.session.execute(text(sql))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            current_app.logger.debug("payment column migration: %s", exc)


def _ensure_user_subscription_column():
    """Add monthly subscription expiry on existing PostgreSQL deployments."""
    from flask import current_app

    if not db.engine.url.drivername.startswith("postgres"):
        return
    try:
        for col in (
            "subscription_started_at TIMESTAMP",
            "subscription_expires_at TIMESTAMP",
        ):
            db.session.execute(
                text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col}")
            )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.debug("user subscription column migration: %s", exc)


def _ensure_user_country_name_column():
    """Custom country label when country_code is OTHER (USD pricing)."""
    from flask import current_app

    if not db.engine.url.drivername.startswith("postgres"):
        return
    try:
        db.session.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS country_name VARCHAR(80)")
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.debug("user country_name column migration: %s", exc)


def _ensure_user_selected_course_column():
    """Individual mentorship track (6-month program)."""
    from flask import current_app

    if not db.engine.url.drivername.startswith("postgres"):
        return
    try:
        db.session.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "selected_course VARCHAR(40)"
            )
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.debug("user selected_course column migration: %s", exc)


def _ensure_coupon_columns():
    """Coupons table + payment discount fields on PostgreSQL."""
    from flask import current_app

    if not db.engine.url.drivername.startswith("postgres"):
        return
    try:
        db.session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS coupons ("
                "id SERIAL PRIMARY KEY, "
                "code VARCHAR(32) UNIQUE NOT NULL, "
                "class_type VARCHAR(20) NOT NULL, "
                "discount_percent INTEGER NOT NULL, "
                "used_by_user_id INTEGER REFERENCES users(id), "
                "used_at TIMESTAMP, "
                "payment_id INTEGER, "
                "created_by_admin_id INTEGER REFERENCES users(id), "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "notes VARCHAR(200))"
            )
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.debug("coupons table migration: %s", exc)


def _ensure_academy_settings_table():
    """Global class-period start (admin Day 1 control)."""
    from flask import current_app

    if not db.engine.url.drivername.startswith("postgres"):
        return
    try:
        db.session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS academy_settings ("
                "id INTEGER PRIMARY KEY, "
                "class_period_started_at TIMESTAMP)"
            )
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.debug("academy_settings migration: %s", exc)


def _ensure_community_columns():
    """Add YouTube video id column on existing PostgreSQL deployments."""
    from flask import current_app

    if not db.engine.url.drivername.startswith("postgres"):
        return
    try:
        db.session.execute(
            text(
                "ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS "
                "youtube_video_id VARCHAR(20)"
            )
        )
        db.session.execute(
            text(
                "ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS "
                "image_urls TEXT"
            )
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.debug("community column migration: %s", exc)


def _seed_defaults():
    from models.user import User
    from services.schedule_slots import sync_ist_schedule_slots

    sync_ist_schedule_slots()

    admin_email = os.getenv("ADMIN_EMAIL", "admin@buxinev.com")
    if not User.query.filter_by(email=admin_email).first():
        admin = User(
            email=admin_email,
            full_name="Buxin Admin",
            country_code="GM",
            role="admin",
            status="active",
            class_type="group",
        )
        admin.set_password(os.getenv("ADMIN_PASSWORD", "BuxinEV@Admin2026"))
        db.session.add(admin)
        db.session.commit()


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")

