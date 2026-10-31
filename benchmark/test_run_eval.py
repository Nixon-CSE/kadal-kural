"""Offline tests for the benchmark orchestrator and scorer (a fake speech backend; no API calls)."""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import Dict, List

import numpy as np
import pytest

from benchmark.corpus import BenchmarkUtterance, build_corpus
from benchmark.noise_profiles import measured_snr_db, rms
from benchmark.run_eval import (
    CLEAN_PROFILE,
    DiskCache,
    TranscriptOutcome,
    build_stt_audio,
    build_work_items,
    gather_transcripts,
    render_report,
    resample_16k_to_8k,
    sample_corpus,
    score_rows,
    summarize,
    threshold_sweep,
    write_csv,
)
from benchmark.scoring import Scorer, classify_bookings
from kadal_kural.config import AppSettings
from kadal_kural.domain.models import CreditGateDecision, LedgerEventStatus

_SR = 8000


@pytest.fixture(scope="module")
def settings() -> AppSettings:
    return AppSettings(gnani_api_key="unused-in-offline-tests")


@pytest.fixture(scope="module")
def scorer(settings: AppSettings) -> Scorer:
    return Scorer(settings)


def _utt(utterance_id: str) -> BenchmarkUtterance:
    return next(u for u in build_corpus() if u.utterance_id == utterance_id)


# ----------------------------------------------------------------------------- scoring


def test_every_clean_corpus_utterance_scores_perfectly(scorer: Scorer) -> None:
    for utt in build_corpus():
        s = scorer.score(utt, utt.spoken_text, 0.0)
        assert s.wer_normalized == 0.0, utt.utterance_id
        assert all(v == s.n_truth_trades for v in s.entity_correct.values()), utt.utterance_id
        assert s.gated.silent_errors == 0 and s.ungated.silent_errors == 0, utt.utterance_id


def test_confident_wrong_rate_is_a_silent_error_the_gate_cannot_see(scorer: Scorer) -> None:
    utt = _utt("single_01")  # "... 250 ரேட்டு"
    s = scorer.score(utt, utt.spoken_text.replace("250", "520"), 0.0)
    assert s.entity_correct["rate"] == 0
    assert (s.gated.silent_errors, s.ungated.silent_errors) == (1, 1)


def test_gate_blocks_low_confidence_wrong_buyer_that_ungated_books(scorer: Scorer) -> None:
    utt = _utt("single_01")
    s = scorer.score(utt, utt.spoken_text.replace("செந்திலுக்கு", "ராமன்"), 0.0)
    assert (s.gated.booked, s.gated.silent_errors) == (0, 0)
    assert (s.ungated.booked, s.ungated.silent_errors) == (1, 1)


def test_empty_transcript_is_total_wer_and_not_a_silent_error(scorer: Scorer) -> None:
    s = scorer.score(_utt("single_01"), "", 0.0)
    assert s.wer_normalized == 1.0 and s.n_parsed_trades == 0
    assert s.gated.silent_errors == 0 and s.entity_correct["buyer"] == 0


def test_duplicate_booking_counts_once_as_an_error(scorer: Scorer) -> None:
    utt = _utt("single_01")
    s = scorer.score(utt, f"{utt.spoken_text} {utt.spoken_text}", 0.0)
    assert (s.gated.booked, s.gated.correct_bookings, s.gated.silent_errors) == (2, 1, 1)


def test_dropped_first_clause_does_not_misalign_the_second(scorer: Scorer) -> None:
    utt = _utt("multi_01")
    first, second = utt.ground_truth_trades
    only_second = utt.spoken_text.split("ரேட்டு")[1].strip() + " ரேட்டு"
    s = scorer.score(utt, only_second, 0.0)
    assert s.n_parsed_trades == 1
    assert s.gated.silent_errors == 0  # the surviving booking matches truth trade #2
    assert sum(s.entity_correct.values()) >= 5  # the second trade was scored against the right intent
    assert first != second


def test_classify_bookings_ignores_non_booked_statuses() -> None:
    held = CreditGateDecision(
        event_id=1, status=LedgerEventStatus.CREDIT_HOLD_BREACH, buyer_id="BUY-101", buyer_name="x",
        sku_name="Export Vanjaram", quantity=1, unit="box", rate_inr=1, trade_value_inr=1,
        previous_balance_inr=0, projected_balance_inr=1, credit_limit_inr=0, excess_amount_inr=1,
        confidence=1.0, tts_response_tamil="", upi_payment_uri="",
    )
    assert classify_bookings([held], _utt("single_01").ground_truth_trades) == (0, 0, 0)


# ----------------------------------------------------------------------------- audio


def test_resample_halves_length_and_preserves_in_band_tone() -> None:
    t = np.arange(16000) / 16000.0
    tone = (8000 * np.sin(2 * np.pi * 1000 * t)).astype(np.int16)
    out = resample_16k_to_8k(tone)
    assert len(out) == 8000
    assert abs(rms(out[200:-200].astype(np.float64)) / rms(tone[400:-400].astype(np.float64)) - 1) < 0.05


def test_stt_audio_hits_target_snr_and_noise_fills_lead_and_tail() -> None:
    clean = (6000 * np.sin(2 * np.pi * 220 * np.arange(_SR * 2) / _SR)).astype(np.int16)
    pcm, achieved = build_stt_audio(clean, "market", 10.0, seed=3, lead_ms=300, tail_ms=800)
    samples = np.frombuffer(pcm, dtype=np.int16)
    lead, tail = _SR * 300 // 1000, _SR * 800 // 1000
    assert len(samples) == len(clean) + lead + tail
    assert achieved is not None and abs(achieved - 10.0) <= 0.5
    speech = samples[lead:-tail].astype(np.float64)
    assert abs(measured_snr_db(clean.astype(np.float64), speech - clean) - 10.0) <= 0.5
    noise_in_speech = rms(speech - clean)
    assert abs(rms(samples[-tail:].astype(np.float64)) / noise_in_speech - 1) < 0.15  # tail at same level


def test_clean_baseline_has_digital_silence_around_speech() -> None:
    clean = np.full(_SR, 1000, dtype=np.int16)
    pcm, achieved = build_stt_audio(clean, CLEAN_PROFILE, None, seed=0, lead_ms=100, tail_ms=100)
    samples = np.frombuffer(pcm, dtype=np.int16)
    assert achieved is None and not samples[:800].any() and not samples[-800:].any()


def test_sample_corpus_is_deterministic_and_spans_categories() -> None:
    corpus = build_corpus()
    a, b = sample_corpus(corpus, 8), sample_corpus(corpus, 8)
    assert [u.utterance_id for u in a] == [u.utterance_id for u in b] and len(a) == 8
    assert len({u.category for u in a}) >= 3
    assert len(sample_corpus(corpus, None)) == len(corpus)


# ----------------------------------------------------------------------------- sweep (fake backend)


class FakeBackend:
    """Returns clean speech; 'transcribes' by reading the utterance back from a registry."""

    def __init__(self, transcript_for: Dict[int, str]) -> None:
        self.calls = {"tts": 0, "stt": 0}
        self._by_len = transcript_for

    async def synthesize_clean_8k(self, text: str) -> np.ndarray:
        self.calls["tts"] += 1
        return (3000 * np.sin(2 * np.pi * 200 * np.arange(_SR) / _SR)).astype(np.int16)

    async def transcribe(self, pcm_8k: bytes) -> TranscriptOutcome:
        self.calls["stt"] += 1
        return TranscriptOutcome("செந்திலுக்கு 25 பாக்ஸ் வஞ்சரம் 250 ரேட்டு", 200.0, 1)


class ExplodingBackend(FakeBackend):
    async def transcribe(self, pcm_8k: bytes) -> TranscriptOutcome:
        raise TimeoutError("prisma hung")


def test_sweep_scores_writes_csv_report_and_reuses_cache(settings: AppSettings, scorer: Scorer, tmp_path: Path) -> None:
    corpus = sample_corpus(build_corpus(), 3)
    items = build_work_items(corpus, ["harbour"], [10.0, 5.0], include_clean=True)
    assert len(items) == 3 + 3 * 1 * 2
    cache = DiskCache(tmp_path / "cache", settings, 300, 860)
    backend = FakeBackend({})

    transcripts = asyncio.run(gather_transcripts(items, backend, cache, settings, concurrency=2))
    assert backend.calls == {"tts": 3, "stt": len(items)}  # TTS once per utterance, not per item

    rows = score_rows(items, transcripts, scorer)
    write_csv(rows, tmp_path / "results.csv")
    with (tmp_path / "results.csv").open(encoding="utf-8") as fh:
        records = list(csv.DictReader(fh))
    assert len(records) == len(items) and {r["profile"] for r in records} == {CLEAN_PROFILE, "harbour"}

    report = render_report(rows, threshold_sweep(rows, scorer), settings, {"date": "2026-10-27", "scope": "test"})
    for needle in ("synthetic", "SFER gate ON", "Threshold sensitivity", "harbour @ 10 dB", "Failure modes"):
        assert needle in report

    again = asyncio.run(gather_transcripts(items, None, cache, settings, concurrency=2))  # analyze-only
    assert all(o.error is None for o in again.values())
    assert {k: v.transcript for k, v in again.items()} == {k: v.transcript for k, v in transcripts.items()}


def test_failed_items_are_recorded_and_excluded_not_fatal(settings: AppSettings, scorer: Scorer, tmp_path: Path) -> None:
    items = build_work_items(sample_corpus(build_corpus(), 2), ["traffic"], [15.0], include_clean=False)
    cache = DiskCache(tmp_path / "cache", settings, 300, 860)
    transcripts = asyncio.run(gather_transcripts(items, ExplodingBackend({}), cache, settings, concurrency=2))
    assert all(o.error and "TimeoutError" in o.error for o in transcripts.values())
    rows = score_rows(items, transcripts, scorer)
    cell = summarize("traffic", rows)
    assert (cell.n, cell.failed, cell.trades) == (0, 2, 0)
    assert cache.load_transcript(items[0]) is None  # failures are never cached


def test_summarize_pools_sfer_over_trades(scorer: Scorer) -> None:
    utt = _utt("single_01")
    good = scorer.score(utt, utt.spoken_text, 100.0)
    bad = scorer.score(utt, utt.spoken_text.replace("250", "520"), 300.0)
    from benchmark.run_eval import EvalRow, WorkItem

    rows: List[EvalRow] = [
        EvalRow(WorkItem(utt, "market", 5.0), TranscriptOutcome("a", 100.0, 1), good),
        EvalRow(WorkItem(utt, "market", 5.0), TranscriptOutcome("b", 300.0, 1), bad),
    ]
    cell = summarize("x", rows)
    assert cell.trades == 2 and cell.errors_gated == 1 and cell.sfer_gated == pytest.approx(0.5)
    assert cell.entity_accuracy["rate"] == pytest.approx(0.5)
    assert cell.stt_p50 == pytest.approx(200.0)


def test_conditions_filter_selects_only_listed_cells() -> None:
    from benchmark.run_eval import build_work_items, filter_conditions, parse_conditions

    corpus = build_corpus()[:2]
    items = build_work_items(corpus, ["harbour", "market"], [10.0, 5.0], True)
    kept = filter_conditions(items, "clean,harbour:10")
    assert {(i.profile, i.snr_db) for i in kept} == {("clean", None), ("harbour", 10.0)}
    assert len(kept) == 4
    assert parse_conditions("market:5") == [("market", 5.0)]
    with __import__("pytest").raises(ValueError):
        parse_conditions("harbour")
