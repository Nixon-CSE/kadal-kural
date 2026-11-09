"""Order channels: every ledger entry records how it arrived, and phone entries form a call log."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from kadal_kural.api.main import create_app, phone_call_id
from kadal_kural.config import PHONE_TOKEN_HEADER, AppSettings
from kadal_kural.domain.calls import group_phone_calls
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import EntrySource, LedgerEventStatus, OrderChannel
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

TOKEN = "channel-token"
BOOKABLE = "குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு"
OVER_LIMIT = "செந்திலுக்கு 40 கிலோ வஞ்சரம் 740 ரேட்டு"
UNDO = "கடைசி ஆர்டர் கேன்சல்"


@pytest.fixture
def client(tmp_path: Path) -> Any:
    settings = AppSettings(db_path=str(tmp_path / "channels.db"), phone_webhook_token=TOKEN)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _phone(client: TestClient, transcript: str, **extra: str) -> Any:
    return client.post("/api/v1/phone-turn", json={"transcript": transcript, **extra}, headers={PHONE_TOKEN_HEADER: TOKEN})


def _events(client: TestClient) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = client.get("/api/v1/state").json()["events"]
    return events


# ---------- every entry point records its channel ----------

def test_typed_order_is_recorded_as_typed(client: TestClient) -> None:
    client.post("/api/v1/ingest", json={"transcript": BOOKABLE, "synthesize_tts": False})
    (event,) = _events(client)
    assert event["channel"] == OrderChannel.TYPED.value
    assert event["call_id"] is None
    assert event["recorded_at"]  # full ISO timestamp, not just the time of day


def test_phone_order_is_recorded_with_its_call(client: TestClient) -> None:
    assert _phone(client, BOOKABLE, conversation_id="conv-42").status_code == 200
    (event,) = _events(client)
    assert event["channel"] == OrderChannel.PHONE.value
    assert event["call_id"] == "conv-42"


def test_phone_undo_row_is_recorded_on_the_phone_channel(client: TestClient) -> None:
    client.post("/api/v1/ingest", json={"transcript": BOOKABLE, "synthesize_tts": False})
    _phone(client, UNDO, conversation_id="conv-7")
    void, booking = _events(client)
    assert void["status"] == LedgerEventStatus.VOIDED_BY_UNDO.value
    assert void["channel"] == OrderChannel.PHONE.value and void["call_id"] == "conv-7"
    assert booking["channel"] == OrderChannel.TYPED.value  # the original keeps its own channel


def test_every_entry_of_a_multi_order_sentence_gets_the_channel(tmp_path: Path) -> None:
    settings = AppSettings(db_path=str(tmp_path / "multi.db"))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    service = PreDispatchCreditFirewallService(settings, matcher, repo)
    source = EntrySource(channel=OrderChannel.DESK_VOICE)
    decisions = service.evaluate_utterance(f"{OVER_LIMIT} {BOOKABLE}", source=source)
    assert len(decisions) == 2
    events = repo.fetch_dashboard_snapshot()["events"]
    assert {e["channel"] for e in events} == {OrderChannel.DESK_VOICE.value}


# ---------- the call log ----------

def test_calls_api_groups_phone_turns_and_ignores_other_channels(client: TestClient) -> None:
    client.post("/api/v1/ingest", json={"transcript": BOOKABLE, "synthesize_tts": False})  # not a call
    _phone(client, OVER_LIMIT, conversation_id="call-a")
    _phone(client, BOOKABLE, conversation_id="call-a")
    _phone(client, BOOKABLE, conversation_id="call-b")
    body = client.get("/api/v1/calls").json()
    assert body["phone_channel_enabled"] is True
    assert body["summary"] == {"calls": 2, "entries": 3, "booked_value_inr": 20_000}
    newest, older = body["calls"]
    assert newest["call_id"] == "call-b"
    assert older["call_id"] == "call-a"
    assert [t["status"] for t in older["turns"]] == [LedgerEventStatus.CREDIT_HOLD_BREACH.value, LedgerEventStatus.BOOKED.value]
    assert older["counts"] == {"booked": 1, "held": 1, "asked_again": 0, "undone": 0}
    assert older["booked_value_inr"] == 10_000


def test_calls_without_an_id_are_one_call_while_turns_keep_coming(client: TestClient) -> None:
    _phone(client, OVER_LIMIT)
    _phone(client, BOOKABLE)
    (call,) = client.get("/api/v1/calls").json()["calls"]
    assert call["call_id"] is None and len(call["turns"]) == 2


def test_an_undone_booking_adds_nothing_to_the_calls_booked_value(client: TestClient) -> None:
    _phone(client, BOOKABLE, conversation_id="c1")
    _phone(client, UNDO, conversation_id="c1")
    (call,) = client.get("/api/v1/calls").json()["calls"]
    assert call["booked_value_inr"] == 0
    assert call["counts"]["undone"] == 1
    assert call["turns"][0]["voided"] is True


def test_calls_api_limit_is_validated(client: TestClient) -> None:
    assert client.get("/api/v1/calls?limit=0").status_code == 422
    assert client.get("/api/v1/calls?limit=101").status_code == 422
    assert client.get("/api/v1/calls?limit=1").json()["calls"] == []


def _row(event_id: int, at: str | None, call_id: str | None = None, status: str = "BOOKED", value: int = 100) -> Dict[str, Any]:
    return {"event_id": event_id, "recorded_at": at, "call_id": call_id, "status": status,
            "trade_value_inr": value, "voided": False}


def test_grouping_splits_calls_on_a_long_silence() -> None:
    rows = [_row(1, "2026-11-09T06:20:00+00:00"), _row(2, "2026-11-09T06:21:30+00:00"),
            _row(3, "2026-11-09T06:40:00+00:00")]
    calls = group_phone_calls(rows, gap_seconds=300)
    assert [[t["event_id"] for t in c.turns] for c in calls] == [[3], [1, 2]]  # newest call first


def test_grouping_by_call_id_wins_over_timing() -> None:
    rows = [_row(1, "2026-11-09T06:20:00+00:00", "x"), _row(2, "2026-11-09T06:20:10+00:00", "y"),
            _row(3, "2026-11-09T07:00:00+00:00", "x")]
    calls = group_phone_calls(rows)
    assert {c.call_id: [t["event_id"] for t in c.turns] for c in calls} == {"x": [1, 3], "y": [2]}


def test_an_entry_without_a_timestamp_is_a_call_of_its_own() -> None:
    calls = group_phone_calls([_row(1, None), _row(2, None)])
    assert len(calls) == 2


@pytest.mark.parametrize(
    "fields,expected",
    [({"conversation_id": "conv-1"}, "conv-1"), ({"Call_ID": "CA9f"}, "CA9f"), ({"session_id": "s:1.2"}, "s:1.2"),
     ({"conversation_id": "{{conversation_id}}"}, None), ({"call_id": "bad id with spaces"}, None), ({}, None)],
)
def test_phone_call_id_accepts_plain_ids_only(fields: Dict[str, str], expected: str | None) -> None:
    assert phone_call_id(fields) == expected


# ---------- privacy and upgrades ----------

def test_buyer_contact_numbers_never_reach_the_browser(client: TestClient) -> None:
    buyers = client.get("/api/v1/state").json()["buyers"]
    assert buyers and all("phone_e164" not in b for b in buyers)
    reset = client.post("/api/v1/reset").json()["snapshot"]["buyers"]
    assert all("phone_e164" not in b for b in reset)


def test_catalog_has_no_dialable_numbers(tmp_path: Path) -> None:
    matcher = BilingualCatalogMatcher(AppSettings(db_path=str(tmp_path / "c.db")).catalog_path)
    for buyer in matcher.buyers.values():
        assert buyer.phone_e164.startswith("+9100000"), buyer.phone_e164  # not a valid Indian number


def test_a_ledger_from_before_channels_is_upgraded_in_place(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:  # the schema before channel, call_id and recorded_at existed
        conn.execute(
            """CREATE TABLE ledger_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            buyer_id TEXT NOT NULL, buyer_name TEXT NOT NULL, sku_name TEXT NOT NULL, quantity INTEGER NOT NULL,
            unit TEXT NOT NULL, rate_inr INTEGER NOT NULL, trade_value_inr INTEGER NOT NULL,
            previous_balance_inr INTEGER NOT NULL, projected_balance_inr INTEGER NOT NULL,
            credit_limit_inr INTEGER NOT NULL, status TEXT NOT NULL, confidence REAL NOT NULL,
            raw_utterance TEXT NOT NULL, normalized_clause TEXT NOT NULL, upi_payment_uri TEXT NOT NULL)"""
        )
        conn.execute(
            "INSERT INTO ledger_events VALUES (NULL,'06:00:00','BUY-102','Kumaran Stores','Tiger Prawn',1,'kg',500,500,0,500,80000,'BOOKED',1.0,'old','old','')"
        )
    settings = AppSettings(db_path=str(db))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    PreDispatchCreditFirewallService(settings, matcher, repo).evaluate_utterance(
        BOOKABLE, source=EntrySource(channel=OrderChannel.PHONE, call_id="after")
    )
    new, old = repo.fetch_dashboard_snapshot()["events"]
    assert old["channel"] is None and old["call_id"] is None and old["recorded_at"] is None
    assert new["channel"] == OrderChannel.PHONE.value and new["call_id"] == "after"
