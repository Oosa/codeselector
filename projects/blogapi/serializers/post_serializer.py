"""Serializers: convert domain objects to/from dicts."""
from datetime import datetime
from typing import Any, Optional
from models.post import Post, Comment, Tag


class SerializationError(Exception):
    pass


class TagSerializer:
    """Serialize/deserialize Tag objects."""

    @staticmethod
    def to_dict(tag: Tag) -> dict:
        return {
            "id": tag.tag_id,
            "name": tag.name,
            "slug": tag.slug,
            "description": tag.description,
        }

    @staticmethod
    def from_dict(data: dict) -> Tag:
        if "name" not in data:
            raise SerializationError("Tag requires 'name'")
        return Tag(
            tag_id=data.get("id", 0),
            name=data["name"],
            slug=data.get("slug", ""),
            description=data.get("description", ""),
        )

    @classmethod
    def many_to_dict(cls, tags: list[Tag]) -> list[dict]:
        return [cls.to_dict(t) for t in tags]


class CommentSerializer:
    """Serialize/deserialize Comment objects."""

    @staticmethod
    def to_dict(comment: Comment) -> dict:
        return {
            "id": comment.comment_id,
            "post_id": comment.post_id,
            "author_name": comment.author_name,
            "author_email": comment.author_email,
            "body": comment.body,
            "created_at": comment.created_at.isoformat(),
            "is_approved": comment.is_approved,
            "parent_id": comment.parent_id,
        }

    @staticmethod
    def from_dict(data: dict) -> Comment:
        required = ("comment_id", "post_id", "author_name", "author_email", "body")
        for field in required:
            if field not in data:
                raise SerializationError(f"Comment requires '{field}'")
        return Comment(
            comment_id=data["comment_id"],
            post_id=data["post_id"],
            author_name=data["author_name"],
            author_email=data["author_email"],
            body=data["body"],
            created_at=datetime.fromisoformat(data.get("created_at", datetime.utcnow().isoformat())),
            is_approved=data.get("is_approved", False),
            parent_id=data.get("parent_id"),
        )


class PostSerializer:
    """Full post serialization with nested tags and comments."""

    def __init__(self, include_content: bool = True, include_comments: bool = False):
        self.include_content = include_content
        self.include_comments = include_comments

    def to_dict(self, post: Post) -> dict:
        data: dict[str, Any] = {
            "id": post.post_id,
            "title": post.title,
            "slug": post.slug,
            "author_id": post.author_id,
            "status": post.status,
            "excerpt": post.auto_excerpt(),
            "read_time": post.read_time_minutes(),
            "word_count": post.word_count(),
            "tags": TagSerializer.many_to_dict(post.tags),
            "created_at": post.created_at.isoformat(),
            "updated_at": post.updated_at.isoformat(),
            "published_at": post.published_at.isoformat() if post.published_at else None,
        }
        if self.include_content:
            data["content"] = post.content
        if self.include_comments:
            data["comments"] = [
                CommentSerializer.to_dict(c) for c in post.approved_comments()
            ]
        return data

    def from_dict(self, data: dict) -> Post:
        if "title" not in data:
            raise SerializationError("Post requires 'title'")
        post = Post(
            post_id=data.get("id", 0),
            title=data["title"],
            author_id=data.get("author_id", 0),
            content=data.get("content", ""),
            status=data.get("status", "draft"),
        )
        for tag_data in data.get("tags", []):
            post.add_tag(TagSerializer.from_dict(tag_data))
        return post

    def many_to_dict(self, posts: list[Post]) -> list[dict]:
        return [self.to_dict(p) for p in posts]

    @staticmethod
    def summary(post: Post) -> dict:
        """Minimal representation for list views."""
        return {
            "id": post.post_id,
            "title": post.title,
            "slug": post.slug,
            "excerpt": post.auto_excerpt(),
            "tags": [t.name for t in post.tags],
        }
