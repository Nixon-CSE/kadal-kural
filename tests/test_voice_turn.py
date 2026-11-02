"""Full live-path timing: the per-utterance JSON timing line, its timeline, and the gateway wiring."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

import pytest
from fastapi.testclient import TestClient

from kadal_kural.api.main import create_app
from kadal_kural.config import (
    CLARIFICATION_PROMPT_TAMIL,
    NS_PER_MS,
    REPLY_AUDIO,
    REPLY_INTERRUPTED,
    SPAN_ASSEMBLE,
    SPAN_DECIDE,
    SPAN_MATCH,
    SPAN_NORMALIZE,
    SPAN_TIMBRE_FIRST_BYTE,
    TIMING_LOGGER_NAME,
    TIMING_ORIGIN_FIRST_SEGMENT,
    TIMING_ORIGIN_REQUEST,
    TIMING_PATH_INGEST,
    TIMING_PATH_LIVE_WS,
    UTTERANCE_TIMING_EVENT,
    AppSettings,
)
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.domain.telemetry import PipelineTelemetry, SpanTiming
from kadal_kural.infrastructure.gnani_client import AssembledUtterance, MultiSegmentTradeAssembler, SynthesisTelemetry
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository
from kadal_kural.infrastructure.timing import log_utterance_timing, utterance_timing_record
from kadal_kural.infrastructure.voice_turn import run_voice_turn

TWO_TRADES = (
    "செந்தில் சீஃபுட்ஸ்க்கு 40 கிலோ எக்ஸ்போர்ட் வஞ்சரம் எழுநூற்றி 40 ரேட்டு "
    "குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு"
)
ASSEMBLE_MS, TTFB_MS, REST_OF_REPLY_MS = 1500, 400, 100


class FakeClock:
    def __init__(self, start_ns: int = 9_000 * NS_PER_MS) -> None:
        self.now_ns = start_ns

    def __call__(self) -> int:
        return self.now_ns

    def advance_ms(self, ms: int) -> None:
        self.now_ns += ms * NS_PER_MS


class FakeTimbre:
    """Spends known fake time before the first audio byte and after it."""

    def __init__(self, clock: FakeClock, fail: bool = False) -> None:
        self.clock = clock
        self.fail = fail
        self.texts: List[str] = []

    async def synthesize_timbre_v25(
        self, text_tamil: str, *, on_first_audio: Optional[Callable[[], None]] = None
    ) -> SynthesisTelemetry:
        self.texts.append(text_tamil)
        if self.fail:
            raise RuntimeError("Timbre down")
        self.clock.advance_ms(TTFB_MS)
        if on_first_audio is not None:
            on_first_audio()
        self.clock.advance_ms(REST_OF_REPLY_MS)
        return SynthesisTelemetry(b"RIFF", float(TTFB_MS), float(TTFB_MS + REST_OF_REPLY_MS), False)


@pytest.fixture
def firewall(tmp_path: Path) -> PreDispatchCreditFirewallService:
    settings = AppSettings(db_path=str(tmp_path / "turn.db"))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    return PreDispatchCreditFirewallService(
        settings, matcher, AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    )


def _timing_lines(caplog: pytest.LogCaptureFixture) -> List[str]:
    return [r.getMessage() for r in caplog.records if r.name == TIMING_LOGGER_NAME]


def test_timing_record_format_is_one_compact_json_line(caplog: pytest.LogCaptureFixture) -> None:
    telemetry = PipelineTelemetry(
        spans=(
            SpanTiming(name=SPAN_ASSEMBLE, start_offset_ns=0, duration_ns=1_500_123_456),
            SpanTiming(name=SPAN_DECIDE, start_offset_ns=1_500_123_456, duration_ns=250_000),
            SpanTiming(name=SPAN_TIMBRE_FIRST_BYTE, start_offset_ns=1_500_500_000, duration_ns=399_500_000),
        )
    )
    record = utterance_timing_record(
        path=TIMING_PATH_LIVE_WS,
        origin=TIMING_ORIGIN_FIRST_SEGMENT,
        telemetry=telemetry,
        stt_reported_latency_ms=[212, 230.5],
        statuses=["BOOKED"],
        reply_outcomes=["audio"],
        logged_at="18:47:03",
        segment_received_ns=[0, 2_800_000_000],
    )
    with caplog.at_level(logging.INFO, logger=TIMING_LOGGER_NAME):
        line = log_utterance_timing(record)
    assert _timing_lines(caplog) == [line]
    assert "\n" not in line and ": " not in line  # one compact line
    assert line == (
        '{"event":"utterance_timing","logged_at":"18:47:03","path":"live_ws","origin":"first_stt_segment_received",'
        '"stt_segments":2,"stt_reported_latency_ms":[212.0,230.5],"segment_gaps_ms":[2800.0],'
        '"spans":{"assemble":{"start_ms":0.0,"duration_ms":1500.123},'
        '"decide":{"start_ms":1500.123,"duration_ms":0.25},'
        '"timbre_first_byte":{"start_ms":1500.5,"duration_ms":399.5}},'
        '"to_first_audio_ms":1900.0,"decisions":["BOOKED"],"reply_outcomes":["audio"]}'
    )


async def test_voice_turn_logs_every_stage_on_one_timeline_from_the_first_segment(
    firewall: PreDispatchCreditFirewallService, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    first_segment_ns = clock()
    clock.advance_ms(ASSEMBLE_MS)  # the assembler's stitching window elapses
    timbre = FakeTimbre(clock)
    with caplog.at_level(logging.INFO, logger=TIMING_LOGGER_NAME):
        turn = await run_voice_turn(
            firewall, timbre, TWO_TRADES,
            path=TIMING_PATH_LIVE_WS, stt_latencies_ms=(210.0, 230.0),
            first_segment_ns=first_segment_ns, clock=clock,
        )
    assert len(timbre.texts) == 2 and [r is not None for r in turn.replies] == [True, True]
    (line,) = _timing_lines(caplog)
    assert line == turn.log_line
    # the firewall's own stages take no fake time; Timbre's first byte arrives TTFB_MS later
    stage = {"start_ms": float(ASSEMBLE_MS), "duration_ms": 0.0}
    record = json.loads(line)
    assert isinstance(record.pop("logged_at"), str)
    assert record == {
        "event": UTTERANCE_TIMING_EVENT,
        "path": TIMING_PATH_LIVE_WS,
        "origin": TIMING_ORIGIN_FIRST_SEGMENT,
        "stt_segments": 2,
        "stt_reported_latency_ms": [210.0, 230.0],
        "segment_gaps_ms": [],  # this call passes no arrival times
        "spans": {
            SPAN_ASSEMBLE: {"start_ms": 0.0, "duration_ms": float(ASSEMBLE_MS)},
            SPAN_NORMALIZE: stage,
            SPAN_MATCH: stage,
            SPAN_DECIDE: stage,
            SPAN_TIMBRE_FIRST_BYTE: {"start_ms": float(ASSEMBLE_MS), "duration_ms": float(TTFB_MS)},
        },
        "to_first_audio_ms": float(ASSEMBLE_MS + TTFB_MS),
        "decisions": ["CREDIT_HOLD_BREACH", "BOOKED"],
        "reply_outcomes": [REPLY_AUDIO, REPLY_AUDIO],
    }
    assert [d.stt_latency_ms for d in turn.evaluation.decisions] == [220.0, 220.0]


async def test_voice_turn_still_logs_its_line_when_synthesis_fails(
    firewall: PreDispatchCreditFirewallService, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    with caplog.at_level(logging.INFO, logger=TIMING_LOGGER_NAME), pytest.raises(RuntimeError, match="Timbre down"):
        await run_voice_turn(
            firewall, FakeTimbre(clock, fail=True), TWO_TRADES, path=TIMING_PATH_LIVE_WS,
            first_segment_ns=clock(), clock=clock,
        )
    (line,) = _timing_lines(caplog)
    record = json.loads(line)
    assert SPAN_TIMBRE_FIRST_BYTE not in record["spans"] and record["to_first_audio_ms"] is None
    assert record["decisions"] == ["CREDIT_HOLD_BREACH", "BOOKED"]


async def test_assembler_reports_when_its_segments_arrived() -> None:
    clock = FakeClock()
    committed: List[AssembledUtterance] = []

    async def _commit(utterance: AssembledUtterance) -> None:
        committed.append(utterance)

    assembler = MultiSegmentTradeAssembler(window_sec=60.0, on_commit=_commit, clock=clock)
    first_ns = clock()
    await assembler.ingest_segment("செந்திலுக்கு 25 கிலோ", 200.0)
    clock.advance_ms(700)
    await assembler.ingest_segment("வஞ்சரம் 800 ரேட்டு", 250.0, received_ns=clock() - 5 * NS_PER_MS)
    await assembler.flush_immediately()
    (utterance,) = committed
    assert utterance == AssembledUtterance(
        text="செந்திலுக்கு 25 கிலோ வஞ்சரம் 800 ரேட்டு",
        segment_latencies_ms=(200.0, 250.0),
        first_segment_ns=first_ns,
        last_segment_ns=first_ns + 695 * NS_PER_MS,
        segment_received_ns=(first_ns, first_ns + 695 * NS_PER_MS),
    )
    assert utterance.mean_stt_latency_ms == 225.0


def test_gateway_emits_timing_lines_even_without_configured_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timing = logging.getLogger(TIMING_LOGGER_NAME)
    monkeypatch.setattr(logging.getLogger(), "handlers", [])  # what uvicorn leaves on the root logger
    monkeypatch.setattr(timing, "handlers", [])
    monkeypatch.setattr(timing, "level", logging.NOTSET)
    create_app(AppSettings(gnani_api_key="", db_path=str(tmp_path / "log.db")))
    assert timing.getEffectiveLevel() == logging.INFO
    (handler,) = timing.handlers
    assert handler.formatter is not None and handler.formatter._fmt == "%(message)s"


def test_ingest_endpoint_logs_one_timing_line_from_request_receipt(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(AppSettings(gnani_api_key="", db_path=str(tmp_path / "api.db")))
    with TestClient(app) as client, caplog.at_level(logging.INFO, logger=TIMING_LOGGER_NAME):
        response = client.post("/api/v1/ingest", json={"transcript": TWO_TRADES, "synthesize_tts": False})
    assert response.status_code == 200
    (line,) = _timing_lines(caplog)
    record = json.loads(line)
    assert (record["path"], record["origin"], record["stt_segments"]) == (TIMING_PATH_INGEST, TIMING_ORIGIN_REQUEST, 0)
    assert list(record["spans"]) == [SPAN_NORMALIZE, SPAN_MATCH, SPAN_DECIDE]
    assert record["to_first_audio_ms"] is None  # no key, so no reply was synthesized
    statuses: Tuple[str, ...] = tuple(d["status"] for d in response.json()["decisions"])
    assert list(statuses) == record["decisions"]


# ------------------------------------------------------------------------------ every turn speaks

UNKNOWN_BUYER = "புது கடைக்கு 30 கிலோ வஞ்சரம் 800 ரேட்டு"  # goes to PENDING_CLARIFICATION
NO_TRADE = "இன்னைக்கு கடல் நல்லா இருக்கு"  # parses into no decision at all


class ScriptedTimbre:
    """Plays back a script of replies, or exceptions, one per synthesis."""

    def __init__(self, script: List[Union[SynthesisTelemetry, Exception]]) -> None:
        self.script = list(script)
        self.texts: List[str] = []

    async def synthesize_timbre_v25(
        self, text_tamil: str, *, on_first_audio: Optional[Callable[[], None]] = None
    ) -> SynthesisTelemetry:
        self.texts.append(text_tamil)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if step.audio_wav_bytes and on_first_audio is not None:
            on_first_audio()
        return step


def _audio(wav: bytes = b"RIFF", interrupted: bool = False) -> SynthesisTelemetry:
    return SynthesisTelemetry(wav, 300.0, 400.0, interrupted)


async def test_turn_with_zero_decisions_still_speaks_the_prompt(
    firewall: PreDispatchCreditFirewallService, caplog: pytest.LogCaptureFixture
) -> None:
    timbre = ScriptedTimbre([_audio()])
    with caplog.at_level(logging.INFO, logger=TIMING_LOGGER_NAME):
        turn = await run_voice_turn(firewall, timbre, NO_TRADE, path=TIMING_PATH_LIVE_WS)
    assert turn.evaluation.decisions == ()
    assert timbre.texts == [CLARIFICATION_PROMPT_TAMIL]
    assert turn.prompt_reply is not None
    (line,) = _timing_lines(caplog)
    record = json.loads(line)
    assert SPAN_TIMBRE_FIRST_BYTE in record["spans"] and record["to_first_audio_ms"] is not None
    assert (record["decisions"], record["reply_outcomes"]) == ([], [REPLY_AUDIO])


async def test_zero_decisions_without_tts_stays_silent(firewall: PreDispatchCreditFirewallService) -> None:
    timbre = ScriptedTimbre([])
    turn = await run_voice_turn(firewall, timbre, NO_TRADE, path=TIMING_PATH_INGEST, synthesize=False)
    assert timbre.texts == [] and turn.prompt_reply is None


@pytest.mark.parametrize(
    "first_attempt",
    [pytest.param(_audio(b""), id="no-audio"), pytest.param(RuntimeError("Timbre hiccup"), id="failed")],
)
async def test_clarification_with_no_audio_is_spoken_again(
    first_attempt: Union[SynthesisTelemetry, Exception],
    firewall: PreDispatchCreditFirewallService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    timbre = ScriptedTimbre([first_attempt, _audio()])
    with caplog.at_level(logging.INFO, logger=TIMING_LOGGER_NAME):
        turn = await run_voice_turn(firewall, timbre, UNKNOWN_BUYER, path=TIMING_PATH_LIVE_WS)
    assert timbre.texts == [CLARIFICATION_PROMPT_TAMIL, CLARIFICATION_PROMPT_TAMIL]
    assert turn.replies[0] is not None and turn.replies[0].audio_wav_bytes
    (line,) = _timing_lines(caplog)
    assert SPAN_TIMBRE_FIRST_BYTE in json.loads(line)["spans"]


async def test_clarification_cut_by_barge_in_is_not_spoken_over_the_trader(
    firewall: PreDispatchCreditFirewallService, caplog: pytest.LogCaptureFixture
) -> None:
    timbre = ScriptedTimbre([_audio(b"", interrupted=True)])
    with caplog.at_level(logging.INFO, logger=TIMING_LOGGER_NAME):
        await run_voice_turn(firewall, timbre, UNKNOWN_BUYER, path=TIMING_PATH_LIVE_WS)
    assert len(timbre.texts) == 1
    (line,) = _timing_lines(caplog)
    assert json.loads(line)["reply_outcomes"] == [REPLY_INTERRUPTED]  # the log explains the missing span


async def test_segment_arriving_mid_turn_no_longer_silences_it(firewall: PreDispatchCreditFirewallService) -> None:
    """The 18:47 mechanism: a repeat arrived before Timbre's first byte and cancelled the turn."""
    first_byte_gate = asyncio.Event()
    spoken: List[str] = []

    class SlowTimbre:
        async def synthesize_timbre_v25(
            self, text_tamil: str, *, on_first_audio: Optional[Callable[[], None]] = None
        ) -> SynthesisTelemetry:
            await first_byte_gate.wait()
            if on_first_audio is not None:
                on_first_audio()
            spoken.append(text_tamil)
            return _audio()

    async def _commit(utterance: AssembledUtterance) -> None:
        await run_voice_turn(firewall, SlowTimbre(), utterance.text, path=TIMING_PATH_LIVE_WS)

    assembler = MultiSegmentTradeAssembler(0.0, _commit)
    await assembler.ingest_segment(UNKNOWN_BUYER, 180.0)
    await asyncio.sleep(0.01)  # the wait is over and Timbre was asked; no audio yet
    await assembler.ingest_segment("குமரனுக்கு 5 கிலோ டைகர் பிரான் 560 ரேட்டு", 180.0)
    first_byte_gate.set()
    await assembler.flush_immediately()
    assert len(spoken) == 2 and spoken[0] == CLARIFICATION_PROMPT_TAMIL


async def test_lone_ledger_verb_after_a_committed_trade_is_not_an_utterance() -> None:
    committed: List[AssembledUtterance] = []

    async def _commit(utterance: AssembledUtterance) -> None:
        committed.append(utterance)

    assembler = MultiSegmentTradeAssembler(0.0, _commit)
    await assembler.ingest_segment("கிரெடிட்டில் ஏற்று", 180.0)
    await assembler.flush_immediately()
    assert committed == []
    await assembler.ingest_segment("குமரனுக்கு 5 கிலோ", 180.0)
    await assembler.ingest_segment("கிரெடிட்டில் ஏற்று", 180.0)  # part of an utterance still being assembled
    await assembler.flush_immediately()
    assert [u.text for u in committed] == ["குமரனுக்கு 5 கிலோ கிரெடிட்டில் ஏற்று"]


async def test_failed_commit_is_logged_not_lost(caplog: pytest.LogCaptureFixture) -> None:
    async def _commit(utterance: AssembledUtterance) -> None:
        raise RuntimeError("Timbre down")

    assembler = MultiSegmentTradeAssembler(0.0, _commit)
    await assembler.ingest_segment("குமரனுக்கு 5 கிலோ", 180.0)
    await assembler.flush_immediately()
    assert any(r.levelno == logging.ERROR and "Voice turn failed" in r.getMessage() for r in caplog.records)
