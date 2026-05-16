import io
import logging

import cloudinary
import cloudinary.uploader
from flask import current_app

logger = logging.getLogger(__name__)

PLACEHOLDER_RECEIPT = "https://via.placeholder.com/400x300?text=Receipt+On+File"


def init_cloudinary(app):
    if not app.config.get("CLOUDINARY_CLOUD_NAME"):
        return
    cloudinary.config(
        cloud_name=app.config["CLOUDINARY_CLOUD_NAME"],
        api_key=app.config["CLOUDINARY_API_KEY"],
        api_secret=app.config["CLOUDINARY_API_SECRET"],
        secure=True,
    )


def _cloudinary_configured() -> bool:
    cfg = current_app.config
    return bool(
        cfg.get("CLOUDINARY_CLOUD_NAME")
        and cfg.get("CLOUDINARY_API_KEY")
        and cfg.get("CLOUDINARY_API_SECRET")
    )


def upload_image(file_data, folder="buxinev"):
    if not _cloudinary_configured():
        return {"url": PLACEHOLDER_RECEIPT, "public_id": "placeholder"}

    upload_payload = file_data
    if hasattr(file_data, "read"):
        upload_payload = io.BytesIO(file_data.read())

    opts = {
        "folder": folder,
        "resource_type": "image",
        "transformation": [{"quality": "auto", "fetch_format": "auto"}],
    }
    try:
        if isinstance(upload_payload, str) and upload_payload.startswith("data:"):
            result = cloudinary.uploader.upload(upload_payload, **opts)
        else:
            result = cloudinary.uploader.upload(upload_payload, **opts)
        return {"url": result["secure_url"], "public_id": result["public_id"]}
    except Exception as exc:
        logger.exception("Cloudinary upload failed: %s", exc)
        raise
