"""View layer for blog post endpoints."""
import json
import logging
from typing import Optional

from models.post import Post, Comment, Tag, STATUS_PUBLISHED

logger = logging.getLogger(__name__)

POSTS_PER_PAGE = 10


def require_auth(handler):
    """Decorator: reject unauthenticated requests."""
    def wrapper(self, request, *args, **kwargs):
        if not request.get("user"):
            return {"status": 401, "body": json.dumps({"error": "Authentication required"})}
        return handler(self, request, *args, **kwargs)
    wrapper.__name__ = handler.__name__
    return wrapper


def require_author_or_admin(handler):
    """Decorator: allow only post author or admin."""
    def wrapper(self, request, post_id, *args, **kwargs):
        post = self.post_repo.get(post_id)
        user = request.get("user")
        if not post:
            return {"status": 404, "body": json.dumps({"error": "Not found"})}
        if user.get("id") != post.author_id and not user.get("is_admin"):
            return {"status": 403, "body": json.dumps({"error": "Forbidden"})}
        return handler(self, request, post_id, *args, **kwargs)
    wrapper.__name__ = handler.__name__
    return wrapper


class PostListView:
    """GET /posts — paginated list of published posts."""

    def __init__(self, post_repo, tag_repo):
        self.post_repo = post_repo
        self.tag_repo = tag_repo

    def get(self, request: dict) -> dict:
        """Return paginated list of published posts."""
        params = request.get("query", {})
        page = int(params.get("page", 1))
        tag_slug = params.get("tag")
        search_query = params.get("q", "").strip()

        posts = self.post_repo.find_published()
        if tag_slug:
            tag = self.tag_repo.find_by_slug(tag_slug)
            if tag:
                posts = [p for p in posts if any(t.tag_id == tag.tag_id for t in p.tags)]
        if search_query:
            posts = self._search(posts, search_query)

        start = (page - 1) * POSTS_PER_PAGE
        page_posts = posts[start: start + POSTS_PER_PAGE]

        return {
            "status": 200,
            "body": json.dumps({
                "posts": [self._serialise_post(p) for p in page_posts],
                "total": len(posts),
                "page": page,
            }),
        }

    def _search(self, posts: list[Post], query: str) -> list[Post]:
        """Filter posts by title/content keyword."""
        q = query.lower()
        return [p for p in posts if q in p.title.lower() or q in p.content.lower()]

    def _serialise_post(self, post: Post) -> dict:
        return {
            "id": post.post_id,
            "title": post.title,
            "slug": post.slug,
            "excerpt": post.auto_excerpt(),
            "read_time": post.read_time_minutes(),
            "tags": [t.name for t in post.tags],
        }


class PostDetailView:
    """GET /posts/{slug}"""

    def __init__(self, post_repo):
        self.post_repo = post_repo

    def get(self, request: dict, slug: str) -> dict:
        """Return full post detail."""
        post = self.post_repo.find_by_slug(slug)
        if not post or not post.is_published():
            return {"status": 404, "body": json.dumps({"error": "Post not found"})}
        post.increment_views()
        return {
            "status": 200,
            "body": json.dumps({
                "id": post.post_id,
                "title": post.title,
                "content": post.content,
                "slug": post.slug,
                "author_id": post.author_id,
                "comments": [
                    {"id": c.comment_id, "body": c.body, "author": c.author_name}
                    for c in post.approved_comments()
                ],
                "tags": [t.name for t in post.tags],
            }),
        }


class PostAdminView:
    """CRUD admin view for managing posts."""

    def __init__(self, post_repo, tag_repo):
        self.post_repo = post_repo
        self.tag_repo = tag_repo
        self._draft_cache: dict[int, Post] = {}

    @require_auth
    def create(self, request: dict) -> dict:
        """POST /admin/posts"""
        body = json.loads(request.get("body", "{}"))
        user = request["user"]
        post_id = self.post_repo.next_id()
        post = Post(
            post_id=post_id,
            title=body.get("title", ""),
            author_id=user["id"],
            content=body.get("content", ""),
        )
        if body.get("tags"):
            self._attach_tags(post, body["tags"])
        self.post_repo.save(post)
        self._draft_cache[post_id] = post
        logger.info("Post %s created by user %s", post_id, user["id"])
        return {"status": 201, "body": json.dumps({"post_id": post_id})}

    @require_auth
    @require_author_or_admin
    def update(self, request: dict, post_id: int) -> dict:
        """PATCH /admin/posts/{id}"""
        post = self.post_repo.get(post_id)
        body = json.loads(request.get("body", "{}"))
        if "title" in body:
            post.update_title(body["title"])
        if "content" in body:
            post.update_content(body["content"])
        if "tags" in body:
            post.tags = []
            self._attach_tags(post, body["tags"])
        self.post_repo.save(post)
        return {"status": 200, "body": json.dumps({"post_id": post_id})}

    @require_auth
    @require_author_or_admin
    def publish_post(self, request: dict, post_id: int) -> dict:
        """POST /admin/posts/{id}/publish"""
        post = self.post_repo.get(post_id)
        post.publish()
        self.post_repo.save(post)
        return {"status": 200, "body": json.dumps({"status": post.status})}

    @require_auth
    @require_author_or_admin
    def delete(self, request: dict, post_id: int) -> dict:
        """DELETE /admin/posts/{id}"""
        self.post_repo.delete(post_id)
        self._draft_cache.pop(post_id, None)
        return {"status": 204, "body": ""}

    def _attach_tags(self, post: Post, tag_names: list[str]) -> None:
        for name in tag_names:
            tag = self.tag_repo.find_by_name(name) or self.tag_repo.create(name)
            post.add_tag(tag)


class CommentView:
    """Handles comment submission and moderation."""

    def __init__(self, post_repo, mailer):
        self.post_repo = post_repo
        self.mailer = mailer

    def submit(self, request: dict, post_id: int) -> dict:
        """POST /posts/{id}/comments"""
        post = self.post_repo.get(post_id)
        if not post or not post.is_published():
            return {"status": 404, "body": json.dumps({"error": "Post not found"})}
        body = json.loads(request.get("body", "{}"))
        comment = Comment(
            comment_id=len(post.comments) + 1,
            post_id=post_id,
            author_name=body.get("name", "Anonymous"),
            author_email=body.get("email", ""),
            body=body.get("body", ""),
        )
        post.add_comment(comment)
        self.post_repo.save(post)
        self.mailer.notify_new_comment(comment)
        return {"status": 201, "body": json.dumps({"comment_id": comment.comment_id})}

    @require_auth
    def approve(self, request: dict, comment_id: int) -> dict:
        """POST /admin/comments/{id}/approve"""
        user = request["user"]
        if not user.get("is_admin"):
            return {"status": 403, "body": json.dumps({"error": "Forbidden"})}
        post = self.post_repo.find_by_comment_id(comment_id)
        if not post:
            return {"status": 404, "body": json.dumps({"error": "Comment not found"})}
        for c in post.comments:
            if c.comment_id == comment_id:
                c.approve()
                break
        self.post_repo.save(post)
        return {"status": 200, "body": json.dumps({"approved": True})}


class AsyncPostSearch:
    """Async post search for large datasets."""

    def __init__(self, post_repo, index):
        self.post_repo = post_repo
        self.index = index

    async def search_posts(self, query: str, page: int = 1) -> dict:
        """Full-text async search over the post index."""
        results = await self.index.search(query, limit=10, offset=(page - 1) * 10)
        posts = [self.post_repo.get(r["id"]) for r in results]
        return {"query": query, "page": page, "results": [p.title for p in posts if p]}

    async def rebuild_index(self) -> int:
        """Re-index all published posts. Returns count of indexed posts."""
        posts = self.post_repo.find_published()
        count = 0
        for post in posts:
            await self.index.upsert({
                "id": post.post_id,
                "title": post.title,
                "content": post.content,
                "tags": [t.name for t in post.tags],
            })
            count += 1
        return count
