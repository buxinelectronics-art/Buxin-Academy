import cloudinary
import cloudinary.uploader
from flask import current_app


def init_cloudinary(app):
    cloudinary.config(
        cloud_name=app.config["CLOUDINARY_CLOUD_NAME"],
        api_key=app.config["CLOUDINARY_API_KEY"],
        api_secret=app.config["CLOUDINARY_API_SECRET"],
        secure=True,
    )


def upload_image(file_data, folder="buxinev"):
    if not current_app.config.get("CLOUDINARY_CLOUD_NAME"):
        return {
            "url": "https://via.placeholder.com/400x300?text=Receipt+Uploaded",
            "public_id": "placeholder",
        }
    result = cloudinary.uploader.upload(
        file_data,
        folder=folder,
        resource_type="image",
        transformation=[{"quality": "auto", "fetch_format": "auto"}],
    )
    return {"url": result["secure_url"], "public_id": result["public_id"]}
