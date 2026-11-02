"""Audit log honesty: a match below the confidence gate is never shown as the buyer or SKU."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from kadal_kural.api.main import create_app
from kadal_kural.config import (
    UNRESOLVED_BUYER_ID,
    UNRESOLVED_BUYER_LABEL,
    UNRESOLVED_SKU_LABEL,
    AppSettings,
)
from kadal_kural.domain.models import LedgerEventStatus

# 'புது கடை' is no registered buyer; the fuzzy matcher's best guess is Senthil Sea Foods at 0.45.
LOW_BUYER = "புது கடைக்கு 30 பாக்ஸ் வஞ்சரம் போடு"
# 'மீன்' (fish) is no SKU; the best guess is Export Vanjaram at 0.6. Kumaran matches exactly.
LOW_SKU = "குமரனுக்கு 60 கிலோ மீன் ஐநூற்றி 60 ரேட்டு கிரெடிட்டில் ஏற்று"
# Buyer and SKU both match exactly; only the ₹5,000/kg rate is out of band.
RATE_ONLY = "குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் 5000 ரேட்டு கிரெடிட்டில் ஏற்று"


@pytest.fixture
def client(tmp_path: Path) -> Any:
    app = create_app(AppSettings(db_path=str(tmp_path / "audit.db")))
    with TestClient(app) as test_client:
        yield test_client


def _ingest_one(client: TestClient, transcript: str) -> Dict[str, Any]:
    response = client.post(
        "/api/v1/ingest", json={"transcript": transcript, "synthesize_tts": False}
    )
    assert response.status_code == 200
    (decision,) = response.json()["decisions"]
    assert decision["status"] == LedgerEventStatus.PENDING_CLARIFICATION.value
    return dict(decision)


def _audit_row(client: TestClient, event_id: int) -> Dict[str, Any]:
    events = client.get("/api/v1/state").json()["events"]
    (row,) = [e for e in events if e["event_id"] == event_id]
    return dict(row)


def test_low_confidence_buyer_is_shown_unresolved_and_guess_kept(client: TestClient) -> None:
    decision = _ingest_one(client, LOW_BUYER)
    assert decision["buyer_name"] == UNRESOLVED_BUYER_LABEL
    assert decision["buyer_id"] == UNRESOLVED_BUYER_ID

    row = _audit_row(client, decision["event_id"])
    assert row["buyer_name"] == UNRESOLVED_BUYER_LABEL
    assert row["buyer_id"] == UNRESOLVED_BUYER_ID
    assert row["buyer_guess"] == "Senthil Sea Foods"
    assert row["buyer_guess_confidence"] == pytest.approx(0.45)
    assert row["sku_name"] == "Export Vanjaram", "a SKU above the gate is still named"
    assert row["raw_utterance"] == LOW_BUYER


def test_low_confidence_sku_is_shown_unresolved_and_guess_kept(client: TestClient) -> None:
    decision = _ingest_one(client, LOW_SKU)
    assert decision["sku_name"] == UNRESOLVED_SKU_LABEL

    row = _audit_row(client, decision["event_id"])
    assert row["sku_name"] == UNRESOLVED_SKU_LABEL
    assert row["sku_guess"] == "Export Vanjaram"
    assert row["sku_guess_confidence"] == pytest.approx(0.6)
    assert row["buyer_name"] == "Kumaran Stores", "a buyer above the gate is still named"
    assert row["buyer_id"] == "BUY-102"


def test_hold_for_another_reason_keeps_confident_names(client: TestClient) -> None:
    decision = _ingest_one(client, RATE_ONLY)
    row = _audit_row(client, decision["event_id"])
    assert (row["buyer_name"], row["sku_name"]) == ("Kumaran Stores", "Tiger Prawn")
    assert row["buyer_guess_confidence"] == pytest.approx(1.0)
    assert row["sku_guess_confidence"] == pytest.approx(1.0)


def test_dashboard_has_a_truncated_heard_column_with_tooltip(client: TestClient) -> None:
    html = client.get("/").text
    assert "<th>Time</th><th>Heard</th><th>Buyer</th>" in html
    assert 'class="heard" title="${escapeHtml(e.raw_utterance)}"' in html
    assert "td.heard {" in html and "text-overflow: ellipsis" in html
