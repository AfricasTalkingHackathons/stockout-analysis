"""Small in-process sliding-window rate limiter.

Suitable for a single instance. For horizontally scaled deployments, replace with a shared
store (e.g. Redis) — documented in the README."""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _dep(bucket: str, sensitive: bool):
    def dependency(request: Request) -> None:
        s = get_settings()
        limit = s.rate_limit_sensitive_per_minute if sensitive else s.rate_limit_public_per_minute
        if not limiter.check(f"{bucket}:{client_ip(request)}", limit):
            raise HTTPException(status_code=429, detail="Too many requests. Please wait and try again.")

    return dependency


def public_limit(bucket: str):
    return _dep(bucket, sensitive=False)


def sensitive_limit(bucket: str):
    return _dep(bucket, sensitive=True)
