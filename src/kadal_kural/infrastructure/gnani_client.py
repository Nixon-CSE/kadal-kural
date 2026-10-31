"""
Production WebSocket adapters for Gnani AI's Sovereign Artha Stack:
- Prisma v2.5 Streaming Speech-to-Text (wss://api.vachana.ai/stt/v3/stream)
- Timbre v2.5 Streaming Text-to-Speech (wss://api.vachana.ai/api/v1/tts)

Enforces strict 1,024-byte binary PCM frame pacing, mid-session vocabulary boosting,
and barge-in TTS stream cancellation (abort -> socket closed P50 52.3 ms / P95 52.5 ms over
24 live trials; measured: see benchmark/REPORT.md).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import struct
import time
from dataclasses import dataclass, replace
from typing import Awaitable, Callable, Dict, List, Optional, Set, Tuple, TypeVar

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import InvalidStatus, WebSocketException

from kadal_kural.config import (
    NS_PER_MS,
    PCM_FRAME_BYTES,
    PCM_SAMPLE_WIDTH_BYTES,
    SUPPORTED_PCM_SAMPLE_RATES,
    TIMBRE_CLOSE_TIMEOUT_SEC,
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
    abort_to_close_ms: Optional[float] = None  # trigger_barge_in_abort() -> socket closed


@dataclass(frozen=True)
class PrismaEventTiming:
    """One Prisma event as the client saw it, timed against the last audio frame sent."""

    event_type: str
    utterance_id: str
    received_after_audio_end_ms: float  # negative while audio was still being sent
    reported_latency_ms: Optional[float]  # Prisma's own 'latency' field (transcripts only)
    is_final: Optional[bool]


@dataclass(frozen=True)
class PrismaStreamTelemetry:
    """Client-side timing of one Prisma v2.5 stream (the final, successful attempt)."""

    attempts: int
    connect_ms: float  # WebSocket open + handshake frame
    audio_send_ms: float  # first audio frame -> last audio frame sent (real-time paced)
    drain_ms: float  # last audio frame sent -> every started utterance transcribed (+ grace)
    events: Tuple[PrismaEventTiming, ...]

    @property
    def final_transcript_after_audio_ms(self) -> Optional[float]:
        """When the last final transcript arrived, measured from the last audio frame sent."""
        finals = [
            e.received_after_audio_end_ms
            for e in self.events
            if e.event_type == "transcript" and e.is_final is not False
        ]
        return max(finals) if finals else None


def _elapsed_ms(start_ns: int, end_ns: int) -> float:
    return (end_ns - start_ns) / NS_PER_MS


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


@dataclass(frozen=True)
class AssembledUtterance:
    """The VAD segments stitched into one utterance, with when the first and last arrived."""

    text: str
    segment_latencies_ms: Tuple[float, ...]  # Prisma-reported, one per segment
    first_segment_ns: int  # time.perf_counter_ns() when the first segment was received
    last_segment_ns: int

    @property
    def mean_stt_latency_ms(self) -> float:
        return round(sum(self.segment_latencies_ms) / max(1, len(self.segment_latencies_ms)), 1)


class MultiSegmentTradeAssembler:
    """
    Stitches consecutive VAD speech segments across a sliding window (AppSettings.assembler_window_sec)
    so multi-trade single-breath utterances split by a brief breath pause are evaluated atomically.
    """

    def __init__(
        self,
        window_sec: float,
        on_commit: Callable[[AssembledUtterance], Awaitable[None]],
        clock: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self._window_sec = window_sec
        self._on_commit = on_commit
        self._clock = clock
        self._segments: List[str] = []
        self._latencies_ms: List[float] = []
        self._received_ns: List[int] = []
        self._flush_task: Optional[asyncio.Task[None]] = None

    async def ingest_segment(
        self, transcript: str, stt_latency_ms: float, received_ns: Optional[int] = None
    ) -> None:
        """Buffers a VAD segment (received at ``received_ns``, default now) and restarts the window."""
        cleaned = transcript.strip()
        if not cleaned:
            return
        self._segments.append(cleaned)
        self._latencies_ms.append(stt_latency_ms)
        self._received_ns.append(self._clock() if received_ns is None else received_ns)
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
        utterance = AssembledUtterance(
            text=" ".join(self._segments),
            segment_latencies_ms=tuple(self._latencies_ms),
            first_segment_ns=self._received_ns[0],
            last_segment_ns=self._received_ns[-1],
        )
        self._segments.clear()
        self._latencies_ms.clear()
        self._received_ns.clear()
        await self._on_commit(utterance)


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
        self._abort_triggered_ns = 0

    def trigger_barge_in_abort(self) -> float:
        """
        Signals any in-flight Timbre v2.5 synthesis stream to abort; its socket is closed without
        waiting for the next frame, and the close handshake is capped at TIMBRE_CLOSE_TIMEOUT_SEC
        (measured abort -> closed: P50 52.3 ms / P95 52.5 ms, see benchmark/REPORT.md).
        Returns the timestamp (perf_counter) when the barge-in interrupt was triggered.
        """
        t0 = time.perf_counter()
        self._abort_triggered_ns = time.perf_counter_ns()
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
        on_first_audio: Optional[Callable[[], None]] = None,
    ) -> SynthesisTelemetry:
        """
        Streams Tamil voice synthesis from Gnani Timbre v2.5 over WebSocket.
        Measures exact Time-To-First-Byte (TTFB) and supports mid-stream barge-in cancellation.
        Audio chunks are reassembled by ``chunk_index`` and the streamed WAV header is repaired.
        ``on_first_audio`` is called once, as soon as the first audio chunk arrives.
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
            abort_to_close_ms: Optional[float] = None

            async with websockets.connect(
                self._settings.timbre_ws_url,
                additional_headers={"Content-Type": "application/json", "X-API-Key-ID": api_key},
                ping_interval=WS_PING_INTERVAL_SEC,
                open_timeout=self._settings.gnani_open_timeout_sec,
                close_timeout=TIMBRE_CLOSE_TIMEOUT_SEC,
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

                # Wait for the next frame *or* the barge-in abort, whichever comes first, so an
                # abort never waits for Timbre's next chunk (or for the read timeout).
                abort_waiter = asyncio.ensure_future(self._barge_in_abort_event.wait())
                try:
                    while True:
                        next_frame = asyncio.ensure_future(self._recv_json(ws))
                        await asyncio.wait({next_frame, abort_waiter}, return_when=asyncio.FIRST_COMPLETED)
                        if self._barge_in_abort_event.is_set():
                            next_frame.cancel()
                            await asyncio.gather(next_frame, return_exceptions=True)
                            was_interrupted = True
                            await ws.close()
                            abort_to_close_ms = _elapsed_ms(self._abort_triggered_ns, time.perf_counter_ns())
                            break
                        msg = next_frame.result()

                        data = msg.get("data")
                        data = data if isinstance(data, dict) else {}
                        audio_b64 = data.get("audio")
                        if audio_b64:
                            if ttfb_ms == 0.0:
                                ttfb_ms = round((time.perf_counter() - t_start) * 1000.0, 1)
                                if on_first_audio is not None:
                                    on_first_audio()
                            received_audio = True
                            raw_index = data.get("chunk_index")
                            index = raw_index if isinstance(raw_index, int) else len(chunks) + 1
                            chunks[index] = base64.b64decode(str(audio_b64))

                        if msg.get("type") == "complete" or data.get("is_final"):
                            break
                finally:
                    abort_waiter.cancel()
                    await asyncio.gather(abort_waiter, return_exceptions=True)

            audio = finalize_streamed_wav(b"".join(chunks[i] for i in sorted(chunks)))
            return SynthesisTelemetry(
                audio_wav_bytes=audio,
                ttfb_ms=ttfb_ms,
                total_synthesis_ms=round((time.perf_counter() - t_start) * 1000.0, 1),
                was_interrupted=was_interrupted,
                abort_to_close_ms=abort_to_close_ms,
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
        append_trailing_silence: bool = True,
    ) -> PrismaStreamTelemetry:
        """
        Streams raw 16-bit mono PCM audio in strict 1,024-byte frames to Gnani Prisma v2.5,
        paced in real time (64ms @ 8kHz, 32ms @ 16kHz) to preserve server-side VAD accuracy.

        The server VAD only closes an utterance after it *receives* ``x-min-silence-ms`` of
        silent audio, so trailing zero-PCM is streamed after the speech (waiting does not
        work). Afterwards the call waits, bounded by the read timeout, for every utterance
        that began to produce its transcript. Pass ``append_trailing_silence=False`` when the
        caller supplies its own tail (e.g. noise-only audio) so the VAD sees it instead.

        Returns the client-side timing of the successful attempt (connect, audio send, drain,
        and when each Prisma event arrived relative to the last audio frame sent).
        """
        api_key = self._require_api_key()
        if sample_rate not in SUPPORTED_PCM_SAMPLE_RATES:
            raise ValueError(
                f"Unsupported sample_rate {sample_rate}; Prisma frames are paced for "
                f"{SUPPORTED_PCM_SAMPLE_RATES} only"
            )
        delivered = False
        attempts = 0

        async def _tracked_on_segment(text: str, latency_ms: float) -> None:
            nonlocal delivered
            delivered = True
            await on_segment(text, latency_ms)

        async def _attempt() -> PrismaStreamTelemetry:
            nonlocal attempts
            attempts += 1
            return await self._prisma_attempt(
                api_key,
                pcm_bytes,
                _tracked_on_segment,
                sample_rate=sample_rate,
                lang_code=lang_code,
                enable_boosting=enable_boosting,
                append_trailing_silence=append_trailing_silence,
            )

        telemetry = await self._with_retry("Prisma v2.5 STT", _attempt, lambda: delivered)
        return replace(telemetry, attempts=attempts)

    async def _prisma_attempt(
        self,
        api_key: str,
        pcm_bytes: bytes,
        on_segment: Callable[[str, float], Awaitable[None]],
        *,
        sample_rate: int,
        lang_code: str,
        enable_boosting: bool,
        append_trailing_silence: bool,
    ) -> PrismaStreamTelemetry:
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
        silence = (
            bytes(int(sample_rate * PCM_SAMPLE_WIDTH_BYTES * silence_ms / 1000.0))
            if append_trailing_silence
            else b""
        )
        open_utterances: Set[str] = set()
        # (received ns, type, utterance id, reported latency ms, is_final) per Prisma event
        event_log: List[Tuple[int, str, str, Optional[float], Optional[bool]]] = []
        connect_start_ns = time.perf_counter_ns()

        async with websockets.connect(
            cfg.prisma_ws_url,
            additional_headers=headers,
            ping_interval=WS_PING_INTERVAL_SEC,
            open_timeout=cfg.gnani_open_timeout_sec,
        ) as ws:
            handshake = await self._recv_json(ws)
            connected_ns = time.perf_counter_ns()
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
                    raw = await ws.recv()
                    received_ns = time.perf_counter_ns()
                    event = self._parse_frame(raw)
                    event_type = event.get("type")
                    utterance_id = str(event.get("utterance_id", ""))
                    if event_type == "speech_start":
                        open_utterances.add(utterance_id)
                        event_log.append((received_ns, "speech_start", utterance_id, None, None))
                    elif event_type == "transcript":
                        logger.debug("Prisma raw transcript event: %s", event)
                        is_final = bool(event.get("is_final", True))
                        if is_final:
                            open_utterances.discard(utterance_id)
                        reported_ms = float(str(event.get("latency", 0.0)))
                        event_log.append((received_ns, "transcript", utterance_id, reported_ms, is_final))
                        # Signal barge-in abort as soon as new user speech arrives
                        self.trigger_barge_in_abort()
                        await on_segment(str(event.get("text", "")), reported_ms)
                    else:
                        event_log.append((received_ns, str(event_type), utterance_id, None, None))

            receiver_task = asyncio.create_task(_receive_events())
            try:
                frames = pacer.push_bytes(pcm_bytes + silence)
                tail = pacer.flush_padded()
                if tail is not None:
                    frames.append(tail)

                audio_start_ns = last_sent_ns = time.perf_counter_ns()
                for frame in frames:
                    if receiver_task.done():
                        receiver_task.result()  # surfaces error frames / closed sockets
                    await ws.send(frame)
                    last_sent_ns = time.perf_counter_ns()
                    await asyncio.sleep(pace_sec)

                await self._drain_open_utterances(receiver_task, open_utterances)
                drained_ns = time.perf_counter_ns()
            finally:
                receiver_task.cancel()
                await asyncio.gather(receiver_task, return_exceptions=True)

        return PrismaStreamTelemetry(
            attempts=1,
            connect_ms=_elapsed_ms(connect_start_ns, connected_ns),
            audio_send_ms=_elapsed_ms(audio_start_ns, last_sent_ns),
            drain_ms=_elapsed_ms(last_sent_ns, drained_ns),
            events=tuple(
                PrismaEventTiming(
                    event_type=kind,
                    utterance_id=uid,
                    received_after_audio_end_ms=_elapsed_ms(last_sent_ns, received_ns),
                    reported_latency_ms=reported_ms,
                    is_final=is_final,
                )
                for received_ns, kind, uid, reported_ms, is_final in event_log
            ),
        )

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
