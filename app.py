import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify
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

    Limiter(
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
    app.register_blueprint(schedule_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(class_bp)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "platform": "Buxin Academy"})

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
            _seed_defaults()
        except Exception as exc:
            app.logger.error("Database init on startup: %s", exc)

    return app


def _seed_defaults():
    from models.schedule import Schedule
    from models.user import User

    if not Schedule.query.first():
        defaults = [
            ("Monday", "6:00 PM"),
            ("Tuesday", "8:00 PM"),
            ("Wednesday", "5:00 PM"),
            ("Thursday", "7:00 PM"),
            ("Friday", "4:00 PM"),
            ("Saturday", "10:00 AM"),
        ]
        for day, time in defaults:
            db.session.add(Schedule(day_of_week=day, time_slot=time))
        db.session.commit()

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

