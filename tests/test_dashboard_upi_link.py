"""/api/v1/state: only a booked trade that no later undo voided carries a visible UPI link."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from kadal_kural.api.main import create_app
from kadal_kural.config import AppSettings
from kadal_kural.domain.models import LedgerEventStatus

# Senthil breaches the credit limit (CREDIT_HOLD_BREACH); Kumaran books (BOOKED).
BREACH_AND_BOOK = (
    "செந்தில் சீஃபுட்ஸ்க்கு 40 கிலோ எக்ஸ்போர்ட் வஞ்சரம் எழுநூற்றி 40 ரேட்டு "
    "குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு கிரெடிட்டில் ஏற்று"
)
BARGE_IN_OVERRIDE = "செந்திலுக்கு 25 கிலோ மட்டும் போடு"  # BOOKED_AFTER_BARGE_IN
UNKNOWN_BUYER = "புது கடைக்கு 30 பாக்ஸ் வஞ்சரம் போடு"  # PENDING_CLARIFICATION
VOICE_UNDO = "கடைசி ஆர்டர் கேன்சல்"  # VOIDED_BY_UNDO of the latest booked trade


def _ingest(client: TestClient, transcript: str) -> List[Dict[str, Any]]:
    response = client.post(
        "/api/v1/ingest", json={"transcript": transcript, "synthesize_tts": False}
    )
    assert response.status_code == 200
    decisions: List[Dict[str, Any]] = response.json()["decisions"]
    return decisions


def _events_by_id(client: TestClient) -> Dict[int, Dict[str, Any]]:
    response = client.get("/api/v1/state")
    assert response.status_code == 200
    return {int(e["event_id"]): e for e in response.json()["events"]}


def test_upi_link_is_visible_only_for_unvoided_booked_trades(tmp_path: Path) -> None:
    app = create_app(AppSettings(db_path=str(tmp_path / "upi.db")))
    with TestClient(app) as client:
        breach, booked = _ingest(client, BREACH_AND_BOOK)
        assert breach["status"] == LedgerEventStatus.CREDIT_HOLD_BREACH.value
        assert breach["upi_payment_uri"], "the breach row still stores a URI; only the flag hides it"
        assert booked["status"] == LedgerEventStatus.BOOKED.value

        (barge_in,) = _ingest(client, BARGE_IN_OVERRIDE)
        assert barge_in["status"] == LedgerEventStatus.BOOKED_AFTER_BARGE_IN.value

        (pending,) = _ingest(client, UNKNOWN_BUYER)
        assert pending["status"] == LedgerEventStatus.PENDING_CLARIFICATION.value

        events = _events_by_id(client)
        assert events[breach["event_id"]]["upi_link_visible"] is False
        assert events[booked["event_id"]]["upi_link_visible"] is True
        assert events[barge_in["event_id"]]["upi_link_visible"] is True
        assert events[pending["event_id"]]["upi_link_visible"] is False

        (undo,) = _ingest(client, VOICE_UNDO)
        assert undo["status"] == LedgerEventStatus.VOIDED_BY_UNDO.value

        events = _events_by_id(client)
        assert events[undo["event_id"]]["upi_link_visible"] is False
        assert events[undo["event_id"]]["voids_event_id"] == barge_in["event_id"]
        assert events[barge_in["event_id"]]["upi_link_visible"] is False, "voided original"
        assert events[booked["event_id"]]["upi_link_visible"] is True, "untouched by the undo"
        assert events[breach["event_id"]]["upi_link_visible"] is False
        assert events[pending["event_id"]]["upi_link_visible"] is False


def test_ledger_created_before_undo_links_gains_the_column(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE ledger_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                buyer_id TEXT NOT NULL, buyer_name TEXT NOT NULL, sku_name TEXT NOT NULL,
                quantity INTEGER NOT NULL, unit TEXT NOT NULL, rate_inr INTEGER NOT NULL,
                trade_value_inr INTEGER NOT NULL, previous_balance_inr INTEGER NOT NULL,
                projected_balance_inr INTEGER NOT NULL, credit_limit_inr INTEGER NOT NULL,
                status TEXT NOT NULL, confidence REAL NOT NULL, raw_utterance TEXT NOT NULL,
                normalized_clause TEXT NOT NULL, upi_payment_uri TEXT NOT NULL
            )
            """
        )
    app = create_app(AppSettings(db_path=str(db_path)))
    with TestClient(app) as client:
        _, booked = _ingest(client, BREACH_AND_BOOK)
        (undo,) = _ingest(client, VOICE_UNDO)
        events = _events_by_id(client)
        assert events[undo["event_id"]]["voids_event_id"] == booked["event_id"]
        assert events[booked["event_id"]]["upi_link_visible"] is False
