"""Rate limiting middleware."""
import time
import logging
from collections import defaultdict
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_RATE = 60       # requests
DEFAULT_WINDOW = 60     # seconds
BURST_MULTIPLIER = 2    # allow short bursts
IP_HEADER = "X-Forwarded-For"


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class TokenBucket:
    """Token-bucket rate limiter for a single key."""

    def __init__(self, rate: int, window: int):
        self.rate = rate
        self.window = window
        self._tokens: float = rate
        self._last_refill: float = time.time()

    def consume(self, tokens: int = 1) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(
            self.rate * BURST_MULTIPLIER,
            self._tokens + elapsed * (self.rate / self.window),
        )
        self._last_refill = now

    def tokens_remaining(self) -> int:
        self._refill()
        return int(self._tokens)

    def retry_after(self) -> int:
        deficit = 1 - self._tokens
        if deficit <= 0:
            return 0
        return int(deficit * self.window / self.rate) + 1


class RateLimiter:
    """Per-IP rate limiter with configurable rules."""

    def __init__(self, rate: int = DEFAULT_RATE, window: int = DEFAULT_WINDOW):
        self.rate = rate
        self.window = window
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(self.rate, self.window)
        )
        self._whitelist: set[str] = set()
        self._blacklist: set[str] = set()

    def check(self, key: str) -> None:
        """Raise RateLimitExceeded if key has exhausted its quota."""
        if key in self._whitelist:
            return
        if key in self._blacklist:
            raise RateLimitExceeded(retry_after=3600)
        bucket = self._buckets[key]
        if not bucket.consume():
            raise RateLimitExceeded(retry_after=bucket.retry_after())

    def whitelist(self, key: str) -> None:
        self._whitelist.add(key)

    def blacklist(self, key: str) -> None:
        self._blacklist.add(key)
        self._buckets.pop(key, None)

    def remaining(self, key: str) -> int:
        if key in self._whitelist:
            return self.rate
        return self._buckets[key].tokens_remaining()

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)

    def _extract_ip(self, request: dict) -> str:
        headers = request.get("headers", {})
        forwarded = headers.get(IP_HEADER, "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return headers.get("REMOTE_ADDR", "unknown")

    def middleware(self, handler: Callable) -> Callable:
        """Wrap an HTTP handler with rate limiting."""
        def wrapped(request: dict, *args, **kwargs) -> dict:
            ip = self._extract_ip(request)
            try:
                self.check(ip)
            except RateLimitExceeded as exc:
                logger.warning("Rate limit exceeded for IP %s", ip)
                return {
                    "status": 429,
                    "headers": {"Retry-After": str(exc.retry_after)},
                    "body": '{"error": "Too many requests"}',
                }
            return handler(request, *args, **kwargs)
        wrapped.__name__ = handler.__name__
        return wrapped


class SlidingWindowLimiter:
    """Sliding window rate limiter (alternative algorithm)."""

    def __init__(self, rate: int = DEFAULT_RATE, window: int = DEFAULT_WINDOW):
        self.rate = rate
        self.window = window
        self._log: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        self._log[key] = [t for t in self._log[key] if t > cutoff]
        if len(self._log[key]) >= self.rate:
            return False
        self._log[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        now = time.time()
        cutoff = now - self.window
        recent = [t for t in self._log[key] if t > cutoff]
        return max(0, self.rate - len(recent))

    def purge_old_keys(self, max_age: Optional[float] = None) -> int:
        """Remove expired keys to free memory. Returns count of purged keys."""
        cutoff = time.time() - (max_age or self.window * 2)
        to_delete = [k for k, ts in self._log.items() if not ts or max(ts) < cutoff]
        for k in to_delete:
            del self._log[k]
        return len(to_delete)
