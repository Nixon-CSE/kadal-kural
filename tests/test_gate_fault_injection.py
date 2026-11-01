"""
Confidence-gate fault injection: take correct transcripts, corrupt their numbers the way
speech recognition does (drop a digit, add a digit, double a number, glue a suffix onto a
hundreds word), and check the gate holds each corrupted trade for clarification while the
same firewall with the gate off would book it.

What the gate does with each corruption (run ``pytest -rxX`` to list the misses):

    caught   rate digit dropped/added (560 -> 56, 50, 5600, 5660): outside the rate band
    caught   suffix the normalizer can't strip (ஐநூற்றுல / ஐநூற்றே / ஐநூறுக்கு 60 -> rate 60)
    caught   hybrid split (ஐநூற்று 60 heard as 500 60): the 60 is a number left over after the rate
    MISSED   quantity digit dropped/added (50 -> 5 kg, 5 -> 50 kg): still inside 1-1,000 kg
    n/a      suffix -க்கு / -க்கும் (ஐநூற்றுக்கு 60): the normalizer recovers 560, books correctly
    n/a      repeated rate (560 560): the extra number is ignored, books correctly
    blocked  repeated quantity (5 5 கிலோ): no SKU resolves, held even with the gate off
    blocked  quantity x1000 (5 -> 5000 kg): gate holds it; without the gate the credit hold does
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

import pytest

from kadal_kural.config import LEFTOVER_NUMBER_CONFIDENCE, AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import CreditGateDecision, LedgerEventStatus
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

NO_GATE = 0.0  # same as benchmark/scoring.py: structural checks still apply

# Correct transcripts (Kumaran has 38,000 of credit headroom; every one books as spoken).
DIGIT_RATE = "குமரனுக்கு 5 கிலோ டைகர் பிரான் 560 ரேட்டு"  # 5 kg @ 560
HYBRID_RATE = "குமரனுக்கு 5 கிலோ டைகர் பிரான் ஐநூற்று 60 ரேட்டு"  # 5 kg @ 560
BIG_QTY = "குமரனுக்கு 50 கிலோ டைகர் பிரான் 560 ரேட்டு"  # 50 kg @ 560


def replace_token(old: str, new: str) -> Callable[[str], str]:
    """A corruption that swaps one whole token of the transcript."""

    def corrupt(transcript: str) -> str:
        tokens = transcript.split()
        assert tokens.count(old) == 1, f"{old!r} must appear once in {transcript!r}"
        return " ".join(new if t == old else t for t in tokens)

    return corrupt


def drop_digit(number: str, index: int) -> Callable[[str], str]:
    return replace_token(number, number[:index] + number[index + 1:])


def add_digit(number: str, index: int, digit: str) -> Callable[[str], str]:
    return replace_token(number, number[:index] + digit + number[index:])


def double(token: str) -> Callable[[str], str]:
    return replace_token(token, f"{token} {token}")


def glue_suffix(hundreds_word: str, suffix: str) -> Callable[[str], str]:
    return replace_token(hundreds_word, hundreds_word + suffix)


@dataclass(frozen=True)
class Corruption:
    name: str
    correct: str
    corrupt: Callable[[str], str]

    @property
    def transcript(self) -> str:
        return self.corrupt(self.correct)


def _decide(tmp_path: Path, transcript: str, *, gate: bool) -> List[CreditGateDecision]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    settings = AppSettings(db_path=str(tmp_path / f"gate_{gate}.db"))
    if not gate:
        settings = settings.model_copy(update={"confidence_threshold": NO_GATE})
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    return PreDispatchCreditFirewallService(settings, matcher, repo).evaluate_utterance(transcript)


IN_RANGE_QUANTITY_MISS = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "in-range quantity digit errors are not caught pre-booking; "
        "mitigated by spoken read-back + voice undo; buyer-history check deferred"
    ),
)


GATE_CASES = [
    pytest.param(Corruption("rate: drop last digit", DIGIT_RATE, drop_digit("560", 2)), id="rate-drop-last-digit"),
    pytest.param(Corruption("rate: drop middle digit", DIGIT_RATE, drop_digit("560", 1)), id="rate-drop-middle-digit"),
    pytest.param(Corruption("rate: add trailing digit", DIGIT_RATE, add_digit("560", 3, "0")), id="rate-add-trailing-digit"),
    pytest.param(Corruption("rate: add inner digit", DIGIT_RATE, add_digit("560", 2, "6")), id="rate-add-inner-digit"),
    pytest.param(Corruption("suffix -ல on hundreds word", HYBRID_RATE, glue_suffix("ஐநூற்று", "ல")), id="suffix-la"),
    pytest.param(Corruption("suffix -ே on hundreds word", HYBRID_RATE, glue_suffix("ஐநூற்று", "ே")), id="suffix-e"),
    pytest.param(
        Corruption("suffix on round hundreds word", HYBRID_RATE, replace_token("ஐநூற்று", "ஐநூறுக்கு")),
        id="suffix-on-round-hundred",
    ),
    pytest.param(
        Corruption("quantity: drop a digit", BIG_QTY, drop_digit("50", 1)),
        id="qty-drop-digit",
        marks=IN_RANGE_QUANTITY_MISS,
    ),
    pytest.param(
        Corruption("quantity: add a digit", DIGIT_RATE, add_digit("5", 1, "0")),
        id="qty-add-digit",
        marks=IN_RANGE_QUANTITY_MISS,
    ),
    pytest.param(
        Corruption("hybrid split: ஐநூற்று 60 -> 500 60", HYBRID_RATE, replace_token("ஐநூற்று", "500")),
        id="hybrid-split",
    ),
]


@pytest.mark.parametrize("case", GATE_CASES)
def test_gate_holds_corrupted_numbers_that_would_book_without_it(case: Corruption, tmp_path: Path) -> None:
    (correct,) = _decide(tmp_path / "correct", case.correct, gate=True)
    assert correct.status == LedgerEventStatus.BOOKED  # the uncorrupted transcript is fine
    (ungated,) = _decide(tmp_path / "off", case.transcript, gate=False)
    assert ungated.status == LedgerEventStatus.BOOKED, "without the gate the corruption books"
    assert (ungated.quantity, ungated.rate_inr) != (correct.quantity, correct.rate_inr), "and books wrong"
    (gated,) = _decide(tmp_path / "on", case.transcript, gate=True)
    assert gated.status == LedgerEventStatus.PENDING_CLARIFICATION


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(Corruption("suffix -க்கு", HYBRID_RATE, glue_suffix("ஐநூற்று", "க்கு")), id="suffix-kku"),
        pytest.param(Corruption("suffix -க்கும்", HYBRID_RATE, glue_suffix("ஐநூற்று", "க்கும்")), id="suffix-kkum"),
        pytest.param(Corruption("repeated rate", DIGIT_RATE, double("560")), id="double-rate"),
    ],
)
def test_corruptions_the_parser_recovers_still_book_correctly(case: Corruption, tmp_path: Path) -> None:
    for gate in (True, False):
        (decision,) = _decide(tmp_path / str(gate), case.transcript, gate=gate)
        assert decision.status == LedgerEventStatus.BOOKED
        assert (decision.quantity, decision.unit, decision.rate_inr) == (5, "kg", 560)


def test_repeated_quantity_is_held_even_without_the_gate(tmp_path: Path) -> None:
    transcript = double("5")(DIGIT_RATE)  # second 5 is read as the rate, leaving no SKU phrase
    for gate in (True, False):
        (decision,) = _decide(tmp_path / str(gate), transcript, gate=gate)
        assert decision.status == LedgerEventStatus.PENDING_CLARIFICATION


def test_thousandfold_quantity_is_held_by_the_gate_and_by_the_credit_limit_without_it(tmp_path: Path) -> None:
    transcript = add_digit("5", 1, "000")(DIGIT_RATE)  # 5000 kg
    (gated,) = _decide(tmp_path / "on", transcript, gate=True)
    (ungated,) = _decide(tmp_path / "off", transcript, gate=False)
    assert gated.status == LedgerEventStatus.PENDING_CLARIFICATION
    assert ungated.status == LedgerEventStatus.CREDIT_HOLD_BREACH


def test_merged_clause_with_no_second_buyer_is_held_not_half_booked(tmp_path: Path) -> None:
    # misheard terminator and no buyer to split on: the second trade's numbers are left over,
    # so nothing books (tests/test_clause_boundaries.py covers merges a buyer name can split)
    transcript = "செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 வேட்டு 5 கிலோ டைகர் பிரான் 560 வேட்டு"
    (decision,) = _decide(tmp_path, transcript, gate=True)
    assert decision.status == LedgerEventStatus.PENDING_CLARIFICATION
    assert decision.confidence == LEFTOVER_NUMBER_CONFIDENCE


def test_exact_repeat_of_the_rate_is_not_a_leftover(tmp_path: Path) -> None:
    (decision,) = _decide(tmp_path, double("560")(DIGIT_RATE), gate=True)
    assert decision.status == LedgerEventStatus.BOOKED and decision.confidence > LEFTOVER_NUMBER_CONFIDENCE
