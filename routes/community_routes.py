from flask import Blueprint, g, jsonify, request

from middlewares.auth import active_student_required, admin_required, token_required
from models import db
from models.community import Comment, CommunityPost, PostLike

community_bp = Blueprint("community", __name__, url_prefix="/api/community")


@community_bp.route("/posts", methods=["GET"])
@active_student_required
def get_posts():
    posts = (
        CommunityPost.query.order_by(
            CommunityPost.is_pinned.desc(),
            CommunityPost.created_at.desc(),
        )
        .limit(50)
        .all()
    )
    uid = g.current_user.id
    return jsonify({"posts": [p.to_dict(uid) for p in posts]})


@community_bp.route("/posts", methods=["POST"])
@active_student_required
def create_post():
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()
    image_url = data.get("image_url")

    if data.get("image_base64"):
        try:
            from services.cloudinary_service import upload_image

            result = upload_image(data["image_base64"], folder="buxinev/community")
            image_url = result["url"]
        except Exception as exc:
            from flask import current_app

            current_app.logger.warning("Community image upload failed: %s", exc)

    if not content and not image_url:
        return jsonify({"error": "Write a message or add an image"}), 400

    post = CommunityPost(
        user_id=g.current_user.id,
        content=content or "📷",
        image_url=image_url,
    )
    db.session.add(post)
    db.session.commit()
    from flask import current_app

    current_app.extensions["socketio"].emit("new_post", post.to_dict(g.current_user.id), room="community")
    return jsonify({"post": post.to_dict(g.current_user.id)}), 201


@community_bp.route("/posts/<int:post_id>/comment", methods=["POST"])
@active_student_required
def add_comment(post_id):
    data = request.get_json() or {}
    comment = Comment(
        post_id=post_id,
        user_id=g.current_user.id,
        content=data.get("content", ""),
    )
    db.session.add(comment)
    db.session.commit()
    from flask import current_app

    current_app.extensions["socketio"].emit("new_comment", comment.to_dict(), room="community")
    return jsonify({"comment": comment.to_dict()}), 201


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
    post = db.session.get(CommunityPost, post_id)
    return jsonify({"liked": liked, "like_count": len(post.likes)})


@community_bp.route("/announcements", methods=["POST"])
@admin_required
def create_announcement():
    data = request.get_json() or {}
    post = CommunityPost(
        user_id=g.current_user.id,
        content=data.get("content", ""),
        is_pinned=data.get("is_pinned", True),
        is_announcement=True,
        meet_link=data.get("meet_link"),
        zoom_link=data.get("zoom_link"),
        image_url=data.get("image_url"),
    )
    db.session.add(post)
    db.session.commit()
    from flask import current_app

    current_app.extensions["socketio"].emit("new_post", post.to_dict(), room="community")
    return jsonify({"post": post.to_dict()}), 201
