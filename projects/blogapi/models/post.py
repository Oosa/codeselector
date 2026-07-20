"""Blog post domain models."""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_ARCHIVED = "archived"

MAX_TITLE_LENGTH = 200
MAX_EXCERPT_LENGTH = 500
MIN_READ_SPEED_WPM = 200


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def estimate_read_time(content: str) -> int:
    """Return estimated reading time in minutes."""
    word_count = len(content.split())
    minutes = max(1, round(word_count / MIN_READ_SPEED_WPM))
    return minutes


@dataclass
class Tag:
    tag_id: int
    name: str
    slug: str
    description: str = ""

    @classmethod
    def from_name(cls, tag_id: int, name: str) -> "Tag":
        return cls(tag_id=tag_id, name=name, slug=slugify(name))


@dataclass
class Comment:
    comment_id: int
    post_id: int
    author_name: str
    author_email: str
    body: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_approved: bool = False
    parent_id: Optional[int] = None

    def approve(self) -> None:
        self.is_approved = True

    def is_reply(self) -> bool:
        return self.parent_id is not None


class Post:
    """A blog post."""

    def __init__(self, post_id: int, title: str, author_id: int,
                 content: str = "", status: str = STATUS_DRAFT):
        self.post_id = post_id
        self.title = title
        self.author_id = author_id
        self.content = content
        self.status = status
        self.slug = slugify(title)
        self.excerpt: str = ""
        self.tags: list[Tag] = []
        self.comments: list[Comment] = []
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.published_at: Optional[datetime] = None
        self._view_count: int = 0
        self._like_count: int = 0

    def publish(self) -> None:
        """Move post to published status."""
        if self.status == STATUS_ARCHIVED:
            raise ValueError("Cannot publish an archived post")
        self.status = STATUS_PUBLISHED
        self.published_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def archive(self) -> None:
        self.status = STATUS_ARCHIVED
        self.updated_at = datetime.utcnow()

    def unpublish(self) -> None:
        self.status = STATUS_DRAFT
        self.published_at = None
        self.updated_at = datetime.utcnow()

    def update_content(self, new_content: str) -> None:
        self.content = new_content
        self.updated_at = datetime.utcnow()

    def update_title(self, new_title: str) -> None:
        if len(new_title) > MAX_TITLE_LENGTH:
            raise ValueError(f"Title too long (max {MAX_TITLE_LENGTH} chars)")
        self.title = new_title
        self.slug = slugify(new_title)
        self.updated_at = datetime.utcnow()

    def auto_excerpt(self) -> str:
        """Generate excerpt from first 500 chars of content."""
        plain = re.sub(r"<[^>]+>", "", self.content)
        return plain[:MAX_EXCERPT_LENGTH].strip()

    def add_tag(self, tag: Tag) -> None:
        if not any(t.tag_id == tag.tag_id for t in self.tags):
            self.tags.append(tag)

    def remove_tag(self, tag_id: int) -> bool:
        original = len(self.tags)
        self.tags = [t for t in self.tags if t.tag_id != tag_id]
        return len(self.tags) < original

    def add_comment(self, comment: Comment) -> None:
        self.comments.append(comment)

    def approved_comments(self) -> list[Comment]:
        return [c for c in self.comments if c.is_approved]

    def increment_views(self) -> int:
        self._view_count += 1
        return self._view_count

    def like(self) -> int:
        self._like_count += 1
        return self._like_count

    def read_time_minutes(self) -> int:
        return estimate_read_time(self.content)

    def is_published(self) -> bool:
        return self.status == STATUS_PUBLISHED

    def word_count(self) -> int:
        return len(self.content.split())

    def __repr__(self) -> str:
        return f"Post(id={self.post_id}, slug={self.slug!r}, status={self.status!r})"
