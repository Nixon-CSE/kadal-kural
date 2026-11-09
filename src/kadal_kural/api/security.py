"""
Browser-facing protections for the desk, plus the phone channel's rate limiter.

The desk is served on localhost without user accounts, so the threat is other websites open in the
same browser, not other users:

* **Cross-site requests (CSRF) and cross-site WebSocket hijacking.** A page on any site can POST to
  ``http://localhost:8000/api/v1/reset`` or open ``ws://localhost:8000/ws/live-audio`` (which writes
  ledger entries and spends Gnani credits). Browsers label such requests with ``Origin`` and
  ``Sec-Fetch-Site``; unsafe methods and WebSocket handshakes from another site are refused.
* **DNS rebinding.** A hostile domain re-pointed at 127.0.0.1 is "same-origin" to itself, so the
  ``Host`` header must be a name this app is meant to be reached by (localhost, or ``allowed_hosts``).
* **Missing hardening headers.** Every response gets a strict CSP, nosniff, frame denial, a
  Permissions-Policy that grants the microphone to this origin only, and ``no-store`` on the API.

Requests that arrived through a proxy or tunnel are left to ``PublicEdgeGuard`` (api/edge.py), which
already confines them to the token-protected phone endpoint and the health check.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Deque, Dict, FrozenSet, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

from starlette.exceptions import HTTPException

from kadal_kural.api.edge import ASGIApp, Message, Receive, Scope, Send, is_proxied

logger = logging.getLogger(__name__)

LOCAL_HOSTS: FrozenSet[str] = frozenset({"localhost", "127.0.0.1", "::1", "testserver"})
SAFE_METHODS: FrozenSet[str] = frozenset({"GET", "HEAD", "OPTIONS"})
# Server-to-server, authenticated by its own token; browsers never call it.
CSRF_EXEMPT_PATHS: FrozenSet[str] = frozenset({"/api/v1/phone-turn"})

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        # Animation libraries and Radix set element styles at runtime; no inline <style> or script.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "media-src 'self' data: blob:",  # Timbre replies arrive as data: WAV
        "font-src 'self'",
        "connect-src 'self'",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
_BASE_HEADERS: List[Tuple[bytes, bytes]] = [
    (b"content-security-policy", CONTENT_SECURITY_POLICY.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"microphone=(self), camera=(), geolocation=(), payment=(), usb=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
]


def _header(scope: Scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return bytes(value).decode("latin-1")
    return None


def _host_name(host_header: str) -> str:
    """'localhost:8000' -> 'localhost', '[::1]:8000' -> '::1'."""
    return (urlsplit(f"//{host_header}").hostname or "").lower()


async def _refuse(scope: Scope, send: Send, status: int, detail: str) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


class SecurityHeaders:
    """Adds hardening headers to every HTTP response; API responses are also marked ``no-store``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = str(scope.get("path", "")).startswith("/api/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {bytes(k).lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in _BASE_HEADERS if k not in present]
                if is_api and b"cache-control" not in present:
                    extra.append((b"cache-control", b"no-store"))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)


class LocalOriginGuard:
    """
    For direct (non-proxied) requests: the ``Host`` must be an expected name, and unsafe methods and
    WebSocket handshakes must not come from another site. Non-browser clients (curl, the tests) send
    no ``Origin`` or ``Sec-Fetch-Site`` and pass.
    """

    def __init__(self, app: ASGIApp, extra_hosts: Iterable[str] = ()) -> None:
        self.app = app
        self.hosts = LOCAL_HOSTS | {h.strip().lower() for h in extra_hosts if h.strip()}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or is_proxied(scope):
            await self.app(scope, receive, send)
            return
        host = _header(scope, b"host") or ""
        if _host_name(host) not in self.hosts:
            logger.warning("Refused request for unexpected host %r (possible DNS rebinding)", host[:100])
            await _refuse(scope, send, 421, "Unknown host. Add it to KADAL_ALLOWED_HOSTS to serve it.")
            return
        method = "WEBSOCKET" if scope["type"] == "websocket" else str(scope.get("method", "GET")).upper()
        if method not in SAFE_METHODS and scope.get("path") not in CSRF_EXEMPT_PATHS and self._cross_site(scope, host):
            logger.warning("Refused cross-site %s %s", method, scope.get("path"))
            await _refuse(scope, send, 403, "Cross-site request refused")
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _cross_site(scope: Scope, host: str) -> bool:
        if (_header(scope, b"sec-fetch-site") or "").lower() == "cross-site":
            return True
        origin = _header(scope, b"origin")
        if origin is None:
            return False
        if origin == "null":  # sandboxed iframes, file:// pages, redirects across origins
            return True
        return urlsplit(origin).netloc.lower() != host.lower()


DEFAULT_MAX_BODY_BYTES = 64 * 1024


class RequestSizeLimit:
    """
    Caps request bodies per path (``limits``; others get ``default``). A declared Content-Length over
    the cap is refused before anything is read; a chunked body is counted as it streams in and the
    read fails with 413, which FastAPI re-raises rather than turning into a 400.
    """

    def __init__(self, app: ASGIApp, limits: Dict[str, int], default: int = DEFAULT_MAX_BODY_BYTES) -> None:
        self.app = app
        self.limits = dict(limits)
        self.default = default

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limits.get(str(scope.get("path", "")), self.default)
        declared = _header(scope, b"content-length")
        if declared is not None and declared.strip().isdigit() and int(declared) > limit:
            await _refuse(scope, send, 413, f"Request body larger than {limit} bytes")
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail=f"Request body larger than {limit} bytes")
            return message

        await self.app(scope, limited_receive, send)


class SlidingWindowRateLimiter:
    """At most ``limit`` events per ``window_seconds`` for each key. Thread-safe; memory is bounded."""

    def __init__(self, limit: int, window_seconds: float = 60.0, max_keys: int = 10_000) -> None:
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, now: Optional[float] = None) -> Optional[float]:
        """Records an event for ``key``. None if allowed, else seconds until the next one is."""
        if self.limit <= 0:
            return None
        now = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.get(key)
            if events is None:
                if len(self._events) >= self.max_keys:  # drop idle keys before growing further
                    self._events = {k: v for k, v in self._events.items() if v and now - v[-1] < self.window}
                events = self._events[key] = deque()
            while events and now - events[0] >= self.window:
                events.popleft()
            if len(events) >= self.limit:
                return max(0.0, self.window - (now - events[0]))
            events.append(now)
            return None


def client_address(scope: Scope) -> str:
    """The caller's address: the tunnel's Cf-Connecting-Ip, the first X-Forwarded-For hop, or the peer."""
    forwarded = _header(scope, b"cf-connecting-ip") or (_header(scope, b"x-forwarded-for") or "").split(",")[0]
    if forwarded.strip():
        return forwarded.strip()
    client = scope.get("client")
    return str(client[0]) if client else "unknown"
