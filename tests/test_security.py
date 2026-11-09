"""Browser and abuse protections: headers, cross-site requests, DNS rebinding, size and rate limits."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, List

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from kadal_kural.api.main import MAX_LIVE_FRAME_BYTES, MAX_TRANSCRIPT_CHARS, create_app
from kadal_kural.api.security import SlidingWindowRateLimiter
from kadal_kural.config import PHONE_TOKEN_HEADER, AppSettings

TOKEN = "security-token"
ORDER = "குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு"
EVIL = "https://evil.example"


def _app(tmp_path: Path, **overrides: Any) -> TestClient:
    settings = AppSettings(db_path=str(tmp_path / "sec.db"), phone_webhook_token=TOKEN, **overrides)
    return TestClient(create_app(settings))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with _app(tmp_path) as test_client:
        yield test_client


def _booked(client: TestClient) -> int:
    return len(client.get("/api/v1/state").json()["events"])


# ---------- headers ----------

def test_every_response_carries_hardening_headers(client: TestClient) -> None:
    for path in ("/", "/api/v1/state", "/healthz"):
        headers = client.get(path).headers
        assert "default-src 'self'" in headers["content-security-policy"], path
        assert "frame-ancestors 'none'" in headers["content-security-policy"]
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "no-referrer"
        assert "microphone=(self)" in headers["permissions-policy"]


def test_api_responses_are_not_cached_but_assets_may_be(client: TestClient) -> None:
    assert client.get("/api/v1/state").headers["cache-control"] == "no-store"
    assert client.get("/").headers.get("cache-control") != "no-store"


# ---------- cross-site requests ----------

@pytest.mark.parametrize("headers", [{"Origin": EVIL}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}])
def test_cross_site_writes_are_refused(client: TestClient, headers: dict[str, str]) -> None:
    client.post("/api/v1/ingest", json={"transcript": ORDER, "synthesize_tts": False})
    assert client.post("/api/v1/reset", headers=headers).status_code == 403
    response = client.post("/api/v1/ingest", json={"transcript": ORDER, "synthesize_tts": False}, headers=headers)
    assert response.status_code == 403
    assert _booked(client) == 1  # neither the reset nor the second order happened


def test_same_origin_and_non_browser_writes_work(client: TestClient) -> None:
    same = {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}
    assert client.post("/api/v1/ingest", json={"transcript": ORDER, "synthesize_tts": False}, headers=same).status_code == 200
    assert client.post("/api/v1/ingest", json={"transcript": ORDER, "synthesize_tts": False}).status_code == 200  # curl


def test_cross_site_reads_are_left_to_the_browsers_same_origin_policy(client: TestClient) -> None:
    assert client.get("/api/v1/state", headers={"Origin": EVIL}).status_code == 200


def test_phone_webhook_is_server_to_server_and_not_subject_to_the_origin_check(client: TestClient) -> None:
    response = client.post(
        "/api/v1/phone-turn", json={"transcript": ORDER}, headers={PHONE_TOKEN_HEADER: TOKEN, "Origin": EVIL}
    )
    assert response.status_code == 200


def test_cross_site_websocket_is_refused(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws/live-audio", headers={"Origin": EVIL}):
            pass
    assert closed.value.code == 1008


# ---------- DNS rebinding ----------

def test_unknown_host_is_refused(client: TestClient) -> None:
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 421
    assert client.post("/api/v1/reset", headers={"Host": "attacker.example:8000"}).status_code == 421


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000"])
def test_local_hosts_are_served(client: TestClient, host: str) -> None:
    assert client.get("/healthz", headers={"Host": host}).status_code == 200


def test_extra_hosts_can_be_allowed(tmp_path: Path) -> None:
    with _app(tmp_path, allowed_hosts="192.168.0.105, desk.lan") as c:
        assert c.get("/healthz", headers={"Host": "192.168.0.105:8000"}).status_code == 200
        assert c.get("/healthz", headers={"Host": "desk.lan"}).status_code == 200
        assert c.get("/healthz", headers={"Host": "other.lan"}).status_code == 421


def test_tunnel_traffic_keeps_its_own_host_name(client: TestClient) -> None:
    tunnel = {"Host": "abc.trycloudflare.com", "Cf-Connecting-Ip": "203.0.113.9", PHONE_TOKEN_HEADER: TOKEN}
    assert client.post("/api/v1/phone-turn", json={"transcript": ORDER}, headers=tunnel).status_code == 200
    assert client.get("/api/v1/state", headers=tunnel).status_code == 403  # still only the phone route


# ---------- size limits ----------

def test_oversized_phone_body_is_refused_before_it_is_read(client: TestClient) -> None:
    big = json.dumps({"transcript": ORDER, "pad": "x" * 40_000})
    response = client.post(
        "/api/v1/phone-turn", content=big, headers={PHONE_TOKEN_HEADER: TOKEN, "Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert _booked(client) == 0


def test_oversized_chunked_body_without_length_is_refused(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(100):
            yield b"x" * 1024  # 100 KB, more than the 64 KB default, with no Content-Length

    response = client.post("/api/v1/ingest", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_overlong_transcripts_are_refused(client: TestClient) -> None:
    long_text = "அ" * (MAX_TRANSCRIPT_CHARS + 1)
    assert client.post("/api/v1/ingest", json={"transcript": long_text}).status_code == 422
    phone = client.post("/api/v1/phone-turn", json={"transcript": long_text}, headers={PHONE_TOKEN_HEADER: TOKEN})
    assert phone.status_code == 422
    assert _booked(client) == 0


def test_upload_limit_is_configurable(tmp_path: Path) -> None:
    with _app(tmp_path, max_upload_bytes=1024) as c:
        files = {"file": ("big.wav", b"\0" * 4096, "audio/wav")}
        assert c.post("/api/v1/upload-wav", files=files).status_code == 413


# ---------- rate limit ----------

def test_phone_channel_is_rate_limited_per_caller(tmp_path: Path) -> None:
    with _app(tmp_path, phone_rate_limit_per_minute=3) as c:
        caller = {PHONE_TOKEN_HEADER: TOKEN, "X-Forwarded-For": "198.51.100.1"}
        codes = [c.post("/api/v1/phone-turn", json={"transcript": ORDER}, headers=caller).status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        limited = c.post("/api/v1/phone-turn", json={"transcript": ORDER}, headers=caller)
        assert int(limited.headers["retry-after"]) >= 1
        other = {PHONE_TOKEN_HEADER: TOKEN, "X-Forwarded-For": "198.51.100.2"}
        assert c.post("/api/v1/phone-turn", json={"transcript": ORDER}, headers=other).status_code == 200


def test_wrong_tokens_count_against_the_limit_too(tmp_path: Path) -> None:
    with _app(tmp_path, phone_rate_limit_per_minute=2) as c:
        guess = {PHONE_TOKEN_HEADER: "guess", "X-Forwarded-For": "198.51.100.7"}
        codes = [c.post("/api/v1/phone-turn", json={"transcript": ORDER}, headers=guess).status_code for _ in range(3)]
        assert codes == [401, 401, 429]


def test_rate_limiter_window_slides() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
    assert limiter.check("a", now=0) is None
    assert limiter.check("a", now=10) is None
    assert limiter.check("a", now=20) == pytest.approx(40)  # the first event expires at t=60
    assert limiter.check("a", now=61) is None
    assert SlidingWindowRateLimiter(limit=0).check("a") is None  # 0 disables


def test_rate_limiter_memory_is_bounded() -> None:
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=1, max_keys=10)
    for i in range(100):
        limiter.check(f"k{i}", now=float(i * 2))  # every key is idle by the time the next arrives
    assert len(limiter._events) <= 11


# ---------- live audio socket ----------

class _IdlePrisma:
    """A Prisma stand-in that connects and then stays silent."""

    def __call__(self, url: str, **kwargs: Any) -> "_IdlePrisma":
        return self

    async def __aenter__(self) -> "_IdlePrisma":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def recv(self) -> str:
        return json.dumps({"type": "connected", "id": "fake"})

    async def send(self, data: Any) -> None:
        return None

    async def __aiter__(self) -> AsyncIterator[str]:
        await asyncio.sleep(3600)
        yield ""


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr("kadal_kural.api.main.websockets.connect", _IdlePrisma())
    with _app(tmp_path, gnani_api_key="test-key") as c:
        yield c


def test_oversized_audio_frame_closes_the_session(live: TestClient) -> None:
    with live.websocket_connect("/ws/live-audio") as ws:
        assert ws.receive_json()["type"] == "prisma_connected"
        ws.send_bytes(b"\0" * (MAX_LIVE_FRAME_BYTES + 1))
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 1009


def test_malformed_control_message_is_ignored(live: TestClient) -> None:
    with live.websocket_connect("/ws/live-audio") as ws:
        assert ws.receive_json()["type"] == "prisma_connected"
        ws.send_text("{not json")
        ws.send_text(json.dumps(["not", "an", "object"]))
        ws.send_bytes(b"\0" * 1024)  # the session is still alive and accepting audio


def test_session_time_limit_closes_the_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kadal_kural.api.main.websockets.connect", _IdlePrisma())
    clock: List[float] = [1000.0]
    monkeypatch.setattr("kadal_kural.api.main.time.monotonic", lambda: clock[0])
    with _app(tmp_path, gnani_api_key="test-key", live_session_max_seconds=60) as c:
        with c.websocket_connect("/ws/live-audio") as ws:
            assert ws.receive_json()["type"] == "prisma_connected"
            clock[0] += 61
            ws.send_bytes(b"\0" * 1024)
            message = ws.receive_json()
            assert message["type"] == "error" and "time limit" in message["message"]


# ---------- logs and error messages ----------

def test_log_safe_escapes_control_characters_and_caps_length() -> None:
    from kadal_kural.api.edge import log_safe

    assert log_safe("/x\nFAKE LOG LINE\r") == "/x\\nFAKE LOG LINE\\r"
    assert log_safe("குமரன்") == "குமரன்"  # printable Tamil is kept as is
    assert len(log_safe("a" * 1000)) == 200


def test_crafted_phone_field_names_cannot_split_the_log_line(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="kadal_kural.phone")
    client.post(
        "/api/v1/phone-turn",
        json={"transcript": ORDER, "x\nFORGED ENTRY": "1"},
        headers={PHONE_TOKEN_HEADER: TOKEN},
    )
    phone_lines = [r.getMessage() for r in caplog.records if r.name == "kadal_kural.phone"]
    assert phone_lines and all("\n" not in line for line in phone_lines)


def test_upload_errors_do_not_echo_parser_internals(client: TestClient) -> None:
    response = client.post("/api/v1/upload-wav", files={"file": ("x.wav", b"not a wav", "audio/wav")})
    assert response.status_code == 400
    assert response.json()["detail"] == "Not a readable WAV file"
