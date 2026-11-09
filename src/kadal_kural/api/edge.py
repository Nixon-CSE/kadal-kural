"""
Edge guard for traffic that reaches the app through a reverse proxy or tunnel.

The phone channel needs a public URL, but a tunnel (e.g. ``cloudflared``) exposes every route:
ledger reset, ingest, and the live-audio socket that spends Gnani credits. Proxies mark what
they forward (``Cf-Connecting-Ip``, ``X-Forwarded-For``, ``Forwarded``); a request carrying any
of these is treated as public and may reach only the allow-listed paths. Direct local requests
(the desk UI on localhost) are untouched. Applies to HTTP and WebSocket scopes alike.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, FrozenSet, Iterable, MutableMapping

logger = logging.getLogger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

PROXY_HEADERS: FrozenSet[bytes] = frozenset({b"cf-connecting-ip", b"x-forwarded-for", b"forwarded"})
PUBLIC_PATHS: FrozenSet[str] = frozenset({"/api/v1/phone-turn", "/healthz"})


def log_safe(value: object, limit: int = 200) -> str:
    """Request-controlled text made safe for a log line: control characters escaped, length capped,
    so a crafted path, header or field name cannot forge or split log entries."""
    text = str(value)[:limit]
    return "".join(ch if ch.isprintable() else ch.encode("unicode_escape").decode("ascii") for ch in text)


def is_proxied(scope: Scope) -> bool:
    return any(name.lower() in PROXY_HEADERS for name, _ in scope.get("headers", []))


class PublicEdgeGuard:
    """ASGI middleware: proxied requests outside ``public_paths`` get 403 (HTTP) or close 1008 (WS)."""

    def __init__(self, app: ASGIApp, public_paths: Iterable[str] = PUBLIC_PATHS) -> None:
        self.app = app
        self.public_paths = frozenset(public_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not is_proxied(scope):
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in self.public_paths:
            await self.app(scope, receive, send)
            return
        logger.warning("Blocked proxied %s request to %s", scope["type"], log_safe(path))
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps({"detail": "Not available through the public URL"}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})
