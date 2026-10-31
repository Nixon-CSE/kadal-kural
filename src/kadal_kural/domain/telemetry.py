"""
Pipeline timing contract for the domain layer: the SpanRecorder protocol, its no-op
default, and the frozen PipelineTelemetry value object returned next to the decisions.

The domain never reads a clock. The recording implementation, backed by the monotonic
time.perf_counter_ns, lives in kadal_kural.infrastructure.timing and is injected into
PreDispatchCreditFirewallService as a SpanRecorderFactory (one fresh recorder per
utterance, so concurrent utterances never share span state).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Dict, Iterator, Optional, Protocol, Tuple

from pydantic import BaseModel, ConfigDict, Field

from kadal_kural.config import NS_PER_MS
from kadal_kural.domain.models import CreditGateDecision


class SpanTiming(BaseModel):
    """One completed span: its start relative to the recorder's origin, and its length."""

    model_config = ConfigDict(frozen=True)

    name: str
    start_offset_ns: int = Field(ge=0)
    duration_ns: int = Field(ge=0)


class PipelineTelemetry(BaseModel):
    """Every completed span for one utterance, in the order the spans started."""

    model_config = ConfigDict(frozen=True)

    spans: Tuple[SpanTiming, ...] = ()

    def duration_ns(self, name: str) -> Optional[int]:
        """Length of the first span called ``name``, or None if it was never recorded."""
        return next((span.duration_ns for span in self.spans if span.name == name), None)

    def durations_ms(self) -> Dict[str, float]:
        """Span name -> length in milliseconds."""
        return {span.name: span.duration_ns / NS_PER_MS for span in self.spans}


class SpanRecorder(Protocol):
    """Starts and stops named spans for one utterance and reports them as telemetry."""

    def start(self, name: str) -> None: ...

    def stop(self, name: str) -> None: ...

    def telemetry(self) -> PipelineTelemetry: ...


SpanRecorderFactory = Callable[[], SpanRecorder]


class NullSpanRecorder:
    """The default recorder: never reads a clock and always reports no spans."""

    def start(self, name: str) -> None:
        return None

    def stop(self, name: str) -> None:
        return None

    def telemetry(self) -> PipelineTelemetry:
        return PipelineTelemetry()


@contextmanager
def recorded_span(recorder: SpanRecorder, name: str) -> Iterator[None]:
    """Times the enclosed block as span ``name``."""
    recorder.start(name)
    try:
        yield
    finally:
        recorder.stop(name)


class UtteranceEvaluation(BaseModel):
    """The firewall's decisions for one utterance, with the pipeline timings beside them."""

    model_config = ConfigDict(frozen=True)

    decisions: Tuple[CreditGateDecision, ...]
    telemetry: PipelineTelemetry
