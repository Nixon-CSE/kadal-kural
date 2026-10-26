"""Mocked-socket unit tests for the Gnani Prisma/Timbre WebSocket client (no network)."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import struct
import wave
from typing import Any, Dict, List, Union

import pytest
from websockets.exceptions import ConnectionClosedError

from kadal_kural.config import AppSettings
from kadal_kural.infrastructure import gnani_client
from kadal_kural.infrastructure.gnani_client import (
    GnaniArthaSpeechClient,
    GnaniConfigurationError,
    GnaniProtocolError,
    finalize_streamed_wav,
)

Frame = Union[Dict[str, Any], BaseException]


class FakeWS:
    """Scripted socket: yields frames in order, then hangs (like an idle server)."""

    def __init__(self, frames: List[Frame]) -> None:
        self._frames = list(frames)
        self.sent: List[Any] = []
        self.closed = False

    async def recv(self) -> str:
        if not self._frames:
            await asyncio.sleep(3600)
        frame = self._frames.pop(0)
        if isinstance(frame, BaseException):
            raise frame
        return json.dumps(frame)

    async def send(self, data: Any) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True


class FakeConnect:
    def __init__(self, script: List[Union[FakeWS, BaseException]]) -> None:
        self._script = list(script)
        self.calls = 0
        self.last_kwargs: Dict[str, Any] = {}

    def __call__(self, url: str, **kwargs: Any) -> "FakeConnect":
        self.calls += 1
        self.last_kwargs = kwargs
        self._current = self._script.pop(0)
        return self

    async def __aenter__(self) -> FakeWS:
        if isinstance(self._current, BaseException):
            raise self._current
        return self._current

    async def __aexit__(self, *exc: object) -> None:
        return None


def _audio(index: int, payload: bytes, final: bool = False) -> Dict[str, Any]:
    return {
        "type": "audio",
        "data": {"chunk_index": index, "audio": base64.b64encode(payload).decode(), "is_final": final},
    }


def _wav_header_streaming(sample_rate: int = 16000) -> bytes:
    """The header Timbre really sends: RIFF and data sizes are the 0xFFFFFFFF placeholder."""
    return (
        b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
        + b"data" + struct.pack("<I", 0xFFFFFFFF)
    )


@pytest.fixture
def settings(tmp_path: Any) -> AppSettings:
    return AppSettings(
        gnani_api_key="test-key",
        gnani_backoff_base_sec=0.0,
        gnani_read_timeout_sec=0.2,
        gnani_max_attempts=3,
        stt_drain_grace_sec=0.01,
        db_path=str(tmp_path / "unit.db"),
    )


@pytest.fixture(autouse=True)
def _no_real_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gnani_client, "frame_pace_seconds", lambda _rate: 0.0)


def _patch_connect(monkeypatch: pytest.MonkeyPatch, script: List[Union[FakeWS, BaseException]]) -> FakeConnect:
    fake = FakeConnect(script)
    monkeypatch.setattr(gnani_client.websockets, "connect", fake)
    return fake


async def test_tts_error_frame_raises_runtime_error_and_is_not_retried(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _patch_connect(monkeypatch, [FakeWS([{"type": "error", "message": "bad voice"}])])
    with pytest.raises(RuntimeError, match="bad voice"):
        await GnaniArthaSpeechClient(settings).synthesize_timbre_v25("வணக்கம்")
    assert fake.calls == 1


async def test_tts_complete_frame_terminates_cleanly(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = FakeWS([
        {"type": "start", "message": "Streaming started"},
        _audio(1, b"\x01\x00" * 600),
        {"type": "complete", "data": {"chunk_index": 2, "audio": "", "is_final": True}},
    ])
    _patch_connect(monkeypatch, [ws])
    telemetry = await GnaniArthaSpeechClient(settings).synthesize_timbre_v25("வணக்கம்")
    assert telemetry.was_interrupted is False
    assert telemetry.ttfb_ms > 0.0
    assert len(telemetry.audio_wav_bytes) == 1200
    assert ws.closed is False  # clean protocol termination, not an abort


async def test_tts_three_chunks_reassemble_in_chunk_index_order_and_wav_is_valid(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    pcm = [bytes([i]) * 400 for i in (1, 2, 3)]  # 200 samples each
    first = _wav_header_streaming() + pcm[0]
    ws = FakeWS([
        _audio(2, pcm[1]),  # arrives out of order
        _audio(1, first),
        _audio(3, pcm[2]),
        {"type": "complete", "data": {"chunk_index": 4, "audio": "", "is_final": True}},
    ])
    _patch_connect(monkeypatch, [ws])
    telemetry = await GnaniArthaSpeechClient(settings).synthesize_timbre_v25("வணக்கம்")

    with wave.open(io.BytesIO(telemetry.audio_wav_bytes), "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 600  # header sizes were repaired, not 0xFFFFFFFF
        assert wf.readframes(wf.getnframes()) == pcm[0] + pcm[1] + pcm[2]


def test_finalize_streamed_wav_leaves_headerless_pcm_untouched() -> None:
    assert finalize_streamed_wav(b"\x00\x01" * 10) == b"\x00\x01" * 10
    assert finalize_streamed_wav(b"") == b""


async def test_tts_retries_connection_failures_then_succeeds(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = FakeWS([_audio(1, b"\x01\x00" * 10), {"type": "complete", "data": {"is_final": True}}])
    fake = _patch_connect(monkeypatch, [OSError("down"), asyncio.TimeoutError(), good])
    telemetry = await GnaniArthaSpeechClient(settings).synthesize_timbre_v25("வணக்கம்")
    assert fake.calls == 3
    assert len(telemetry.audio_wav_bytes) == 20
    assert fake.last_kwargs["open_timeout"] == settings.gnani_open_timeout_sec


async def test_tts_gives_up_after_max_attempts(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _patch_connect(monkeypatch, [OSError("down")] * 3)
    with pytest.raises(OSError):
        await GnaniArthaSpeechClient(settings).synthesize_timbre_v25("வணக்கம்")
    assert fake.calls == 3


async def test_tts_read_timeout_on_silent_server(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _patch_connect(monkeypatch, [FakeWS([]) for _ in range(3)])
    with pytest.raises(asyncio.TimeoutError):
        await GnaniArthaSpeechClient(settings).synthesize_timbre_v25("வணக்கம்")
    assert fake.calls == 3  # a timeout before any audio is retryable


async def test_tts_does_not_retry_after_audio_was_received(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = FakeWS([_audio(1, b"\x00\x00" * 8), ConnectionClosedError(None, None)])
    fake = _patch_connect(monkeypatch, [ws, FakeWS([])])
    with pytest.raises(ConnectionClosedError):
        await GnaniArthaSpeechClient(settings).synthesize_timbre_v25("வணக்கம்")
    assert fake.calls == 1


async def test_tts_malformed_frame_raises_protocol_error(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RawWS(FakeWS):
        async def recv(self) -> str:
            return "not json{"

    fake = _patch_connect(monkeypatch, [RawWS([])])
    with pytest.raises(GnaniProtocolError):
        await GnaniArthaSpeechClient(settings).synthesize_timbre_v25("வணக்கம்")
    assert fake.calls == 1


async def test_missing_api_key_raises_configuration_error(tmp_path: Any) -> None:
    client = GnaniArthaSpeechClient(AppSettings(gnani_api_key="", db_path=str(tmp_path / "x.db")))
    with pytest.raises(GnaniConfigurationError):
        await client.synthesize_timbre_v25("வணக்கம்")


_HANDSHAKE: Dict[str, Any] = {"type": "connected", "config": {"sample_rate": 16000, "chunk_size": 512}}


async def test_stt_streams_trailing_silence_and_delivers_transcript(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = FakeWS([
        _HANDSHAKE,
        {"type": "speech_start", "utterance_id": "u1"},
        {"type": "transcript", "text": "20 கிலோ", "latency": 210, "utterance_id": "u1", "is_final": True},
    ])
    fake = _patch_connect(monkeypatch, [ws])
    got: List[tuple[str, float]] = []

    async def _on_segment(text: str, latency: float) -> None:
        got.append((text, latency))

    pcm = b"\x10\x00" * 1024  # exactly 2 frames of speech
    await GnaniArthaSpeechClient(settings).stream_pcm_to_prisma_v25(
        pcm, _on_segment, sample_rate=16000, enable_boosting=False
    )
    assert got == [("20 கிலோ", 210.0)]
    assert fake.last_kwargs["additional_headers"]["x-sample-rate"] == "16000"
    frames = [f for f in ws.sent if isinstance(f, bytes)]
    assert all(len(f) == 1024 for f in frames)
    silence_frames = [f for f in frames if not any(f)]
    # (360ms + 500ms margin) of 16kHz 16-bit PCM = 27,520 bytes -> at least 26 silent frames
    assert len(silence_frames) >= 26


async def test_stt_error_frame_raises_and_is_not_retried(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _patch_connect(monkeypatch, [FakeWS([_HANDSHAKE, {"type": "error", "message": "quota"}])])

    async def _on_segment(text: str, latency: float) -> None:
        raise AssertionError("no segment expected")

    with pytest.raises(RuntimeError, match="quota"):
        await GnaniArthaSpeechClient(settings).stream_pcm_to_prisma_v25(
            b"\x00\x00" * 4096, _on_segment, sample_rate=8000
        )
    assert fake.calls == 1


async def test_stt_utterance_without_transcript_times_out(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    script: List[Union[FakeWS, BaseException]] = [
        FakeWS([_HANDSHAKE, {"type": "speech_start", "utterance_id": "u1"}]) for _ in range(3)
    ]
    fake = _patch_connect(monkeypatch, script)

    async def _on_segment(text: str, latency: float) -> None:
        return None

    with pytest.raises(asyncio.TimeoutError):
        await GnaniArthaSpeechClient(settings).stream_pcm_to_prisma_v25(
            b"\x00\x00" * 1024, _on_segment, sample_rate=8000
        )
    assert fake.calls == 3


async def test_stt_rejects_unsupported_sample_rate(settings: AppSettings) -> None:
    async def _on_segment(text: str, latency: float) -> None:
        return None

    with pytest.raises(ValueError, match="Unsupported sample_rate"):
        await GnaniArthaSpeechClient(settings).stream_pcm_to_prisma_v25(
            b"\x00" * 1024, _on_segment, sample_rate=44100
        )
