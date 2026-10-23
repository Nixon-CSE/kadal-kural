"""
Pipecat-Architecture Frame Pipeline for Kadal Kural.
Implements typed FrameProcessors (InputAudioRawFrame -> StartInterruptionFrame ->
TranscriptionFrame -> CreditDecisionFrame -> TTSAudioRawFrame) compatible with
Gnani AI's Artha WebSocket stack and Python 3.9+.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

from kadal_kural.domain.models import CreditGateDecision
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.gnani_client import (
    GnaniArthaSpeechClient,
    MultiSegmentTradeAssembler,
    PCM1024RingBufferPacer,
)


@dataclass(frozen=True)
class Frame:
    """Base immutable pipeline frame."""

    timestamp_ns: int = field(default_factory=time.perf_counter_ns)


@dataclass(frozen=True)
class InputAudioRawFrame(Frame):
    """Raw 16-bit mono PCM audio chunk entering the pipeline."""

    pcm_bytes: bytes = b""
    sample_rate: int = 8000


@dataclass(frozen=True)
class StartInterruptionFrame(Frame):
    """Emitted when user speech barges in over active Timbre v2.5 playback."""

    reason: str = "user_barge_in"


@dataclass(frozen=True)
class TranscriptionFrame(Frame):
    """Emitted by Gnani Prisma v2.5 upon completing a VAD speech segment."""

    text: str = ""
    stt_latency_ms: float = 0.0


@dataclass(frozen=True)
class CreditDecisionFrame(Frame):
    """Emitted by the deterministic Pre-Dispatch Credit Firewall."""

    decisions: List[CreditGateDecision] = field(default_factory=list)


@dataclass(frozen=True)
class TTSAudioRawFrame(Frame):
    """Synthesized Tamil WAV audio frame emitted by Gnani Timbre v2.5."""

    decision: Optional[CreditGateDecision] = None
    wav_bytes: bytes = b""
    ttfb_ms: float = 0.0


class PipecatArthaPipelineRunner:
    """
    Orchestrates the end-to-end voice frame pipeline:
    1. Paces InputAudioRawFrames into 1,024-byte chunks for Prisma v2.5.
    2. Flushes active TTS playback buffer on StartInterruptionFrame (Barge-In).
    3. Stitches multi-segment utterances via MultiSegmentTradeAssembler.
    4. Evaluates deterministic credit limits via PreDispatchCreditFirewallService.
    5. Streams spoken Tamil alerts via Timbre v2.5 when live TTS is enabled.
    """

    def __init__(
        self,
        firewall_service: PreDispatchCreditFirewallService,
        speech_client: GnaniArthaSpeechClient,
        *,
        assembler_window_sec: float = 1.5,
        on_decision_emitted: Optional[Callable[[CreditDecisionFrame], Awaitable[None]]] = None,
        on_tts_emitted: Optional[Callable[[TTSAudioRawFrame], Awaitable[None]]] = None,
    ) -> None:
        self._firewall = firewall_service
        self._speech_client = speech_client
        self._on_decision_emitted = on_decision_emitted
        self._on_tts_emitted = on_tts_emitted
        self._pacer = PCM1024RingBufferPacer()
        self._tts_playback_queue: asyncio.Queue[TTSAudioRawFrame] = asyncio.Queue()
        self.last_barge_in_flush_ms: float = 0.0

        self._assembler = MultiSegmentTradeAssembler(
            window_sec=assembler_window_sec,
            on_commit=self._handle_assembled_utterance,
        )

    async def push_frame(self, frame: Frame, *, synthesize_live_tts: bool = False) -> None:
        """Routes a typed frame through the Kadal Kural processor chain."""
        if isinstance(frame, StartInterruptionFrame):
            await self._handle_interruption(frame)
            return

        if isinstance(frame, TranscriptionFrame):
            # If TTS is currently queued, user speech automatically triggers barge-in flush
            if not self._tts_playback_queue.empty():
                await self._handle_interruption(StartInterruptionFrame(reason="vad_speech_detected"))
            await self._assembler.ingest_segment(frame.text, frame.stt_latency_ms)
            return

        if isinstance(frame, InputAudioRawFrame):
            # Slice arbitrary PCM chunk into strict 1,024-byte Gnani STT frames
            _ = self._pacer.push_bytes(frame.pcm_bytes)

    async def flush_assembler(self, *, synthesize_live_tts: bool = False) -> CreditDecisionFrame:
        """Forces immediate commit of buffered transcript segments and returns the decision frame."""
        self._synthesize_flag = synthesize_live_tts
        await self._assembler.flush_immediately()
        return getattr(self, "_last_decision_frame", CreditDecisionFrame(decisions=[]))

    async def _handle_interruption(self, frame: StartInterruptionFrame) -> float:
        """Flushes all queued TTS audio frames and signals Gnani Timbre v2.5 stream abort."""
        t0 = self._speech_client.trigger_barge_in_abort()
        while not self._tts_playback_queue.empty():
            try:
                self._tts_playback_queue.get_nowait()
                self._tts_playback_queue.task_done()
            except asyncio.QueueEmpty:
                break
        self.last_barge_in_flush_ms = round((time.perf_counter() - t0) * 1000.0, 4)
        return self.last_barge_in_flush_ms

    async def _handle_assembled_utterance(self, merged_text: str, mean_stt_ms: float) -> None:
        decisions = self._firewall.evaluate_utterance(merged_text, stt_latency_ms=mean_stt_ms)
        decision_frame = CreditDecisionFrame(decisions=decisions)
        self._last_decision_frame = decision_frame

        if self._on_decision_emitted is not None:
            await self._on_decision_emitted(decision_frame)

        if getattr(self, "_synthesize_flag", False):
            for dec in decisions:
                telemetry = await self._speech_client.synthesize_timbre_v25(dec.tts_response_tamil)
                tts_frame = TTSAudioRawFrame(
                    decision=dec,
                    wav_bytes=telemetry.audio_wav_bytes,
                    ttfb_ms=telemetry.ttfb_ms,
                )
                await self._tts_playback_queue.put(tts_frame)
                if self._on_tts_emitted is not None:
                    await self._on_tts_emitted(tts_frame)
