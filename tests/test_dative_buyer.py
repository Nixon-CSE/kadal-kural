"""A buyer comes only from a dative phrase in the clause itself, or from the held trade on a மட்டும் override."""

from __future__ import annotations

from pathlib import Path

import pytest

from kadal_kural.config import UNRESOLVED_BUYER_ID, UNRESOLVED_BUYER_LABEL, AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import HeldTradeContext, LedgerEventStatus
from kadal_kural.domain.normalizer import strip_tamil_dative_suffix
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

SENTHIL = "BUY-101"
SENTHIL_OPENING_BALANCE = 128_000

# Ledger row 35, 19:16:04: no buyer spoken. It used to fuzzy-match the fish name to Kumaran (0.386).
ROW_19_16_04 = "வஞ்சரம் 500 ரேட்டு"


@pytest.fixture
def service(tmp_path: Path) -> PreDispatchCreditFirewallService:
    settings = AppSettings(db_path=str(tmp_path / "dative.db"))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    return PreDispatchCreditFirewallService(settings, matcher, repo)


def test_bare_ku_glued_to_a_name_is_dative() -> None:
    # Live probe: Tanglish 'Senthil ku' comes back from Prisma as 'செந்தில்கு'.
    assert strip_tamil_dative_suffix("செந்தில்கு") == "செந்தில்"


def test_bare_ku_keeps_the_length_guard() -> None:
    assert strip_tamil_dative_suffix("கு") == "கு"
    assert strip_tamil_dative_suffix("பகு") == "பகு"  # one letter before the suffix: too short


def test_bare_ku_does_not_shadow_longer_suffixes() -> None:
    assert strip_tamil_dative_suffix("குமரனுக்கு") == "குமரன்"
    assert strip_tamil_dative_suffix("செந்திலுக்கு") == "செந்தில்"
    assert strip_tamil_dative_suffix("சீஃபுட்ஸ்க்கு") == "சீஃபுட்ஸ்"


def test_row_19_16_04_has_no_buyer_and_its_sku_is_resolved(
    service: PreDispatchCreditFirewallService,
) -> None:
    (decision,) = service.evaluate_utterance(ROW_19_16_04)
    assert decision.status == LedgerEventStatus.PENDING_CLARIFICATION
    assert (decision.buyer_id, decision.buyer_name) == (UNRESOLVED_BUYER_ID, UNRESOLVED_BUYER_LABEL)
    assert decision.sku_name == "Export Vanjaram"


def test_nominative_buyer_is_held_not_booked_to_a_guess(
    service: PreDispatchCreditFirewallService,
) -> None:
    (decision,) = service.evaluate_utterance("செந்தில் 10 கிலோ வஞ்சரம் 800 ரேட்டு")
    assert decision.status == LedgerEventStatus.PENDING_CLARIFICATION
    assert decision.buyer_name == UNRESOLVED_BUYER_LABEL
    assert service.repository.get_buyer_row(SENTHIL)["running_balance_inr"] == SENTHIL_OPENING_BALANCE


def test_bare_ku_buyer_books(service: PreDispatchCreditFirewallService) -> None:
    (decision,) = service.evaluate_utterance("செந்தில்கு 10 கிலோ வஞ்சரம் 800 ரேட்டு")
    assert decision.status == LedgerEventStatus.BOOKED
    assert decision.buyer_id == SENTHIL


def test_held_buyer_is_inherited_only_on_a_mattum_override() -> None:
    matcher = BilingualCatalogMatcher(AppSettings().catalog_path)
    held = HeldTradeContext(buyer_id=SENTHIL, sku_id="SKU-VAN-EXP", rate_inr=740, blocked_event_id=1)

    (override,) = matcher.parse_utterance("25 கிலோ மட்டும் போடு", held_context=held)
    assert override.buyer_id == SENTHIL and override.is_barge_in_override

    (fragment,) = matcher.parse_utterance(ROW_19_16_04, held_context=held)
    assert fragment.buyer_id is None and fragment.buyer_confidence == 0.0
