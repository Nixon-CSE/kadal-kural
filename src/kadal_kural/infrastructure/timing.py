"""Recording SpanRecorder backed by the monotonic time.perf_counter_ns clock."""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Tuple

from kadal_kural.domain.telemetry import PipelineTelemetry, SpanTiming

NanosecondClock = Callable[[], int]


class PerfCounterSpanRecorder:
    """
    Records named spans for one utterance against a monotonic nanosecond clock
    (time.perf_counter_ns unless a test injects a fake one). Span offsets are relative to
    the clock reading taken when the recorder is created. Starting a running span or
    stopping one that never started is a programming error and raises ValueError.
    """

    def __init__(self, clock: NanosecondClock = time.perf_counter_ns) -> None:
        self._clock = clock
        self._origin_ns = clock()
        self._running: Dict[str, Tuple[int, int]] = {}  # name -> (start order, start ns)
        self._completed: List[Tuple[int, SpanTiming]] = []
        self._next_order = 0

    def start(self, name: str) -> None:
        if name in self._running:
            raise ValueError(f"span {name!r} is already running")
        self._running[name] = (self._next_order, self._clock())
        self._next_order += 1

    def stop(self, name: str) -> None:
        if name not in self._running:
            raise ValueError(f"span {name!r} was never started")
        order, started_ns = self._running.pop(name)
        span = SpanTiming(
            name=name,
            start_offset_ns=started_ns - self._origin_ns,
            duration_ns=self._clock() - started_ns,
        )
        self._completed.append((order, span))

    def telemetry(self) -> PipelineTelemetry:
        return PipelineTelemetry(spans=tuple(span for _, span in sorted(self._completed, key=lambda s: s[0])))
