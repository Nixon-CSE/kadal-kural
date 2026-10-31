"""
One voice turn on the live path: the firewall's decisions for an utterance, the spoken
Timbre replies, and exactly one structured JSON timing line, all on a single timeline per
utterance (STT segment received -> assemble -> normalize -> match -> decide -> Timbre first
byte). Shared by the FastAPI gateway and the Pipecat-style pipeline runner.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional, Protocol, Sequence, Tuple

from kadal_kural.config import (
    SPAN_ASSEMBLE,
    SPAN_TIMBRE_FIRST_BYTE,
    TIMING_ORIGIN_FIRST_SEGMENT,
    TIMING_ORIGIN_REQUEST,
)
from kadal_kural.domain.models import CreditGateDecision
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.domain.telemetry import PipelineTelemetry, UtteranceEvaluation
from kadal_kural.infrastructure.gnani_client import SynthesisTelemetry
from kadal_kural.infrastructure.timing import (
    NanosecondClock,
    PerfCounterSpanRecorder,
    log_utterance_timing,
    utterance_timing_record,
)


class SpeechSynthesizer(Protocol):
    """The slice of GnaniArthaSpeechClient a voice turn needs (tests pass a fake)."""

    async def synthesize_timbre_v25(
        self, text_tamil: str, *, on_first_audio: Optional[Callable[[], None]] = None
    ) -> SynthesisTelemetry: ...


@dataclass(frozen=True)
class VoiceTurn:
    """Decisions, one reply per decision (None when not synthesized), and the full timeline."""

    evaluation: UtteranceEvaluation
    replies: Tuple[Optional[SynthesisTelemetry], ...]
    telemetry: PipelineTelemetry
    log_line: str


async def run_voice_turn(
    firewall: PreDispatchCreditFirewallService,
    speech: SpeechSynthesizer,
    transcript: str,
    *,
    path: str,
    stt_latencies_ms: Sequence[float] = (),
    first_segment_ns: Optional[int] = None,
    decision_stt_latency_ms: Optional[float] = None,
    synthesize: bool = True,
    on_evaluated: Optional[Callable[[UtteranceEvaluation], Awaitable[None]]] = None,
    on_reply: Optional[Callable[[CreditGateDecision, SynthesisTelemetry], Awaitable[None]]] = None,
    clock: NanosecondClock = time.perf_counter_ns,
) -> VoiceTurn:
    """
    Evaluates ``transcript`` and (if ``synthesize``) speaks every decision. The timeline's
    origin is ``first_segment_ns`` (perf_counter_ns when the first STT segment arrived) or,
    when there was no STT, the moment this is called. ``stt_latencies_ms`` are the
    Prisma-reported per-segment latencies; their mean is stamped on the decisions unless
    ``decision_stt_latency_ms`` overrides it. One JSON timing line is logged even when a
    synthesis fails part-way.
    """
    now_ns = clock()
    spans = PerfCounterSpanRecorder(clock, origin_ns=now_ns if first_segment_ns is None else first_segment_ns)
    if first_segment_ns is not None:
        spans.record_span(SPAN_ASSEMBLE, first_segment_ns, now_ns)
    if decision_stt_latency_ms is None:
        decision_stt_latency_ms = (
            round(sum(stt_latencies_ms) / len(stt_latencies_ms), 1) if stt_latencies_ms else 0.0
        )

    evaluation = firewall.evaluate_utterance_timed(transcript, stt_latency_ms=decision_stt_latency_ms, spans=spans)
    replies: List[Optional[SynthesisTelemetry]] = []
    try:
        if on_evaluated is not None:
            await on_evaluated(evaluation)
        for index, decision in enumerate(evaluation.decisions):
            if not synthesize:
                replies.append(None)
                continue
            on_first_audio: Optional[Callable[[], None]] = None
            if index == 0:
                spans.start(SPAN_TIMBRE_FIRST_BYTE)
                on_first_audio = lambda: spans.stop(SPAN_TIMBRE_FIRST_BYTE)  # noqa: E731
            reply = await speech.synthesize_timbre_v25(decision.tts_response_tamil, on_first_audio=on_first_audio)
            replies.append(reply)
            if on_reply is not None:
                await on_reply(decision, reply)
    finally:
        telemetry = spans.telemetry()
        log_line = log_utterance_timing(
            utterance_timing_record(
                path=path,
                origin=TIMING_ORIGIN_REQUEST if first_segment_ns is None else TIMING_ORIGIN_FIRST_SEGMENT,
                telemetry=telemetry,
                stt_reported_latency_ms=stt_latencies_ms,
                statuses=[d.status.value for d in evaluation.decisions],
            )
        )
    return VoiceTurn(evaluation=evaluation, replies=tuple(replies), telemetry=telemetry, log_line=log_line)
