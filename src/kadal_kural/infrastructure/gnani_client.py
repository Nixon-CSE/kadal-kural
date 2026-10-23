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
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional, Tuple
import websockets
from websockets.exceptions import ConnectionClosed

from kadal_kural.config import AppSettings

logger = logging.getLogger(__name__)

MANDATORY_PCM_FRAME_BYTES: int = 1024
PACE_INTERVAL_8KHZ_SEC: float = 0.064
PACE_INTERVAL_16KHZ_SEC: float = 0.032


class GnaniConfigurationError(RuntimeError):
    """Raised when a live Gnani API call is attempted without a configured API key."""


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
        self._buffer.extend(raw_pcm)
        frames: List[bytes] = []
        while len(self._buffer) >= MANDATORY_PCM_FRAME_BYTES:
            frames.append(bytes(self._buffer[:MANDATORY_PCM_FRAME_BYTES]))
            del self._buffer[:MANDATORY_PCM_FRAME_BYTES]
        return frames

    def flush_padded(self) -> Optional[bytes]:
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
        cleaned = transcript.strip()
        if not cleaned:
            return
        self._segments.append(cleaned)
        self._latencies_ms.append(stt_latency_ms)
        if self._flush_task is not None and not self._flush_task.done():
            self._flush_task.cancel()
        self._flush_task = asyncio.create_task(self._wait_and_flush())

    async def flush_immediately(self) -> None:
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


class GnaniArthaSpeechClient:
    """
    Production client for Gnani Prisma v2.5 STT and Timbre v2.5 TTS over WebSocket.
    Contains zero mocked responses; every method communicates with api.vachana.ai.
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
            "word_boosting": {
                "enabled": True,
                "words": default_bias[:100],
                "score": bias_score,
            },
            "substitution": {
                "enabled": True,
                "map": default_subs,
            },
        }
        return json.dumps(payload, ensure_ascii=False)

    async def synthesize_timbre_v25(
        self,
        text_tamil: str,
        *,
        sample_rate: int = 16000,
    ) -> SynthesisTelemetry:
        """
        Streams Tamil voice synthesis from Gnani Timbre v2.5 over WebSocket.
        Measures exact Time-To-First-Byte (TTFB) and supports mid-stream barge-in cancellation.
        """
        api_key = self._require_api_key()
        self._barge_in_abort_event.clear()

        headers = {
            "Content-Type": "application/json",
            "X-API-Key-ID": api_key,
        }
        t_start = time.perf_counter()
        ttfb_ms = 0.0
        audio_buffer = bytearray()
        was_interrupted = False

        async with websockets.connect(
            self._settings.timbre_ws_url,
            additional_headers=headers,
            ping_interval=20,
        ) as ws:
            request_payload = {
                "text": text_tamil,
                "voice": self._settings.timbre_default_voice,
                "model": "timbre-v2.5",
                "language": "ta-IN",
                "speed": 1.0,
                "audio_config": {
                    "sample_rate": sample_rate,
                    "num_channels": 1,
                    "sample_width": 2,
                    "encoding": "linear_pcm",
                    "container": "wav",
                },
            }
            await ws.send(json.dumps(request_payload, ensure_ascii=False))

            async for raw_frame in ws:
                if self._barge_in_abort_event.is_set():
                    was_interrupted = True
                    await ws.close()
                    break

                msg = json.loads(raw_frame)
                audio_b64 = msg.get("audio")
                if audio_b64:
                    if ttfb_ms == 0.0:
                        ttfb_ms = round((time.perf_counter() - t_start) * 1000.0, 1)
                    audio_buffer.extend(base64.b64decode(audio_b64))
                if msg.get("is_final"):
                    break

        total_ms = round((time.perf_counter() - t_start) * 1000.0, 1)
        return SynthesisTelemetry(
            audio_wav_bytes=bytes(audio_buffer),
            ttfb_ms=ttfb_ms,
            total_synthesis_ms=total_ms,
            was_interrupted=was_interrupted,
        )

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
        Streams raw 16-bit mono PCM audio in strict 1,024-byte frames to Gnani Prisma v2.5.
        Paces frames at 64ms (for 8kHz) or 32ms (for 16kHz) to preserve server-side VAD accuracy.
        """
        api_key = self._require_api_key()
        pace_sec = PACE_INTERVAL_8KHZ_SEC if sample_rate == 8000 else PACE_INTERVAL_16KHZ_SEC
        pacer = PCM1024RingBufferPacer()

        headers = {
            "x-api-key-id": api_key,
            "lang_code": lang_code,
            "x-sample-rate": str(sample_rate),
            "x-format": "transcribe",
            "x-vad-threshold": str(self._settings.vad_threshold),
            "x-min-speech-ms": str(self._settings.min_speech_ms),
            "x-min-silence-ms": str(self._settings.min_silence_ms),
            "x-enable-substitution": "true" if enable_boosting else "false",
        }

        async with websockets.connect(
            self._settings.prisma_ws_url,
            additional_headers=headers,
            ping_interval=20,
        ) as ws:
            handshake = json.loads(await ws.recv())
            logger.info("Prisma v2.5 WebSocket connected: session_id=%s", handshake.get("id"))

            if enable_boosting:
                await ws.send(self.build_runtime_settings_frame())

            async def _receive_transcripts() -> None:
                try:
                    async for raw_msg in ws:
                        event = json.loads(raw_msg)
                        if event.get("type") == "transcript":
                            # Signal barge-in abort as soon as new user speech arrives
                            self.trigger_barge_in_abort()
                            await on_segment(
                                str(event.get("text", "")),
                                float(event.get("latency", 0.0)),
                            )
                except ConnectionClosed:
                    return

            receiver_task = asyncio.create_task(_receive_transcripts())
            try:
                frames = pacer.push_bytes(pcm_bytes)
                tail = pacer.flush_padded()
                if tail is not None:
                    frames.append(tail)

                for frame in frames:
                    await ws.send(frame)
                    await asyncio.sleep(pace_sec)

                # Wait briefly for trailing silence window (x-min-silence-ms) to emit final segment
                await asyncio.sleep((self._settings.min_silence_ms / 1000.0) + 0.35)
            finally:
                receiver_task.cancel()
