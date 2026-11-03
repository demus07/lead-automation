"""Fixed-window rate limiting backed by Redis, with an in-process fallback when Redis is unavailable."""
from __future__ import annotations

import logging
import threading
import time

import redis

from app.core.config import get_settings

log = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._redis_failed_at = 0.0
        self._local: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def _client(self) -> redis.Redis | None:
        if self._redis is not None:
            return self._redis
        if time.time() - self._redis_failed_at < 30:
            return None
        try:
            r = redis.Redis.from_url(get_settings().redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
            r.ping()
            self._redis = r
        except Exception:  # pragma: no cover - depends on infra
            self._redis_failed_at = time.time()
            self._redis = None
        return self._redis

    def hit(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        """Returns (allowed, remaining)."""
        bucket = int(time.time() // window)
        full = f"rl:{key}:{bucket}"
        r = self._client()
        if r is not None:
            try:
                pipe = r.pipeline()
                pipe.incr(full)
                pipe.expire(full, window + 1)
                count = int(pipe.execute()[0])
                return count <= limit, max(0, limit - count)
            except Exception:  # pragma: no cover
                self._redis = None
                self._redis_failed_at = time.time()
        with self._lock:
            b, c = self._local.get(key, (bucket, 0))
            if b != bucket:
                b, c = bucket, 0
            c += 1
            self._local[key] = (b, c)
            if len(self._local) > 50_000:
                self._local.clear()
            return c <= limit, max(0, limit - c)


limiter = RateLimiter()
