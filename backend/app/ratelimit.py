"""
PRAHARI · rate limiting
════════════════════════════════════════════════════════════════════════════
A fixed-window counter in process memory. Adequate for a single instance and
honest about what it is not: with several replicas each keeps its own window,
so a deployment that scales horizontally should put this behind the platform's
own limiter or a shared Redis counter.

Authentication endpoints get a much tighter budget than everything else,
because a login endpoint is where credential stuffing lands.
"""
from __future__ import annotations

import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import Settings

AUTH_PATHS = ("/api/auth/login", "/api/auth/register", "/api/auth/password/reset-request")
WRITE_METHODS = ("POST", "PATCH", "PUT", "DELETE")


class RateLimiter:
    def __init__(self, settings: Settings):
        self.s = settings
        self._buckets: dict[tuple[str, str], tuple[int, float]] = {}
        self._lock = threading.Lock()

    def _key(self, request: Request) -> tuple[str, str]:
        fwd = request.headers.get("x-forwarded-for")
        ip = fwd.split(",")[0].strip() if fwd else (
            request.client.host if request.client else "unknown")
        scope = "auth" if request.url.path in AUTH_PATHS else "general"
        return ip, scope

    def _limit(self, scope: str) -> int:
        return (self.s.rate_limit_auth_per_minute if scope == "auth"
                else self.s.rate_limit_per_minute)

    def check(self, request: Request) -> JSONResponse | None:
        if not request.url.path.startswith("/api"):
            return None
        if request.method == "OPTIONS":
            return None
        key = self._key(request)
        limit = self._limit(key[1])
        now = time.time()
        window = int(now // 60)
        with self._lock:
            count, w = self._buckets.get(key, (0, window))
            if w != window:
                count, w = 0, window
            count += 1
            self._buckets[key] = (count, w)
            if len(self._buckets) > 20000:            # bound the memory, drop old windows
                self._buckets = {k: v for k, v in self._buckets.items() if v[1] == window}
        if count > limit:
            retry = int(60 - (now % 60)) or 1
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited",
                         "message": f"Too many requests. Try again in {retry} seconds.",
                         "message_mr": "खूप विनंत्या. थोड्या वेळाने पुन्हा प्रयत्न करा.",
                         "retryable": True},
                headers={"Retry-After": str(retry)})
        return None
