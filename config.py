import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "buxinev-dev-secret-change-in-production")
    JWT_SECRET = os.getenv("JWT_SECRET", SECRET_KEY)
    JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "168"))

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///buxinev.db",
    )
    if SQLALCHEMY_DATABASE_URI:
        if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
            SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
                "postgres://", "postgresql://", 1
            )
        if SQLALCHEMY_DATABASE_URI.startswith("postgresql://"):
            SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
    # Optional: CLOUDINARY_URL=cloudinary://key:secret@cloud_name
    _cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    if _cloudinary_url and not CLOUDINARY_CLOUD_NAME:
        import re
        m = re.match(r"cloudinary://([^:]+):([^@]+)@(.+)", _cloudinary_url)
        if m:
            CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, CLOUDINARY_CLOUD_NAME = m.groups()

    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5500,http://127.0.0.1:5500,"
            "https://buxinelectronics-art.github.io,"
            "http://academy.techbuxin.com,https://academy.techbuxin.com",
        ).split(",")
        if o.strip()
    ]

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB (JSON base64 receipts)

    BASE_GROUP_PRICE_USD = 5.0
    BASE_INDIVIDUAL_PRICE_USD = 100.0
