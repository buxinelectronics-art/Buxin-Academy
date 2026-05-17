from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.orm import joinedload

from middlewares.auth import active_student_required, admin_required, token_required
from models import db
from models.community import (
    Comment,
    CommunityPost,
    PostLike,
    parse_post_image_urls,
    serialize_post_image_urls,
)
from services.community_media import extract_youtube_id

community_bp = Blueprint("community", __name__, url_prefix="/api/community")
MAX_POST_IMAGES = 5


def _post_has_body(content: str, image_urls: list, youtube_id: str | None) -> bool:
    if image_urls:
        return True
    if youtube_id:
        return True
    return bool(content and content not in ("📷",))


def _emit(event, payload):
    current_app.extensions["socketio"].emit(event, payload, room="community")


def _post_response(post, uid=None, include_comments=True):
    return post.to_dict(uid, include_comments=include_comments)


def _can_manage_post(post):
    user = g.current_user
    return user.role == "admin" or post.user_id == user.id


def _upload_image_file(file):
    from services.cloudinary_service import upload_image

    return upload_image(file, folder="buxinev/community")["url"]


def _apply_images_upload(data, files=None, legacy_file=None):
    urls = []
    upload_files = []
    if files:
        upload_files.extend([f for f in files if f and f.filename])
    if legacy_file and legacy_file.filename:
        upload_files.append(legacy_file)
    upload_files = upload_files[:MAX_POST_IMAGES]

    for file in upload_files:
        try:
            urls.append(_upload_image_file(file))
        except Exception as exc:
            current_app.logger.warning("Community file upload failed: %s", exc)
            raise

    if not urls and data.get("image_base64"):
        try:
            from services.cloudinary_service import upload_image

            urls.append(upload_image(data["image_base64"], folder="buxinev/community")["url"])
        except Exception as exc:
            current_app.logger.warning("Community image upload failed: %s", exc)
            raise

    if not urls and data.get("image_url"):
        urls.append(data["image_url"])

    return urls


def _parse_post_payload():
    """JSON body or multipart form (preferred for photos on mobile)."""
    multi = request.files.getlist("images") or []
    file = request.files.get("image")
    if multi or (file and file.filename):
        return {
            "content": (request.form.get("content") or "").strip(),
            "is_pinned": request.form.get("is_pinned") in ("true", "1", "on"),
            "is_announcement": request.form.get("is_announcement") in ("true", "1", "on"),
            "meet_link": request.form.get("meet_link") or None,
            "zoom_link": request.form.get("zoom_link") or None,
            "image_base64": None,
        }, multi, file
    data = request.get_json(silent=True, force=True) or {}
    return data, [], None


@community_bp.route("/posts", methods=["GET"])
@active_student_required
def get_posts():
    posts = (
        CommunityPost.query.options(
            joinedload(CommunityPost.author),
            joinedload(CommunityPost.likes),
            joinedload(CommunityPost.comments),
        )
        .order_by(
            CommunityPost.is_pinned.desc(),
            CommunityPost.created_at.desc(),
        )
        .limit(50)
        .all()
    )
    uid = g.current_user.id
    return jsonify({"posts": [_post_response(p, uid) for p in posts]})


@community_bp.route("/posts", methods=["POST"])
@active_student_required
def create_post():
    try:
        data, upload_files, legacy_file = _parse_post_payload()
    except Exception:
        return jsonify({"error": "Invalid post data"}), 400

    content = (data.get("content") or "").strip()
    try:
        image_urls = _apply_images_upload(data, files=upload_files, legacy_file=legacy_file)
    except Exception:
        return jsonify({"error": "Could not upload image. Try a smaller JPG or PNG."}), 400

    if len(image_urls) > MAX_POST_IMAGES:
        return jsonify({"error": f"You can add up to {MAX_POST_IMAGES} images per post"}), 400

    youtube_id = extract_youtube_id(content)
    if not _post_has_body(content, image_urls, youtube_id):
        return jsonify({"error": "Write a message, paste a YouTube link, or add an image"}), 400

    image_url = image_urls[0] if image_urls else None
    post = CommunityPost(
        user_id=g.current_user.id,
        content=content or ("📷" if image_urls else "🎬"),
        image_url=image_url,
        image_urls=serialize_post_image_urls(image_urls),
        youtube_video_id=youtube_id,
        is_pinned=bool(data.get("is_pinned")) if g.current_user.role == "admin" else False,
        is_announcement=bool(data.get("is_announcement")) if g.current_user.role == "admin" else False,
        meet_link=data.get("meet_link"),
        zoom_link=data.get("zoom_link"),
    )
    db.session.add(post)
    db.session.commit()
    payload = _post_response(post, g.current_user.id)
    _emit("new_post", payload)
    return jsonify({"post": payload}), 201


@community_bp.route("/posts/<int:post_id>", methods=["PATCH"])
@token_required
def update_post(post_id):
    post = db.session.get(CommunityPost, post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404
    if not _can_manage_post(post):
        return jsonify({"error": "Not allowed to edit this post"}), 403

    data = request.get_json() or {}
    if "content" in data:
        post.content = (data.get("content") or "").strip() or post.content
        post.youtube_video_id = extract_youtube_id(post.content)
    if "is_pinned" in data and g.current_user.role == "admin":
        post.is_pinned = bool(data["is_pinned"])
    if "meet_link" in data:
        post.meet_link = data.get("meet_link")
    if "zoom_link" in data:
        post.zoom_link = data.get("zoom_link")
    if data.get("image_base64"):
        urls = _apply_images_upload(data)
        if urls:
            post.image_url = urls[0]
            post.image_urls = serialize_post_image_urls(urls)

    db.session.commit()
    payload = _post_response(post, g.current_user.id)
    _emit("post_updated", payload)
    return jsonify({"post": payload})


@community_bp.route("/posts/<int:post_id>", methods=["DELETE"])
@token_required
def delete_post(post_id):
    post = db.session.get(CommunityPost, post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404
    if not _can_manage_post(post):
        return jsonify({"error": "Not allowed to delete this post"}), 403

    db.session.delete(post)
    db.session.commit()
    _emit("post_deleted", {"id": post_id})
    return jsonify({"message": "Post deleted"})


@community_bp.route("/posts/<int:post_id>/comment", methods=["POST"])
@active_student_required
def add_comment(post_id):
    post = db.session.get(CommunityPost, post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    data = request.get_json() or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Comment cannot be empty"}), 400

    comment = Comment(
        post_id=post_id,
        user_id=g.current_user.id,
        content=content,
    )
    db.session.add(comment)
    db.session.commit()
    payload = comment.to_dict()
    _emit("new_comment", {"post_id": post_id, "comment": payload})
    return jsonify({"comment": payload}), 201


@community_bp.route("/posts/<int:post_id>/comments", methods=["GET"])
@active_student_required
def get_comments(post_id):
    comments = (
        Comment.query.filter_by(post_id=post_id)
        .order_by(Comment.created_at.asc())
        .all()
    )
    return jsonify({"comments": [c.to_dict() for c in comments]})


@community_bp.route("/posts/<int:post_id>/like", methods=["POST"])
@active_student_required
def toggle_like(post_id):
    post = db.session.get(CommunityPost, post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    existing = PostLike.query.filter_by(
        post_id=post_id, user_id=g.current_user.id
    ).first()
    if existing:
        db.session.delete(existing)
        liked = False
    else:
        db.session.add(PostLike(post_id=post_id, user_id=g.current_user.id))
        liked = True
    db.session.commit()
    db.session.refresh(post)
    return jsonify({
        "liked": liked,
        "like_count": len(post.likes),
        "post_id": post_id,
    })


@community_bp.route("/announcements", methods=["POST"])
@admin_required
def create_announcement():
    try:
        data, upload_file = _parse_post_payload()
    except Exception:
        return jsonify({"error": "Invalid announcement data"}), 400

    content = (data.get("content") or "").strip()
    try:
        image_url = _apply_image_upload(data, file=upload_file)
    except Exception:
        return jsonify({"error": "Could not upload image. Try a smaller JPG or PNG."}), 400

    youtube_id = extract_youtube_id(content)
    if not _post_has_body(content, image_url, youtube_id):
        return jsonify({"error": "Message, YouTube link, or image required"}), 400

    post = CommunityPost(
        user_id=g.current_user.id,
        content=content or ("📷" if image_url else "🎬"),
        is_pinned=data.get("is_pinned", True),
        is_announcement=True,
        meet_link=data.get("meet_link"),
        zoom_link=data.get("zoom_link"),
        image_url=image_url,
        youtube_video_id=youtube_id,
    )
    db.session.add(post)
    db.session.commit()
    payload = _post_response(post, g.current_user.id)
    _emit("new_post", payload)
    return jsonify({"post": payload}), 201
