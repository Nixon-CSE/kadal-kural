"""Unit and integration tests for the Kadal Kural Pre-Dispatch Credit Firewall."""

from __future__ import annotations

from pathlib import Path
from kadal_kural.config import AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import LedgerEventStatus
from kadal_kural.domain.normalizer import (
    format_inr_for_timbre_prosody,
    normalize_hybrid_tamil_numerals,
    strip_tamil_dative_suffix,
)
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

PLAYGROUND_SCREENSHOT_TRANSCRIPT = (
    "செந்தில் சீஃபுட்ஸ்க்கு 40 பாக்ஸ் எக்ஸ்போர்ட் வஞ்சரம் எழுநூற்றி 40 ரேட்டு "
    "குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு கிரெடிட்டில் ஏற்று"
)


def test_normalize_hybrid_tamil_numerals_from_playground() -> None:
    normalized = normalize_hybrid_tamil_numerals(PLAYGROUND_SCREENSHOT_TRANSCRIPT)
    assert "740" in normalized
    assert "560" in normalized
    assert "எழுநூற்றி" not in normalized
    assert "ஐநூற்றி" not in normalized


def test_strip_tamil_dative_suffixes() -> None:
    assert strip_tamil_dative_suffix("செந்தில் சீஃபுட்ஸ்க்கு") == "செந்தில் சீஃபுட்ஸ்"
    assert strip_tamil_dative_suffix("குமரனுக்கு") == "குமரன்"
    assert strip_tamil_dative_suffix("செந்திலுக்கு") == "செந்தில்"


def test_format_inr_for_timbre_prosody() -> None:
    assert format_inr_for_timbre_prosody(128000) == "1 லட்சத்து 28 ஆயிரம் ரூபாய்"
    assert format_inr_for_timbre_prosody(150000) == "1 லட்சத்து 50 ஆயிரம் ரூபாய்"
    assert format_inr_for_timbre_prosody(29600) == "ரூபாய் 29,600"


def test_end_to_end_credit_firewall_and_barge_in(tmp_path: Path) -> None:
    db_file = tmp_path / "test_kadal.db"
    settings = AppSettings(db_path=str(db_file))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    service = PreDispatchCreditFirewallService(settings, matcher, repo)

    decisions = service.evaluate_utterance(PLAYGROUND_SCREENSHOT_TRANSCRIPT, stt_latency_ms=288.0)
    assert len(decisions) == 2

    senthil_decision, kumaran_decision = decisions
    assert senthil_decision.status == LedgerEventStatus.CREDIT_HOLD_BREACH
    assert senthil_decision.trade_value_inr == 29_600
    assert senthil_decision.projected_balance_inr == 157_600
    assert senthil_decision.excess_amount_inr == 7_600

    assert kumaran_decision.status == LedgerEventStatus.BOOKED
    assert kumaran_decision.trade_value_inr == 33_600
    assert kumaran_decision.projected_balance_inr == 75_600

    # Verify Senthil balance was NOT committed during credit hold
    assert repo.get_buyer_row("BUY-101")["running_balance_inr"] == 128_000

    # Step 2: Barge-in quantity override
    override_decisions = service.evaluate_utterance("செந்திலுக்கு 25 பாக்ஸ் மட்டும் போடு")
    assert len(override_decisions) == 1
    override = override_decisions[0]
    assert override.status == LedgerEventStatus.BOOKED_AFTER_BARGE_IN
    assert override.trade_value_inr == 18_500
    assert override.projected_balance_inr == 146_500
    assert repo.get_buyer_row("BUY-101")["running_balance_inr"] == 146_500


def test_voice_undo_compensating_transaction(tmp_path: Path) -> None:
    db_file = tmp_path / "test_undo.db"
    settings = AppSettings(db_path=str(db_file))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    service = PreDispatchCreditFirewallService(settings, matcher, repo)

    # Book Kumaran stores (42,000 + 33,600 = 75,600)
    service.evaluate_utterance(
        "குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு கிரெடிட்டில் ஏற்று"
    )
    assert repo.get_buyer_row("BUY-102")["running_balance_inr"] == 75_600

    # Issue Voice Undo
    undo_decisions = service.evaluate_utterance("கடைசி ஆர்டர் கேன்சல்")
    assert len(undo_decisions) == 1
    assert undo_decisions[0].status == LedgerEventStatus.VOIDED_BY_UNDO
    assert undo_decisions[0].projected_balance_inr == 42_000
    assert repo.get_buyer_row("BUY-102")["running_balance_inr"] == 42_000


def test_confidence_gate_blocks_unknown_buyer(tmp_path: Path) -> None:
    db_file = tmp_path / "test_gate.db"
    settings = AppSettings(db_path=str(db_file))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    service = PreDispatchCreditFirewallService(settings, matcher, repo)

    decisions = service.evaluate_utterance("புது கடைக்கு 30 பாக்ஸ் வஞ்சரம் போடு")
    assert len(decisions) == 1
    assert decisions[0].status == LedgerEventStatus.PENDING_CLARIFICATION
