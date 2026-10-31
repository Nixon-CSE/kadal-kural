"""
Recording SpanRecorder backed by the monotonic time.perf_counter_ns clock, and the one
structured JSON timing line logged per utterance on the live path.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from kadal_kural.config import (
    NS_PER_MS,
    SPAN_TIMBRE_FIRST_BYTE,
    TIMING_LOG_DECIMALS,
    TIMING_LOGGER_NAME,
    UTTERANCE_TIMING_EVENT,
)
from kadal_kural.domain.telemetry import PipelineTelemetry, SpanTiming

NanosecondClock = Callable[[], int]

timing_logger = logging.getLogger(TIMING_LOGGER_NAME)


class PerfCounterSpanRecorder:
    """
    Records named spans for one utterance against a monotonic nanosecond clock
    (time.perf_counter_ns unless a test injects a fake one). Span offsets are relative to
    ``origin_ns``, which defaults to the clock reading taken when the recorder is created.
    Starting a running span or stopping one that never started is a programming error and
    raises ValueError.
    """

    def __init__(self, clock: NanosecondClock = time.perf_counter_ns, origin_ns: Optional[int] = None) -> None:
        self._clock = clock
        self.origin_ns = clock() if origin_ns is None else origin_ns
        self._running: Dict[str, Tuple[int, int]] = {}  # name -> (start order, start ns)
        self._completed: List[Tuple[int, SpanTiming]] = []
        self._next_order = 0

    def now_ns(self) -> int:
        return self._clock()

    def start(self, name: str) -> None:
        if name in self._running:
            raise ValueError(f"span {name!r} is already running")
        self._running[name] = (self._next_order, self._clock())
        self._next_order += 1

    def stop(self, name: str) -> None:
        if name not in self._running:
            raise ValueError(f"span {name!r} was never started")
        order, started_ns = self._running.pop(name)
        self._complete(order, name, started_ns, self._clock())

    def record_span(self, name: str, start_ns: int, end_ns: int) -> None:
        """Records a span whose endpoints were captured earlier (e.g. when a segment arrived)."""
        if end_ns < start_ns:
            raise ValueError(f"span {name!r} ends before it starts")
        self._complete(self._next_order, name, start_ns, end_ns)
        self._next_order += 1

    def _complete(self, order: int, name: str, start_ns: int, end_ns: int) -> None:
        span = SpanTiming(name=name, start_offset_ns=start_ns - self.origin_ns, duration_ns=end_ns - start_ns)
        self._completed.append((order, span))

    def telemetry(self) -> PipelineTelemetry:
        return PipelineTelemetry(spans=tuple(span for _, span in sorted(self._completed, key=lambda s: s[0])))


def _ms(ns: int) -> float:
    return round(ns / NS_PER_MS, TIMING_LOG_DECIMALS)


def utterance_timing_record(
    *,
    path: str,
    origin: str,
    telemetry: PipelineTelemetry,
    stt_reported_latency_ms: Sequence[float],
    statuses: Sequence[str],
) -> Dict[str, object]:
    """
    The structured timing record for one utterance. Every span is on one timeline whose zero
    is ``origin`` (when the first STT segment arrived, or when the request arrived);
    ``to_first_audio_ms`` is the end of the first reply's Timbre first byte on that timeline,
    or None when no reply audio was produced.
    """
    spans = {
        span.name: {"start_ms": _ms(span.start_offset_ns), "duration_ms": _ms(span.duration_ns)}
        for span in telemetry.spans
    }
    first_audio = next((s for s in telemetry.spans if s.name == SPAN_TIMBRE_FIRST_BYTE), None)
    return {
        "event": UTTERANCE_TIMING_EVENT,
        "path": path,
        "origin": origin,
        "stt_segments": len(stt_reported_latency_ms),
        "stt_reported_latency_ms": [float(v) for v in stt_reported_latency_ms],
        "spans": spans,
        "to_first_audio_ms": (
            None if first_audio is None else _ms(first_audio.start_offset_ns + first_audio.duration_ns)
        ),
        "decisions": list(statuses),
    }


def log_utterance_timing(record: Dict[str, object], logger: logging.Logger = timing_logger) -> str:
    """Logs ``record`` as one compact JSON line at INFO and returns the line."""
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    logger.info(line)
    return line
