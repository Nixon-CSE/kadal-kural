"""Pipeline timing: the SpanRecorder implementations and the firewall's PipelineTelemetry, on a fake clock."""

from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import Any, Callable, Tuple, TypeVar

import pytest

from kadal_kural.config import NS_PER_MS, SPAN_DECIDE, SPAN_MATCH, SPAN_NORMALIZE, SPAN_UNDO, AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import LedgerEventStatus
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.domain.telemetry import NullSpanRecorder, PipelineTelemetry, SpanTiming
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository
from kadal_kural.infrastructure.timing import PerfCounterSpanRecorder

_T = TypeVar("_T")

# How far each faked stage moves the clock; distinct primes so every sum below is unambiguous.
NORMALIZE_MS, MATCH_MS, READ_MS, WRITE_MS, UNDO_MS = 2, 3, 5, 7, 11

TWO_TRADES = (
    "செந்தில் சீஃபுட்ஸ்க்கு 40 கிலோ எக்ஸ்போர்ட் வஞ்சரம் எழுநூற்றி 40 ரேட்டு "
    "குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு"
)


class FakeClock:
    """A nanosecond clock that moves only when a test, or a faked stage, advances it."""

    def __init__(self, start_ns: int = 7_000 * NS_PER_MS) -> None:
        self.now_ns = start_ns

    def __call__(self) -> int:
        return self.now_ns

    def advance_ms(self, ms: int) -> None:
        self.now_ns += ms * NS_PER_MS


def _advancing(clock: FakeClock, ms: int, fn: Callable[..., _T]) -> Callable[..., _T]:
    """Wraps ``fn`` so each call first spends ``ms`` of fake time."""

    def wrapper(*args: Any, **kwargs: Any) -> _T:
        clock.advance_ms(ms)
        return fn(*args, **kwargs)

    return wrapper


TimedFirewall = Tuple[PreDispatchCreditFirewallService, FakeClock]


@pytest.fixture
def timed_firewall(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TimedFirewall:
    """A real firewall (real matcher, real SQLite ledger) whose stages take known fake time."""
    clock = FakeClock()
    settings = AppSettings(db_path=str(tmp_path / "timed.db"))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    monkeypatch.setattr(matcher, "normalize", _advancing(clock, NORMALIZE_MS, matcher.normalize))
    monkeypatch.setattr(matcher, "parse_normalized", _advancing(clock, MATCH_MS, matcher.parse_normalized))
    monkeypatch.setattr(repo, "get_buyer_row", _advancing(clock, READ_MS, repo.get_buyer_row))
    monkeypatch.setattr(
        repo, "append_event_and_update_balance",
        _advancing(clock, WRITE_MS, repo.append_event_and_update_balance),
    )
    monkeypatch.setattr(repo, "undo_last_booked_trade", _advancing(clock, UNDO_MS, repo.undo_last_booked_trade))
    service = PreDispatchCreditFirewallService(
        settings, matcher, repo, span_recorder_factory=lambda: PerfCounterSpanRecorder(clock)
    )
    return service, clock


def _ms(ms: int) -> int:
    return ms * NS_PER_MS


# ------------------------------------------------------------------------------ recorder


def test_recorder_reports_exact_offsets_and_durations_in_start_order() -> None:
    clock = FakeClock()
    recorder = PerfCounterSpanRecorder(clock)
    clock.advance_ms(1)
    recorder.start("outer")
    clock.advance_ms(2)
    recorder.start("inner")
    clock.advance_ms(3)
    recorder.stop("inner")
    clock.advance_ms(4)
    recorder.stop("outer")
    assert recorder.telemetry().spans == (
        SpanTiming(name="outer", start_offset_ns=_ms(1), duration_ns=_ms(9)),
        SpanTiming(name="inner", start_offset_ns=_ms(3), duration_ns=_ms(3)),
    )


def test_recorder_rejects_restarting_a_running_span_or_stopping_an_unknown_one() -> None:
    recorder = PerfCounterSpanRecorder(FakeClock())
    recorder.start("a")
    with pytest.raises(ValueError, match="already running"):
        recorder.start("a")
    with pytest.raises(ValueError, match="never started"):
        recorder.stop("b")


def test_recorder_defaults_to_the_monotonic_perf_counter_ns_clock() -> None:
    default_clock = inspect.signature(PerfCounterSpanRecorder).parameters["clock"].default
    assert default_clock is time.perf_counter_ns


def test_null_recorder_reports_no_spans() -> None:
    recorder = NullSpanRecorder()
    recorder.start("x")
    recorder.stop("x")
    recorder.stop("never-started")
    assert recorder.telemetry() == PipelineTelemetry()


def test_telemetry_lookups() -> None:
    telemetry = PipelineTelemetry(
        spans=(
            SpanTiming(name=SPAN_NORMALIZE, start_offset_ns=0, duration_ns=_ms(2)),
            SpanTiming(name=SPAN_MATCH, start_offset_ns=_ms(2), duration_ns=1_500_000),
        )
    )
    assert telemetry.duration_ns(SPAN_MATCH) == 1_500_000
    assert telemetry.duration_ns(SPAN_DECIDE) is None
    assert telemetry.durations_ms() == {SPAN_NORMALIZE: 2.0, SPAN_MATCH: 1.5}


# ------------------------------------------------------------------------------ firewall


def test_firewall_times_normalize_match_and_decide_including_sqlite_writes(timed_firewall: TimedFirewall) -> None:
    service, _ = timed_firewall
    result = service.evaluate_utterance_timed(TWO_TRADES)
    assert [d.status for d in result.decisions] == [
        LedgerEventStatus.CREDIT_HOLD_BREACH,
        LedgerEventStatus.BOOKED,
    ]
    # decide = per intent, one buyer read + one ledger write (the hold is logged too)
    decide_ms = 2 * (READ_MS + WRITE_MS)
    assert result.telemetry.spans == (
        SpanTiming(name=SPAN_NORMALIZE, start_offset_ns=0, duration_ns=_ms(NORMALIZE_MS)),
        SpanTiming(name=SPAN_MATCH, start_offset_ns=_ms(NORMALIZE_MS), duration_ns=_ms(MATCH_MS)),
        SpanTiming(
            name=SPAN_DECIDE, start_offset_ns=_ms(NORMALIZE_MS + MATCH_MS), duration_ns=_ms(decide_ms)
        ),
    )


def test_gate_blocked_trade_still_counts_its_ledger_write_in_decide(timed_firewall: TimedFirewall) -> None:
    service, _ = timed_firewall
    result = service.evaluate_utterance_timed("புது கடைக்கு 30 கிலோ வஞ்சரம் 800 ரேட்டு")
    assert [d.status for d in result.decisions] == [LedgerEventStatus.PENDING_CLARIFICATION]
    assert result.telemetry.duration_ns(SPAN_DECIDE) == _ms(WRITE_MS)  # no buyer read, one write


def test_voice_undo_records_only_the_undo_span(timed_firewall: TimedFirewall) -> None:
    service, _ = timed_firewall
    service.evaluate_utterance("குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு")
    result = service.evaluate_utterance_timed("கடைசி ஆர்டர் கேன்சல்")
    assert [d.status for d in result.decisions] == [LedgerEventStatus.VOIDED_BY_UNDO]
    # the undo reads the buyer and writes the compensating event itself, inside the span
    undo_ms = UNDO_MS + READ_MS + WRITE_MS
    assert result.telemetry.spans == (SpanTiming(name=SPAN_UNDO, start_offset_ns=0, duration_ns=_ms(undo_ms)),)


def test_timing_never_changes_the_decisions(tmp_path: Path, timed_firewall: TimedFirewall) -> None:
    timed_service, _ = timed_firewall
    settings = AppSettings(db_path=str(tmp_path / "untimed.db"))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    untimed = PreDispatchCreditFirewallService(
        settings, matcher, AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    )
    timed = timed_service.evaluate_utterance_timed(TWO_TRADES)
    plain = untimed.evaluate_utterance_timed(TWO_TRADES)
    assert plain.telemetry == PipelineTelemetry()  # the default recorder is the no-op one
    assert list(plain.decisions) == list(timed.decisions)
    assert untimed.evaluate_utterance(TWO_TRADES)[0].status == LedgerEventStatus.CREDIT_HOLD_BREACH
