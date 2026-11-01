"""Clause-boundary robustness: buyer names start clauses, and the rate may sit on either side of the rate word."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from benchmark.corpus import build_corpus
from kadal_kural.config import AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import LedgerEventStatus, TradeIntent
from kadal_kural.domain.normalizer import split_multi_trade_clauses
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

SENTHIL, KUMARAN = "BUY-101", "BUY-102"
VANJARAM, PRAWN = "SKU-VAN-EXP", "SKU-PRW-TIG"
Trade = Tuple[str, str, int, str, int]  # buyer, SKU, quantity, unit, rate

# Real Prisma output at market @ 5 dB: the ரேட்டு terminator was misheard (வேட்டு, ரேக்கு, ரைட்டு).
MERGED_TRANSCRIPTS: Dict[str, str] = {
    "multi_02": "செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 வேட்டு குமரனுக்கு 10 கிலோ வஞ்சரம் 800 வேட்டு",
    "multi_13": "குமரனுக்கு 40 கிலோ எக்ஸ்போர்ட் வஞ்சரம் எழுநூற்றி 40 ரேக்கு செந்திலுக்கு 30 கிலோ டைகர் பிரான் நானூற்றி 50 ரேக்கு",
    "multi_20": "செந்திலுக்கு 30 கிலோ வஞ்சரம் 600 வேட்டு செந்திலி சிவக்கு 40 கிலோ வஞ்சரம் 600 வேட்டு",
    "multi_21": "குமரனுக்கு 20 கிலோ டைகர் பிரான் 350 ரைட்டு குமரனுக்கு 10 கிலோ டைகர் பிரான் 500 ரைட்டு",
}


@pytest.fixture(scope="module")
def matcher() -> BilingualCatalogMatcher:
    return BilingualCatalogMatcher(AppSettings().catalog_path)


def _trades(intents: List[TradeIntent]) -> List[Tuple[object, ...]]:
    return [(i.buyer_id, i.sku_id, i.quantity, i.unit, i.rate_inr) for i in intents]


def _split(matcher: BilingualCatalogMatcher, text: str) -> List[str]:
    return split_multi_trade_clauses(text, matcher._buyer_phrase_length)


# ------------------------------------------------------------------------- merged real transcripts


@pytest.mark.parametrize("utterance_id", MERGED_TRANSCRIPTS)
def test_merged_transcripts_produce_their_two_true_trades(utterance_id: str, matcher: BilingualCatalogMatcher) -> None:
    truth = next(u for u in build_corpus() if u.utterance_id == utterance_id).ground_truth_trades
    intents = matcher.parse_utterance(MERGED_TRANSCRIPTS[utterance_id])
    assert len(intents) == len(truth) == 2
    for intent, expected in zip(intents, truth):
        assert intent.buyer_id == expected.buyer_id
        assert intent.sku_id is not None and matcher.skus[intent.sku_id].canonical_name == expected.sku_canonical_name
        assert (intent.quantity, intent.unit, intent.rate_inr) == (expected.quantity, expected.unit, expected.rate_inr)
        assert intent.overall_confidence >= AppSettings().confidence_threshold


@pytest.mark.parametrize(
    ("utterance_id", "statuses"),
    [
        ("multi_02", [LedgerEventStatus.BOOKED, LedgerEventStatus.BOOKED]),
        ("multi_13", [LedgerEventStatus.BOOKED, LedgerEventStatus.BOOKED]),
        ("multi_20", [LedgerEventStatus.BOOKED, LedgerEventStatus.CREDIT_HOLD_BREACH]),  # 18,000 + 24,000 > 22,000
        ("multi_21", [LedgerEventStatus.BOOKED, LedgerEventStatus.BOOKED]),
    ],
)
def test_merged_transcripts_reach_the_firewall_as_two_trades(
    utterance_id: str, statuses: List[LedgerEventStatus], tmp_path: Path
) -> None:
    settings = AppSettings(db_path=str(tmp_path / "ledger.db"))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    service = PreDispatchCreditFirewallService(settings, matcher, repo)
    assert [d.status for d in service.evaluate_utterance(MERGED_TRANSCRIPTS[utterance_id])] == statuses


# ------------------------------------------------------------------------- rate on either side


@pytest.mark.parametrize(
    "transcript",
    [
        pytest.param("குமரனுக்கு 5 கிலோ டைகர் பிரான் 560 ரேட்டு", id="rate-before"),
        pytest.param("குமரனுக்கு 5 கிலோ டைகர் பிரான் ரேட்டு 560", id="rate-after"),
        pytest.param("குமரனுக்கு 5 கிலோ டைகர் பிரான் ஐநூற்று 60 ரேட்டு", id="hybrid-before"),
        pytest.param("குமரனுக்கு 5 கிலோ டைகர் பிரான் ரேட்டு ஐநூற்று 60", id="hybrid-after"),
        pytest.param("குமரனுக்கு 5 கிலோ டைகர் பிரான் ரேட் 560 கிரெடிட்டில் ஏற்று", id="after-then-ledger-verb"),
    ],
)
def test_single_trade_reads_the_same_in_either_word_order(transcript: str, matcher: BilingualCatalogMatcher) -> None:
    (intent,) = matcher.parse_utterance(transcript)
    assert _trades([intent]) == [(KUMARAN, PRAWN, 5, "kg", 560)]
    assert intent.overall_confidence == 1.0


@pytest.mark.parametrize(
    "transcript",
    [
        pytest.param("செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 ரேட்டு குமரனுக்கு 5 கிலோ டைகர் பிரான் 560 ரேட்டு", id="both-before"),
        pytest.param("செந்திலுக்கு 10 கிலோ வஞ்சரம் ரேட்டு 800 குமரனுக்கு 5 கிலோ டைகர் பிரான் ரேட்டு 560", id="both-after"),
        pytest.param("செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 ரேட்டு குமரனுக்கு 5 கிலோ டைகர் பிரான் ரேட்டு 560", id="before-then-after"),
        pytest.param("செந்திலுக்கு 10 கிலோ வஞ்சரம் ரேட்டு 800 குமரனுக்கு 5 கிலோ டைகர் பிரான் 560 ரேட்டு", id="after-then-before"),
    ],
)
def test_two_trades_read_the_same_in_any_word_order(transcript: str, matcher: BilingualCatalogMatcher) -> None:
    assert _trades(matcher.parse_utterance(transcript)) == [
        (SENTHIL, VANJARAM, 10, "kg", 800),
        (KUMARAN, PRAWN, 5, "kg", 560),
    ]


def test_number_after_the_rate_word_is_not_the_rate_when_the_clause_has_one() -> None:
    text = "குமரனுக்கு 5 கிலோ டைகர் பிரான் 560 ரேட்டு 30 கிலோ வஞ்சரம் 800 ரேட்டு"
    assert split_multi_trade_clauses(text) == ["குமரனுக்கு 5 கிலோ டைகர் பிரான் 560", "30 கிலோ வஞ்சரம் 800"]


def test_number_followed_by_a_unit_after_the_rate_word_is_the_next_quantity() -> None:
    text = "குமரனுக்கு 560 ரேட்டு 30 கிலோ வஞ்சரம் 800 ரேட்டு"
    assert split_multi_trade_clauses(text) == ["குமரனுக்கு 560", "30 கிலோ வஞ்சரம் 800"]


# ------------------------------------------------------------------------- buyer boundaries


def test_word_before_a_one_word_buyer_stays_in_the_previous_clause(matcher: BilingualCatalogMatcher) -> None:
    assert _split(matcher, "செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 வேட்டு குமரனுக்கு 5 கிலோ") == [
        "செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 வேட்டு",
        "குமரனுக்கு 5 கிலோ",
    ]


@pytest.mark.parametrize(
    ("buyer_words", "buyer_id"),
    [("செந்தில் சீஃபுட்ஸ்க்கு", SENTHIL), ("Kumaran ku", KUMARAN)],
    ids=["two-word-tamil", "tanglish"],
)
def test_two_word_dative_buyer_starts_the_new_clause_whole(
    buyer_words: str, buyer_id: str, matcher: BilingualCatalogMatcher
) -> None:
    first = "குமரனுக்கு 5 கிலோ டைகர் பிரான் 560"
    second = f"{buyer_words} 10 கிலோ வஞ்சரம் 800"
    assert _split(matcher, f"{first} {second}") == [first, second]
    assert [i.buyer_id for i in matcher.parse_utterance(f"{first} {second}")] == [KUMARAN, buyer_id]


def test_buyer_name_before_any_number_does_not_split(matcher: BilingualCatalogMatcher) -> None:
    text = "செந்தில் சீஃபுட்ஸ்க்கு 10 கிலோ வஞ்சரம் 800"
    assert _split(matcher, text) == [text]


def test_unknown_dative_word_mid_clause_is_not_a_boundary(matcher: BilingualCatalogMatcher) -> None:
    text = "செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 ராமனுக்கு 5 கிலோ"
    assert _split(matcher, text) == [text]


def test_misspelled_rate_word_is_not_a_terminator() -> None:
    text = "செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 வேட்டு 5 கிலோ டைகர் பிரான் 560 ரைட்டு"
    assert split_multi_trade_clauses(text) == [text]
