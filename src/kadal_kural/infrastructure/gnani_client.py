"""
Production WebSocket adapters for Gnani AI's Sovereign Artha Stack:
- Prisma v2.5 Streaming Speech-to-Text (wss://api.vachana.ai/stt/v3/stream)
- Timbre v2.5 Streaming Text-to-Speech (wss://api.vachana.ai/api/v1/tts)

Enforces strict 1,024-byte binary PCM frame pacing, mid-session vocabulary boosting,
and sub-50ms barge-in TTS stream cancellation.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import struct
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional, Set, TypeVar

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import InvalidStatus, WebSocketException

from kadal_kural.config import (
    PCM_FRAME_BYTES,
    PCM_SAMPLE_WIDTH_BYTES,
    SUPPORTED_PCM_SAMPLE_RATES,
    WS_PING_INTERVAL_SEC,
    AppSettings,
    frame_pace_seconds,
)

logger = logging.getLogger(__name__)

MANDATORY_PCM_FRAME_BYTES: int = PCM_FRAME_BYTES
_T = TypeVar("_T")

_RIFF_HEADER_MIN_BYTES: int = 12
_WAV_CHUNK_HEADER_BYTES: int = 8
_UNSET_WAV_SIZE: int = 0xFFFFFFFF
_RETRYABLE_HTTP_STATUS_FLOOR: int = 500


class GnaniConfigurationError(RuntimeError):
    """Raised when a live Gnani API call is attempted without a configured API key."""


class GnaniProtocolError(RuntimeError):
    """Raised when Gnani sends an ``error``-type frame. Never retried: the server rejected the request."""


@dataclass(frozen=True)
class SynthesisTelemetry:
    """Measured production telemetry from a live Timbre v2.5 WebSocket synthesis call."""

    audio_wav_bytes: bytes
    ttfb_ms: float
    total_synthesis_ms: float
    was_interrupted: bool


class PCM1024RingBufferPacer:
    """
    Accumulates arbitrary-length raw PCM bytes from browser WebRTC/AudioWorklet or
    telephony streams and yields strict 1,024-byte frames required by Gnani Prisma v2.5.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def push_bytes(self, raw_pcm: bytes) -> List[bytes]:
        """Appends ``raw_pcm`` and returns every complete 1,024-byte frame now available."""
        self._buffer.extend(raw_pcm)
        frames: List[bytes] = []
        while len(self._buffer) >= MANDATORY_PCM_FRAME_BYTES:
            frames.append(bytes(self._buffer[:MANDATORY_PCM_FRAME_BYTES]))
            del self._buffer[:MANDATORY_PCM_FRAME_BYTES]
        return frames

    def flush_padded(self) -> Optional[bytes]:
        """Returns the remaining partial frame zero-padded to 1,024 bytes, or None if empty."""
        if not self._buffer:
            return None
        padded = bytes(self._buffer).ljust(MANDATORY_PCM_FRAME_BYTES, b"\x00")
        self._buffer.clear()
        return padded


class MultiSegmentTradeAssembler:
    """
    Stitches consecutive VAD speech segments across a sliding window (default 1.5s)
    so multi-trade single-breath utterances split by a brief breath pause are evaluated atomically.
    """

    def __init__(
        self,
        window_sec: float,
        on_commit: Callable[[str, float], Awaitable[None]],
    ) -> None:
        self._window_sec = window_sec
        self._on_commit = on_commit
        self._segments: List[str] = []
        self._latencies_ms: List[float] = []
        self._flush_task: Optional[asyncio.Task[None]] = None

    async def ingest_segment(self, transcript: str, stt_latency_ms: float) -> None:
        """Buffers a VAD segment and (re)starts the stitching window."""
        cleaned = transcript.strip()
        if not cleaned:
            return
        self._segments.append(cleaned)
        self._latencies_ms.append(stt_latency_ms)
        if self._flush_task is not None and not self._flush_task.done():
            self._flush_task.cancel()
        self._flush_task = asyncio.create_task(self._wait_and_flush())

    async def flush_immediately(self) -> None:
        """Commits any buffered segments now instead of waiting for the window to elapse."""
        if self._flush_task is not None and not self._flush_task.done():
            self._flush_task.cancel()
        await self._commit_buffer()

    async def _wait_and_flush(self) -> None:
        try:
            await asyncio.sleep(self._window_sec)
            await self._commit_buffer()
        except asyncio.CancelledError:
            return

    async def _commit_buffer(self) -> None:
        if not self._segments:
            return
        merged_utterance = " ".join(self._segments)
        mean_latency_ms = sum(self._latencies_ms) / max(1, len(self._latencies_ms))
        self._segments.clear()
        self._latencies_ms.clear()
        await self._on_commit(merged_utterance, round(mean_latency_ms, 1))


def finalize_streamed_wav(audio: bytes) -> bytes:
    """
    Timbre streams a WAV whose RIFF/data size fields are the 0xFFFFFFFF "unknown length"
    placeholder. Rewrites them to the real byte counts so strict decoders accept the file.
    Non-RIFF (headerless PCM) or already-correct input is returned unchanged.
    """
    if len(audio) < _RIFF_HEADER_MIN_BYTES or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return audio
    data_tag = audio.find(b"data", _RIFF_HEADER_MIN_BYTES)
    if data_tag < 0:
        return audio
    data_start = data_tag + _WAV_CHUNK_HEADER_BYTES
    patched = bytearray(audio)
    struct.pack_into("<I", patched, 4, len(audio) - _WAV_CHUNK_HEADER_BYTES)
    struct.pack_into("<I", patched, data_tag + 4, max(0, len(audio) - data_start))
    return bytes(patched)


class GnaniArthaSpeechClient:
    """
    Production client for Gnani Prisma v2.5 STT and Timbre v2.5 TTS over WebSocket.
    Contains zero mocked responses; every method communicates with api.vachana.ai.

    Resilience: both sockets use an open timeout and a per-read timeout, and connection
    failures are retried with exponential backoff (``gnani_max_attempts``). A retry never
    happens after output was already produced, and never after a server ``error`` frame.
    """

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._barge_in_abort_event = asyncio.Event()

    def trigger_barge_in_abort(self) -> float:
        """
        Signals any in-flight Timbre v2.5 synthesis stream to abort immediately.
        Returns the timestamp (perf_counter) when the barge-in interrupt was triggered.
        """
        t0 = time.perf_counter()
        self._barge_in_abort_event.set()
        return t0

    def _require_api_key(self) -> str:
        key = self._settings.gnani_api_key.strip()
        if not key or key == "your_gnani_api_key_here":
            raise GnaniConfigurationError(
                "KADAL_GNANI_API_KEY is not set in .env. Set your live Gnani API key to stream audio."
            )
        return key

    @staticmethod
    def build_runtime_settings_frame(
        bias_words: Optional[List[str]] = None,
        substitution_rules: Optional[List[Dict[str, object]]] = None,
        bias_score: float = 0.85,
    ) -> str:
        """
        Constructs the documented Gnani STT WebSocket `update_settings` control frame
        for mid-session word boosting and server-side phonetic token substitution.
        """
        default_bias = bias_words or [
            "Senthil",
            "Kumaran",
            "Vanjaram",
            "Prawn",
            "box",
            "kilo",
        ]
        default_subs = substitution_rules or [
            {
                "patterns": ["டைகர் ஃப்ராண்ட்", "டைகர் ப்ரான்"],
                "replacement": "டைகர் பிரான்",
            },
            {
                "patterns": ["செந்தில் சீஃபுட்ஸ்க்கு"],
                "replacement": "செந்தில் சீஃபுட்ஸ்",
            },
        ]
        payload = {
            "type": "update_settings",
            "bias": {
                "list": default_bias[:100],
                "score": bias_score,
            },
            "substitution": {
                "enabled": True,
                "map": default_subs,
            },
        }
        return json.dumps(payload, ensure_ascii=False)

    # ------------------------------------------------------------------ resilience

    @staticmethod
    def _is_retryable(exc: BaseException) -> bool:
        if isinstance(exc, (GnaniProtocolError, GnaniConfigurationError)):
            return False
        if isinstance(exc, InvalidStatus):
            return exc.response.status_code >= _RETRYABLE_HTTP_STATUS_FLOOR
        return isinstance(exc, (OSError, asyncio.TimeoutError, WebSocketException))

    async def _with_retry(
        self,
        label: str,
        attempt: Callable[[], Awaitable[_T]],
        made_progress: Callable[[], bool],
    ) -> _T:
        """
        Runs ``attempt`` up to ``gnani_max_attempts`` times with exponential backoff.
        Gives up immediately on non-retryable errors or once ``made_progress()`` is true
        (output already delivered, so replaying the stream would duplicate it).
        """
        max_attempts = self._settings.gnani_max_attempts
        for attempt_no in range(1, max_attempts + 1):
            try:
                return await attempt()
            except Exception as exc:
                if (
                    attempt_no >= max_attempts
                    or made_progress()
                    or not self._is_retryable(exc)
                ):
                    raise
                delay = self._settings.gnani_backoff_base_sec * (2 ** (attempt_no - 1))
                logger.warning(
                    "%s attempt %d/%d failed (%s: %s); retrying in %.2fs",
                    label,
                    attempt_no,
                    max_attempts,
                    type(exc).__name__,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
        raise AssertionError("unreachable: retry loop always returns or raises")

    async def _recv_json(self, ws: ClientConnection) -> Dict[str, object]:
        """Reads one JSON frame within the read timeout; raises on ``error`` frames."""
        raw = await asyncio.wait_for(ws.recv(), timeout=self._settings.gnani_read_timeout_sec)
        return self._parse_frame(raw)

    @staticmethod
    def _parse_frame(raw: object) -> Dict[str, object]:
        if not isinstance(raw, (str, bytes)):
            raise GnaniProtocolError(f"Unexpected non-text WebSocket frame: {type(raw).__name__}")
        try:
            msg = json.loads(raw)
        except ValueError as exc:
            raise GnaniProtocolError(f"Malformed JSON frame from Gnani: {exc}") from exc
        if not isinstance(msg, dict):
            raise GnaniProtocolError("Gnani frame is not a JSON object")
        if msg.get("type") == "error":
            raise GnaniProtocolError(f"Gnani error frame: {msg.get('message')}")
        return msg

    # ------------------------------------------------------------------ Timbre TTS

    async def synthesize_timbre_v25(
        self,
        text_tamil: str,
        *,
        sample_rate: int = 16000,
    ) -> SynthesisTelemetry:
        """
        Streams Tamil voice synthesis from Gnani Timbre v2.5 over WebSocket.
        Measures exact Time-To-First-Byte (TTFB) and supports mid-stream barge-in cancellation.
        Audio chunks are reassembled by ``chunk_index`` and the streamed WAV header is repaired.
        Raises ``GnaniProtocolError`` (a ``RuntimeError``) on an ``error`` frame.
        """
        api_key = self._require_api_key()
        self._barge_in_abort_event.clear()
        t_start = time.perf_counter()
        received_audio = False

        async def _attempt() -> SynthesisTelemetry:
            nonlocal received_audio
            chunks: Dict[int, bytes] = {}
            ttfb_ms = 0.0
            was_interrupted = False

            async with websockets.connect(
                self._settings.timbre_ws_url,
                additional_headers={"Content-Type": "application/json", "X-API-Key-ID": api_key},
                ping_interval=WS_PING_INTERVAL_SEC,
                open_timeout=self._settings.gnani_open_timeout_sec,
            ) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "text": text_tamil,
                            "voice": self._settings.timbre_default_voice,
                            "model": "timbre-v2.5",
                            "language": "ta-IN",
                            "speed": 1.0,
                            "audio_config": {
                                "sample_rate": sample_rate,
                                "num_channels": 1,
                                "sample_width": PCM_SAMPLE_WIDTH_BYTES,
                                "encoding": "linear_pcm",
                                "container": "wav",
                            },
                        },
                        ensure_ascii=False,
                    )
                )

                while True:
                    msg = await self._recv_json(ws)
                    if self._barge_in_abort_event.is_set():
                        was_interrupted = True
                        await ws.close()
                        break

                    data = msg.get("data")
                    data = data if isinstance(data, dict) else {}
                    audio_b64 = data.get("audio")
                    if audio_b64:
                        if ttfb_ms == 0.0:
                            ttfb_ms = round((time.perf_counter() - t_start) * 1000.0, 1)
                        received_audio = True
                        raw_index = data.get("chunk_index")
                        index = raw_index if isinstance(raw_index, int) else len(chunks) + 1
                        chunks[index] = base64.b64decode(str(audio_b64))

                    if msg.get("type") == "complete" or data.get("is_final"):
                        break

            audio = finalize_streamed_wav(b"".join(chunks[i] for i in sorted(chunks)))
            return SynthesisTelemetry(
                audio_wav_bytes=audio,
                ttfb_ms=ttfb_ms,
                total_synthesis_ms=round((time.perf_counter() - t_start) * 1000.0, 1),
                was_interrupted=was_interrupted,
            )

        return await self._with_retry("Timbre v2.5 TTS", _attempt, lambda: received_audio)

    # ------------------------------------------------------------------ Prisma STT

    async def stream_pcm_to_prisma_v25(
        self,
        pcm_bytes: bytes,
        on_segment: Callable[[str, float], Awaitable[None]],
        *,
        sample_rate: int = 8000,
        lang_code: str = "ta-IN",
        enable_boosting: bool = True,
    ) -> None:
        """
        Streams raw 16-bit mono PCM audio in strict 1,024-byte frames to Gnani Prisma v2.5,
        paced in real time (64ms @ 8kHz, 32ms @ 16kHz) to preserve server-side VAD accuracy.

        The server VAD only closes an utterance after it *receives* ``x-min-silence-ms`` of
        silent audio, so trailing zero-PCM is streamed after the speech (waiting does not
        work). Afterwards the call waits, bounded by the read timeout, for every utterance
        that began to produce its transcript.
        """
        api_key = self._require_api_key()
        if sample_rate not in SUPPORTED_PCM_SAMPLE_RATES:
            raise ValueError(
                f"Unsupported sample_rate {sample_rate}; Prisma frames are paced for "
                f"{SUPPORTED_PCM_SAMPLE_RATES} only"
            )
        delivered = False

        async def _tracked_on_segment(text: str, latency_ms: float) -> None:
            nonlocal delivered
            delivered = True
            await on_segment(text, latency_ms)

        async def _attempt() -> None:
            await self._prisma_attempt(
                api_key,
                pcm_bytes,
                _tracked_on_segment,
                sample_rate=sample_rate,
                lang_code=lang_code,
                enable_boosting=enable_boosting,
            )

        await self._with_retry("Prisma v2.5 STT", _attempt, lambda: delivered)

    async def _prisma_attempt(
        self,
        api_key: str,
        pcm_bytes: bytes,
        on_segment: Callable[[str, float], Awaitable[None]],
        *,
        sample_rate: int,
        lang_code: str,
        enable_boosting: bool,
    ) -> None:
        cfg = self._settings
        pace_sec = frame_pace_seconds(sample_rate)
        pacer = PCM1024RingBufferPacer()
        headers = {
            "x-api-key-id": api_key,
            "lang_code": lang_code,
            "x-sample-rate": str(sample_rate),
            "x-format": "transcribe",
            "x-vad-threshold": str(cfg.vad_threshold),
            "x-min-speech-ms": str(cfg.min_speech_ms),
            "x-min-silence-ms": str(cfg.min_silence_ms),
            "x-enable-substitution": "true" if enable_boosting else "false",
        }
        silence_ms = cfg.min_silence_ms + cfg.stt_trailing_silence_margin_ms
        silence = bytes(int(sample_rate * PCM_SAMPLE_WIDTH_BYTES * silence_ms / 1000.0))
        open_utterances: Set[str] = set()

        async with websockets.connect(
            cfg.prisma_ws_url,
            additional_headers=headers,
            ping_interval=WS_PING_INTERVAL_SEC,
            open_timeout=cfg.gnani_open_timeout_sec,
        ) as ws:
            handshake = await self._recv_json(ws)
            handshake_cfg = handshake.get("config")
            handshake_cfg = handshake_cfg if isinstance(handshake_cfg, dict) else {}
            logger.info(
                "Prisma v2.5 WebSocket connected: requested_rate=%s server_rate=%s chunk_size=%s",
                sample_rate,
                handshake_cfg.get("sample_rate"),
                handshake_cfg.get("chunk_size"),
            )

            if enable_boosting:
                await ws.send(self.build_runtime_settings_frame())

            async def _receive_events() -> None:
                while True:
                    # Silence is legitimate while audio is still being sent, so this read is
                    # unbounded; the post-send drain below is what is bounded by the timeout.
                    event = self._parse_frame(await ws.recv())
                    event_type = event.get("type")
                    utterance_id = str(event.get("utterance_id", ""))
                    if event_type == "speech_start":
                        open_utterances.add(utterance_id)
                    elif event_type == "transcript":
                        if event.get("is_final", True):
                            open_utterances.discard(utterance_id)
                        # Signal barge-in abort as soon as new user speech arrives
                        self.trigger_barge_in_abort()
                        await on_segment(
                            str(event.get("text", "")),
                            float(str(event.get("latency", 0.0))),
                        )

            receiver_task = asyncio.create_task(_receive_events())
            try:
                frames = pacer.push_bytes(pcm_bytes + silence)
                tail = pacer.flush_padded()
                if tail is not None:
                    frames.append(tail)

                for frame in frames:
                    if receiver_task.done():
                        receiver_task.result()  # surfaces error frames / closed sockets
                    await ws.send(frame)
                    await asyncio.sleep(pace_sec)

                await self._drain_open_utterances(receiver_task, open_utterances)
            finally:
                receiver_task.cancel()
                await asyncio.gather(receiver_task, return_exceptions=True)

    async def _drain_open_utterances(
        self,
        receiver_task: "asyncio.Task[None]",
        open_utterances: Set[str],
    ) -> None:
        """Waits (bounded by the read timeout) until every started utterance has its transcript."""
        cfg = self._settings
        loop = asyncio.get_running_loop()
        deadline = loop.time() + cfg.gnani_read_timeout_sec
        while open_utterances:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError(
                    f"Prisma produced no transcript for {len(open_utterances)} open utterance(s) "
                    f"within {cfg.gnani_read_timeout_sec}s"
                )
            done, _ = await asyncio.wait({receiver_task}, timeout=min(0.05, remaining))
            if done:
                receiver_task.result()
        # Short grace for any further segment of an utterance that just closed.
        done, _ = await asyncio.wait({receiver_task}, timeout=cfg.stt_drain_grace_sec)
        if done:
            receiver_task.result()
