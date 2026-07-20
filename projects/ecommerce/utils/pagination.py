"""Pagination helpers."""
from dataclasses import dataclass
from typing import Generic, TypeVar, Optional

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass
class PageParams:
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self):
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.page_size < 1 or self.page_size > MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be 1–{MAX_PAGE_SIZE}")

    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def limit(self) -> int:
        return self.page_size


@dataclass
class Page(Generic[T]):
    """A single page of results."""
    items: list[T]
    total: int
    page: int
    page_size: int

    def total_pages(self) -> int:
        if self.total == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    def has_next(self) -> bool:
        return self.page < self.total_pages()

    def has_prev(self) -> bool:
        return self.page > 1

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages(),
            "has_next": self.has_next(),
            "has_prev": self.has_prev(),
        }


def paginate(items: list, params: PageParams) -> Page:
    """Paginate a plain Python list (in-memory pagination)."""
    total = len(items)
    start = params.offset()
    end = start + params.limit()
    return Page(
        items=items[start:end],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


def parse_page_params(query: dict) -> PageParams:
    """Extract and validate PageParams from a query-string dict."""
    try:
        page = int(query.get("page", 1))
        page_size = int(query.get("page_size", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        raise ValueError("page and page_size must be integers")
    return PageParams(page=page, page_size=page_size)
