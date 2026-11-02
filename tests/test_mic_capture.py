"""Opt-in raw mic capture: what the browser sent is saved exactly, with where segments arrived."""

from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List

import pytest
from fastapi.testclient import TestClient

from kadal_kural.api.main import create_app
from kadal_kural.config import NS_PER_MS, AppSettings
from kadal_kural.infrastructure.mic_capture import MicCaptureRecorder


class FakeClock:
    def __init__(self) -> None:
        self.now_ns = 5_000 * NS_PER_MS

    def __call__(self) -> int:
        return self.now_ns


def test_recorder_writes_the_exact_pcm_and_segment_positions(tmp_path: Path) -> None:
    clock = FakeClock()
    recorder = MicCaptureRecorder(tmp_path, 8000, clock=clock, stamp="t")
    recorder.write(b"\x01\x00" * 8000)  # 1 s of audio
    clock.now_ns += 1_250 * NS_PER_MS
    recorder.mark_segment("அமரனுக்கு 20 கிலோ", 180.0)
    recorder.write(b"\x02\x00" * 4000)
    recorder.close()
    with wave.open(str(tmp_path / "mic_t.wav"), "rb") as wf:
        assert (wf.getframerate(), wf.getnchannels(), wf.getsampwidth()) == (8000, 1, 2)
        assert wf.readframes(wf.getnframes()) == b"\x01\x00" * 8000 + b"\x02\x00" * 4000
    assert json.loads((tmp_path / "mic_t.json").read_text(encoding="utf-8")) == {
        "wav": "mic_t.wav",
        "sample_rate": 8000,
        "audio_ms": 1500.0,
        "segments": [
            {
                "text": "அமரனுக்கு 20 கிலோ",
                "reported_latency_ms": 180.0,
                "audio_ms_at_arrival": 1000.0,
                "session_ms_at_arrival": 1250.0,
            }
        ],
    }


class FakePrisma:
    """Handshake, one transcript once audio arrived, then idle."""

    def __init__(self) -> None:
        self.audio = asyncio.Event()

    def __call__(self, url: str, **kwargs: Any) -> "FakePrisma":
        return self

    async def __aenter__(self) -> "FakePrisma":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def recv(self) -> str:
        return json.dumps({"type": "connected", "id": "fake"})

    async def send(self, data: Any) -> None:
        if isinstance(data, bytes):
            self.audio.set()

    async def __aiter__(self) -> AsyncIterator[str]:
        await self.audio.wait()
        yield json.dumps({"type": "transcript", "text": "குமரனுக்கு 20 கிலோ", "latency": 190, "is_final": True})
        await asyncio.sleep(3600)


@pytest.mark.parametrize("enabled", [True, False])
def test_live_session_saves_a_capture_only_when_enabled(
    enabled: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captures = tmp_path / "captures"
    settings = AppSettings(
        gnani_api_key="test-key", db_path=str(tmp_path / "c.db"), mic_capture_dir=str(captures) if enabled else ""
    )
    monkeypatch.setattr("kadal_kural.api.main.websockets.connect", FakePrisma())
    sent = bytes(range(256)) * 8  # two 1,024-byte frames' worth, sent in odd-sized browser chunks
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/live-audio") as ws:
            assert ws.receive_json()["type"] == "prisma_connected"
            ws.send_bytes(sent[:700])
            ws.send_bytes(sent[700:])
            assert ws.receive_json()["type"] == "barge_in_and_segment"
    if not enabled:
        assert not captures.exists()
        return
    (wav_path,) = captures.glob("mic_*.wav")
    with wave.open(str(wav_path), "rb") as wf:
        assert wf.readframes(wf.getnframes()) == sent
    sidecar: Dict[str, Any] = json.loads(wav_path.with_suffix(".json").read_text(encoding="utf-8"))
    segments: List[Dict[str, Any]] = sidecar["segments"]
    assert [s["text"] for s in segments] == ["குமரனுக்கு 20 கிலோ"]
    assert 0.0 < segments[0]["audio_ms_at_arrival"] <= sidecar["audio_ms"]
