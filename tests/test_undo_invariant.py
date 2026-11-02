"""Voice undo voids only the most recent booking, once; balances always match the live bookings."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pytest

from kadal_kural.config import UNDO_ALREADY_CANCELLED_TAMIL, AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import CreditGateDecision, LedgerEventStatus
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

SENTHIL, KUMARAN = "BUY-101", "BUY-102"
BOOK_SENTHIL = "செந்திலுக்கு 10 கிலோ வஞ்சரம் 800 ரேட்டு"  # ₹8,000, within Senthil's limit
BOOK_KUMARAN = "குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு கிரெடிட்டில் ஏற்று"  # ₹33,600
HOLD_SENTHIL_BOOK_KUMARAN = (  # Senthil breaches the limit (held); Kumaran books
    "செந்தில் சீஃபுட்ஸ்க்கு 40 கிலோ எக்ஸ்போர்ட் வஞ்சரம் எழுநூற்றி 40 ரேட்டு "
    "குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு கிரெடிட்டில் ஏற்று"
)
BARGE_IN_SENTHIL = "செந்திலுக்கு 25 கிலோ மட்டும் போடு"  # BOOKED_AFTER_BARGE_IN on the held trade
UNDO = "கடைசி ஆர்டர் கேன்சல்"
BOOKED_STATUSES = (LedgerEventStatus.BOOKED.value, LedgerEventStatus.BOOKED_AFTER_BARGE_IN.value)


def _build(db_path: Path) -> PreDispatchCreditFirewallService:
    settings = AppSettings(db_path=str(db_path))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    return PreDispatchCreditFirewallService(settings, matcher, repo)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "undo.db"


def _rows(db_path: Path) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM ledger_events ORDER BY event_id")]


def _assert_balance_invariant(service: PreDispatchCreditFirewallService, db_path: Path) -> None:
    """Each buyer's balance == opening balance + the sum of bookings no undo has voided."""
    rows = _rows(db_path)
    voided = {r["voids_event_id"] for r in rows if r["voids_event_id"] is not None}
    for buyer in service.matcher.buyers.values():
        live_bookings = sum(
            r["trade_value_inr"]
            for r in rows
            if r["buyer_id"] == buyer.buyer_id
            and r["status"] in BOOKED_STATUSES
            and r["event_id"] not in voided
        )
        balance = service.repository.get_buyer_row(buyer.buyer_id)["running_balance_inr"]
        assert balance == buyer.opening_balance_inr + live_bookings, buyer.buyer_id


@pytest.mark.parametrize(
    "steps",
    [
        pytest.param([BOOK_KUMARAN, UNDO, UNDO], id="book-undo-undo"),
        pytest.param([BOOK_SENTHIL, BOOK_KUMARAN, UNDO, UNDO], id="bookA-bookB-undo-undo"),
        pytest.param([UNDO], id="undo-empty-ledger"),
        pytest.param([UNDO, UNDO, BOOK_KUMARAN, UNDO, UNDO, UNDO], id="undo-empty-then-book"),
        pytest.param(
            [HOLD_SENTHIL_BOOK_KUMARAN, BARGE_IN_SENTHIL, UNDO, UNDO], id="hold-bargein-undo-undo"
        ),
    ],
)
def test_balances_match_live_bookings_after_every_step(steps: Sequence[str], db_path: Path) -> None:
    service = _build(db_path)
    for utterance in steps:
        service.evaluate_utterance(utterance)
        _assert_balance_invariant(service, db_path)


def _void_rows(db_path: Path) -> List[Dict[str, Any]]:
    return [r for r in _rows(db_path) if r["status"] == LedgerEventStatus.VOIDED_BY_UNDO.value]


def test_second_undo_is_a_no_op_with_an_already_cancelled_reply(db_path: Path) -> None:
    service = _build(db_path)
    (booking,) = service.evaluate_utterance(BOOK_KUMARAN)
    (first,) = service.evaluate_utterance(UNDO)
    rows_after_first = len(_rows(db_path))

    (second,) = service.evaluate_utterance(UNDO)
    assert second.status == LedgerEventStatus.VOIDED_BY_UNDO
    assert second.tts_response_tamil == UNDO_ALREADY_CANCELLED_TAMIL
    assert second.event_id == first.event_id, "points at the existing void, not a new row"
    assert second.previous_balance_inr == second.projected_balance_inr == 42_000
    assert second.trade_value_inr == 0
    assert len(_rows(db_path)) == rows_after_first, "no ledger row written"
    assert [r["voids_event_id"] for r in _void_rows(db_path)] == [booking.event_id]


def test_undo_twice_leaves_the_earlier_booking_and_its_upi_link(db_path: Path) -> None:
    service = _build(db_path)
    (booking_a,) = service.evaluate_utterance(BOOK_SENTHIL)
    (booking_b,) = service.evaluate_utterance(BOOK_KUMARAN)
    service.evaluate_utterance(UNDO)
    service.evaluate_utterance(UNDO)

    assert [r["voids_event_id"] for r in _void_rows(db_path)] == [booking_b.event_id]
    assert service.repository.get_buyer_row(SENTHIL)["running_balance_inr"] == 136_000
    assert service.repository.get_buyer_row(KUMARAN)["running_balance_inr"] == 42_000

    events = {e["event_id"]: e for e in service.repository.fetch_dashboard_snapshot()["events"]}
    assert events[booking_a.event_id]["upi_link_visible"] is True
    assert events[booking_b.event_id]["upi_link_visible"] is False, "voided row keeps F1 behaviour"
    assert not any(events[r["event_id"]]["upi_link_visible"] for r in _void_rows(db_path))


def test_undo_on_an_empty_ledger_writes_nothing(db_path: Path) -> None:
    service = _build(db_path)
    decisions: Sequence[CreditGateDecision] = service.evaluate_utterance(UNDO)
    assert all(d.status != LedgerEventStatus.VOIDED_BY_UNDO for d in decisions)
    assert _rows(db_path) == []


def test_concurrent_undos_on_separate_connections_void_once(db_path: Path) -> None:
    service = _build(db_path)
    (booking,) = service.evaluate_utterance(BOOK_KUMARAN)
    repos = [
        AppendOnlyLedgerRepository(str(db_path), list(service.matcher.buyers.values()))
        for _ in range(2)
    ]
    barrier = threading.Barrier(len(repos))
    results: List[Optional[Dict[str, Any]]] = [None] * len(repos)

    def _undo(index: int) -> None:
        barrier.wait()
        results[index] = repos[index].undo_last_booked_trade(UNDO)

    threads = [threading.Thread(target=_undo, args=(i,)) for i in range(len(repos))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(bool(r and r["already_voided"]) for r in results) == [False, True]
    assert [r["voids_event_id"] for r in _void_rows(db_path)] == [booking.event_id]
    _assert_balance_invariant(service, db_path)
