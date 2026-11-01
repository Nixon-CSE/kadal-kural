"""/ws/live-audio: a browser leaving mid-stream ends the session cleanly, with no error logged."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, List

import pytest
from fastapi.testclient import TestClient

from kadal_kural.api.main import create_app
from kadal_kural.config import AppSettings


class FakePrisma:
    """Handshake, then the given events, then an idle server; records what it is sent."""

    def __init__(self, events: List[dict[str, Any]]) -> None:
        self.events = events
        self.sent: List[Any] = []

    def __call__(self, url: str, **kwargs: Any) -> "FakePrisma":
        return self

    async def __aenter__(self) -> "FakePrisma":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def recv(self) -> str:
        return json.dumps({"type": "connected", "id": "fake"})

    async def send(self, data: Any) -> None:
        self.sent.append(data)

    async def __aiter__(self) -> AsyncIterator[str]:
        for event in self.events:
            yield json.dumps(event)
        await asyncio.sleep(3600)


def _errors(caplog: pytest.LogCaptureFixture) -> List[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.fixture
def app_settings(tmp_path: Path) -> AppSettings:
    return AppSettings(gnani_api_key="test-key", db_path=str(tmp_path / "live.db"))


def test_client_disconnecting_mid_stream_closes_cleanly(
    app_settings: AppSettings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    prisma = FakePrisma([])
    monkeypatch.setattr("kadal_kural.api.main.websockets.connect", prisma)
    caplog.set_level(logging.INFO)
    first_frame = bytes(range(256)) * 4  # 1,024 bytes: the first byte must arrive intact and in order
    with TestClient(create_app(app_settings)) as client:
        with client.websocket_connect("/ws/live-audio") as ws:
            assert ws.receive_json()["type"] == "prisma_connected"
            ws.send_bytes(first_frame[:300])  # browser chunks needn't match Prisma's frame size
            ws.send_bytes(first_frame[300:])
            ws.send_bytes(b"\x01\x00" * 100)
    assert _errors(caplog) == []
    assert any("client disconnected" in r.getMessage() for r in caplog.records)
    assert [f for f in prisma.sent if isinstance(f, bytes)] == [first_frame]  # the partial tail waits


def test_disconnect_drops_a_half_assembled_utterance_without_booking_it(
    app_settings: AppSettings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fragment = {"type": "transcript", "text": "குமரனுக்கு 5 கிலோ", "latency": 180, "is_final": True}
    monkeypatch.setattr("kadal_kural.api.main.websockets.connect", FakePrisma([fragment]))
    with TestClient(create_app(app_settings)) as client:
        with client.websocket_connect("/ws/live-audio") as ws:
            assert ws.receive_json()["type"] == "prisma_connected"
            assert ws.receive_json()["type"] == "barge_in_and_segment"
        assert client.get("/api/v1/state").json()["events"] == []
    assert _errors(caplog) == []
