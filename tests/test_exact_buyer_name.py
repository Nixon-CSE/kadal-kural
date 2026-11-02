"""A full registered buyer name opening a clause exactly needs no dative suffix; nothing looser does."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from kadal_kural.config import UNRESOLVED_BUYER_LABEL, AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import LedgerEventStatus
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

SENTHIL = "BUY-101"
SENTHIL_OPENING_BALANCE = 128_000


@pytest.fixture
def service(tmp_path: Path) -> PreDispatchCreditFirewallService:
    settings = AppSettings(db_path=str(tmp_path / "exact.db"))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    return PreDispatchCreditFirewallService(settings, matcher, repo)


@pytest.mark.parametrize("name", ["செந்தில் சீஃபுட்ஸ்", "Senthil Sea Foods"])
def test_exact_full_name_without_suffix_books(service: PreDispatchCreditFirewallService, name: str) -> None:
    (decision,) = service.evaluate_utterance(f"{name} 10 கிலோ வஞ்சரம் 800 ரேட்டு")
    assert decision.status == LedgerEventStatus.BOOKED
    assert decision.buyer_id == SENTHIL


@pytest.mark.parametrize(
    "utterance",
    [
        pytest.param("செந்தில் 10 கிலோ வஞ்சரம் 800 ரேட்டு", id="partial-name"),
        pytest.param("செந்தில் சீ பிட்ஸ் 10 கிலோ வஞ்சரம் 800 ரேட்டு", id="fuzzy-full-name"),
        pytest.param("வஞ்சரம் செந்தில் சீஃபுட்ஸ் 10 கிலோ 800 ரேட்டு", id="full-name-not-at-start"),
    ],
)
def test_partial_fuzzy_or_misplaced_name_without_suffix_is_held(
    service: PreDispatchCreditFirewallService, utterance: str
) -> None:
    (decision,) = service.evaluate_utterance(utterance)
    assert decision.status == LedgerEventStatus.PENDING_CLARIFICATION
    assert decision.buyer_name == UNRESOLVED_BUYER_LABEL
    assert service.repository.get_buyer_row(SENTHIL)["running_balance_inr"] == SENTHIL_OPENING_BALANCE


def test_row_19_16_04_still_has_an_unresolved_buyer(service: PreDispatchCreditFirewallService) -> None:
    (decision,) = service.evaluate_utterance("வஞ்சரம் 500 ரேட்டு")
    assert decision.status == LedgerEventStatus.PENDING_CLARIFICATION
    assert decision.buyer_name == UNRESOLVED_BUYER_LABEL
    assert decision.sku_name == "Export Vanjaram"


def _catalog_with_kumaran_alias(tmp_path: Path, alias: str) -> Path:
    catalog: Dict[str, Any] = json.loads(Path(AppSettings().catalog_path).read_text(encoding="utf-8"))
    kumaran = next(b for b in catalog["buyers"] if b["buyer_id"] == "BUY-102")
    kumaran["aliases"].append(alias)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "alias",
    [
        pytest.param("வஞ்சரம்", id="equals-sku-alias"),
        pytest.param("Tiger Prawn", id="equals-sku-name-other-case"),
        pytest.param("குமரன் இறால் கடை", id="contains-sku-alias"),
    ],
)
def test_catalog_load_fails_when_a_buyer_name_contains_a_sku_name(tmp_path: Path, alias: str) -> None:
    with pytest.raises(ValueError, match="BUY-102"):
        BilingualCatalogMatcher(_catalog_with_kumaran_alias(tmp_path, alias))
