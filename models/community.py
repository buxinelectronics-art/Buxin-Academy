from datetime import datetime

from models import db


class CommunityPost(db.Model):
    __tablename__ = "community_posts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500))
    is_pinned = db.Column(db.Boolean, default=False)
    is_announcement = db.Column(db.Boolean, default=False)
    meet_link = db.Column(db.String(500))
    zoom_link = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    comments = db.relationship("Comment", backref="post", lazy=True, cascade="all, delete-orphan")
    likes = db.relationship("PostLike", backref="post", lazy=True, cascade="all, delete-orphan")

    def to_dict(self, current_user_id=None, include_comments=False):
        like_count = len(self.likes)
        liked = any(l.user_id == current_user_id for l in self.likes) if current_user_id else False
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "author_name": self.author.full_name if self.author else "Unknown",
            "author_role": self.author.role if self.author else "student",
            "author_picture": self.author.profile_picture if self.author else None,
            "content": self.content,
            "image_url": self.image_url,
            "is_pinned": self.is_pinned,
            "is_announcement": self.is_announcement,
            "meet_link": self.meet_link,
            "zoom_link": self.zoom_link,
            "like_count": like_count,
            "liked": liked,
            "comment_count": len(self.comments),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_comments:
            ordered = sorted(self.comments, key=lambda c: c.created_at or datetime.min)
            data["comments"] = [c.to_dict() for c in ordered]
        return data


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("community_posts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("User", backref="comments")

    def to_dict(self):
        return {
            "id": self.id,
            "post_id": self.post_id,
            "user_id": self.user_id,
            "author_name": self.author.full_name if self.author else "Unknown",
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PostLike(db.Model):
    __tablename__ = "post_likes"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("community_posts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("post_id", "user_id", name="unique_post_like"),)
