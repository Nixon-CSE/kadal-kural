"""Public edge guard: through a tunnel only the phone channel and health check are reachable."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from kadal_kural.api.main import create_app
from kadal_kural.config import PHONE_TOKEN_HEADER, AppSettings

TOKEN = "edge-token"
ORDER = {"transcript": "குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு"}
CLOUDFLARE: Dict[str, str] = {"Cf-Connecting-Ip": "203.0.113.7", "X-Forwarded-For": "203.0.113.7"}


@pytest.fixture
def client(tmp_path: Path) -> Any:
    settings = AppSettings(db_path=str(tmp_path / "edge.db"), phone_webhook_token=TOKEN, gnani_api_key="k")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "method,path",
    [("GET", "/"), ("GET", "/api/v1/state"), ("POST", "/api/v1/reset"), ("POST", "/api/v1/ingest"),
     ("GET", "/static/app.js"), ("GET", "/docs")],
)
def test_proxied_requests_cannot_reach_private_routes(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path, headers=CLOUDFLARE, json=ORDER)
    assert response.status_code == 403
    assert client.get("/api/v1/state").json()["events"] == []  # nothing written


@pytest.mark.parametrize("header", ["Cf-Connecting-Ip", "X-Forwarded-For", "Forwarded"])
def test_any_proxy_header_marks_the_request_public(client: TestClient, header: str) -> None:
    assert client.post("/api/v1/reset", headers={header: "for=203.0.113.7"}).status_code == 403


def test_phone_channel_and_health_stay_reachable_through_the_proxy(client: TestClient) -> None:
    assert client.get("/healthz", headers=CLOUDFLARE).status_code == 200
    response = client.post("/api/v1/phone-turn", headers={**CLOUDFLARE, PHONE_TOKEN_HEADER: TOKEN}, json=ORDER)
    assert response.status_code == 200 and response.json()["booked_count"] == 1


def test_phone_token_is_still_required_through_the_proxy(client: TestClient) -> None:
    assert client.post("/api/v1/phone-turn", headers=CLOUDFLARE, json=ORDER).status_code == 401


def test_live_audio_socket_is_closed_for_proxied_clients(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect("/ws/live-audio", headers=CLOUDFLARE) as ws:
        ws.receive_json()
    assert closed.value.code == 1008


def test_local_requests_are_unaffected(client: TestClient) -> None:
    assert client.get("/").status_code == 200
    assert client.post("/api/v1/reset").status_code == 200


def test_guard_can_be_disabled_behind_an_authenticating_proxy(tmp_path: Path) -> None:
    settings = AppSettings(db_path=str(tmp_path / "open.db"), public_edge_guard=False)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/state", headers=CLOUDFLARE).status_code == 200
