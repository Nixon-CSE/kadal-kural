"""Thread-safe, WAL-mode SQLite append-only ledger repository."""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kadal_kural.domain.models import (
    UNKNOWN_SOURCE,
    BuyerProfile,
    EntrySource,
    LedgerEventStatus,
    OrderChannel,
)

# Only a committed trade is payable; holds, clarifications and undo rows never get a UPI link.
_UPI_PAYABLE_STATUSES = frozenset(
    {LedgerEventStatus.BOOKED.value, LedgerEventStatus.BOOKED_AFTER_BARGE_IN.value}
)

# Nullable ledger_events columns added after the first schema, with their SQLite types.
_ADDED_LEDGER_COLUMNS: Dict[str, str] = {
    "voids_event_id": "INTEGER",
    "buyer_guess": "TEXT",
    "buyer_guess_confidence": "REAL",
    "sku_guess": "TEXT",
    "sku_guess_confidence": "REAL",
    "channel": "TEXT",  # OrderChannel value; NULL on entries written before channels were recorded
    "call_id": "TEXT",  # the phone call an entry belongs to, when the agent sent an id
    "recorded_at": "TEXT",  # ISO 8601 UTC; created_at keeps only the time of day
}

class AppendOnlyLedgerRepository:
    """
    Guarantees zero destructive updates to historical ledger events.
    Every credit hold, clarification, undo, or barge-in override writes an immutable audit row.
    """

    def __init__(self, db_path: str, seed_buyers: List[BuyerProfile]) -> None:
        self._db_path = db_path
        self._seed_buyers = seed_buyers
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.execute("PRAGMA foreign_keys=ON;")
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS buyers (
                    buyer_id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    tamil_speak_name TEXT NOT NULL,
                    credit_limit_inr INTEGER NOT NULL,
                    running_balance_inr INTEGER NOT NULL,
                    phone_e164 TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ledger_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    buyer_id TEXT NOT NULL,
                    buyer_name TEXT NOT NULL,
                    sku_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit TEXT NOT NULL,
                    rate_inr INTEGER NOT NULL,
                    trade_value_inr INTEGER NOT NULL,
                    previous_balance_inr INTEGER NOT NULL,
                    projected_balance_inr INTEGER NOT NULL,
                    credit_limit_inr INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    raw_utterance TEXT NOT NULL,
                    normalized_clause TEXT NOT NULL,
                    upi_payment_uri TEXT NOT NULL,
                    voids_event_id INTEGER,
                    buyer_guess TEXT,
                    buyer_guess_confidence REAL,
                    sku_guess TEXT,
                    sku_guess_confidence REAL,
                    channel TEXT,
                    call_id TEXT,
                    recorded_at TEXT
                );
                """
            )
            columns = {str(r["name"]) for r in cur.execute("PRAGMA table_info(ledger_events)")}
            for name, sql_type in _ADDED_LEDGER_COLUMNS.items():  # ledgers created before they existed
                if name not in columns:
                    cur.execute(f"ALTER TABLE ledger_events ADD COLUMN {name} {sql_type}")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ledger_events_channel ON ledger_events (channel, event_id)")
            for buyer in self._seed_buyers:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO buyers
                    (buyer_id, canonical_name, tamil_speak_name, credit_limit_inr, running_balance_inr, phone_e164)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        buyer.buyer_id,
                        buyer.canonical_name,
                        buyer.tamil_speak_name,
                        buyer.credit_limit_inr,
                        buyer.opening_balance_inr,
                        buyer.phone_e164,
                    ),
                )
            self._conn.commit()

    def get_buyer_row(self, buyer_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM buyers WHERE buyer_id = ?", (buyer_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Buyer {buyer_id} not found in database")
            return dict(row)

    def append_event_and_update_balance(
        self,
        *,
        buyer_id: str,
        buyer_name: str,
        sku_name: str,
        quantity: int,
        unit: str,
        rate_inr: int,
        trade_value_inr: int,
        previous_balance_inr: int,
        projected_balance_inr: int,
        credit_limit_inr: int,
        status: LedgerEventStatus,
        confidence: float,
        raw_utterance: str,
        normalized_clause: str,
        upi_payment_uri: str,
        commit_balance: bool,
        voids_event_id: Optional[int] = None,
        buyer_guess: Optional[str] = None,
        buyer_guess_confidence: Optional[float] = None,
        sku_guess: Optional[str] = None,
        sku_guess_confidence: Optional[float] = None,
        source: EntrySource = UNKNOWN_SOURCE,
    ) -> int:
        now_str = time.strftime("%H:%M:%S")
        recorded_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        channel = source.channel.value if source.channel is not None else None
        with self._lock:
            owns_transaction = not self._conn.in_transaction  # else a caller's transaction commits
            cur = self._conn.cursor()
            if commit_balance:
                cur.execute(
                    "UPDATE buyers SET running_balance_inr = ? WHERE buyer_id = ?",
                    (projected_balance_inr, buyer_id),
                )
            cur.execute(
                """
                INSERT INTO ledger_events (
                    created_at, buyer_id, buyer_name, sku_name, quantity, unit,
                    rate_inr, trade_value_inr, previous_balance_inr, projected_balance_inr,
                    credit_limit_inr, status, confidence, raw_utterance, normalized_clause, upi_payment_uri,
                    voids_event_id, buyer_guess, buyer_guess_confidence, sku_guess, sku_guess_confidence,
                    channel, call_id, recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_str,
                    buyer_id,
                    buyer_name,
                    sku_name,
                    quantity,
                    unit,
                    rate_inr,
                    trade_value_inr,
                    previous_balance_inr,
                    projected_balance_inr,
                    credit_limit_inr,
                    status.value,
                    confidence,
                    raw_utterance,
                    normalized_clause,
                    upi_payment_uri,
                    voids_event_id,
                    buyer_guess,
                    buyer_guess_confidence,
                    sku_guess,
                    sku_guess_confidence,
                    channel,
                    source.call_id,
                    recorded_at,
                ),
            )
            if owns_transaction:
                self._conn.commit()
            return int(cur.lastrowid or 0)

    def undo_last_booked_trade(
        self, raw_utterance: str, source: EntrySource = UNKNOWN_SOURCE
    ) -> Optional[Dict[str, Any]]:
        """
        Compensating transaction for voice undo ('கடைசி ஆர்டர் கேன்சல்' / 'last trade cancel').
        Never deletes rows; writes an immutable VOIDED_BY_UNDO compensating entry.

        Applies only to the most recent booking. If an earlier undo already voided it, nothing
        is written and the result has ``already_voided`` True, the existing void row's
        event_id and the unchanged balance. None when the ledger holds no booking.

        The read, the already-voided check and the void row share one BEGIN IMMEDIATE
        transaction: it takes SQLite's write lock up front, so a concurrent undo, even on
        another connection, waits and then sees the void instead of voiding the trade again.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                result = self._undo_last_booking(raw_utterance, source)
            except BaseException:
                self._conn.rollback()
                raise
            self._conn.commit()
            return result

    def _undo_last_booking(self, raw_utterance: str, source: EntrySource) -> Optional[Dict[str, Any]]:
        """undo_last_booked_trade's body; runs inside its transaction."""
        cur = self._conn.cursor()
        last_row = cur.execute(
            """
            SELECT * FROM ledger_events
            WHERE status IN (?, ?)
            ORDER BY event_id DESC LIMIT 1
            """,
            (LedgerEventStatus.BOOKED.value, LedgerEventStatus.BOOKED_AFTER_BARGE_IN.value),
        ).fetchone()
        if last_row is None:
            return None

        buyer_id = str(last_row["buyer_id"])
        buyer = self.get_buyer_row(buyer_id)
        current_bal = int(buyer["running_balance_inr"])
        booking_info: Dict[str, Any] = {
            "buyer_id": buyer_id,
            "buyer_name": str(last_row["buyer_name"]),
            "tamil_speak_name": str(buyer["tamil_speak_name"]),
            "sku_name": str(last_row["sku_name"]),
            "quantity": int(last_row["quantity"]),
            "unit": str(last_row["unit"]),
            "rate_inr": int(last_row["rate_inr"]),
            "previous_balance_inr": current_bal,
            "credit_limit_inr": int(buyer["credit_limit_inr"]),
        }

        existing_void = cur.execute(
            "SELECT event_id FROM ledger_events WHERE voids_event_id = ? LIMIT 1",
            (int(last_row["event_id"]),),
        ).fetchone()
        if existing_void is not None:
            return {
                **booking_info,
                "event_id": int(existing_void["event_id"]),
                "already_voided": True,
                "reversed_value_inr": 0,
                "restored_balance_inr": current_bal,
            }

        reversed_val = int(last_row["trade_value_inr"])
        restored_bal = max(0, current_bal - reversed_val)
        event_id = self.append_event_and_update_balance(
            buyer_id=buyer_id,
            buyer_name=booking_info["buyer_name"],
            sku_name=booking_info["sku_name"],
            quantity=booking_info["quantity"],
            unit=booking_info["unit"],
            rate_inr=booking_info["rate_inr"],
            trade_value_inr=reversed_val,
            previous_balance_inr=current_bal,
            projected_balance_inr=restored_bal,
            credit_limit_inr=booking_info["credit_limit_inr"],
            status=LedgerEventStatus.VOIDED_BY_UNDO,
            confidence=1.0,
            raw_utterance=raw_utterance,
            normalized_clause="VOICE_COMPENSATING_UNDO",
            upi_payment_uri="",
            commit_balance=True,
            voids_event_id=int(last_row["event_id"]),
            source=source,
        )
        return {
            **booking_info,
            "event_id": event_id,
            "already_voided": False,
            "reversed_value_inr": reversed_val,
            "restored_balance_inr": restored_bal,
        }

    def reset_to_seed_state(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM ledger_events;")
            cur.execute("DELETE FROM buyers;")
            self._conn.commit()
        self._initialize_schema()

    def _voided_event_ids(self) -> set[int]:
        return {
            int(r["voids_event_id"])
            for r in self._conn.execute(
                "SELECT voids_event_id FROM ledger_events WHERE voids_event_id IS NOT NULL"
            ).fetchall()
        }

    def fetch_channel_events(self, channel: OrderChannel, limit: int = 500) -> List[Dict[str, Any]]:
        """The newest ``limit`` entries from one channel, oldest first, each with a ``voided`` flag."""
        with self._lock:
            rows = [
                dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM ledger_events WHERE channel = ? ORDER BY event_id DESC LIMIT ?",
                    (channel.value, limit),
                ).fetchall()
            ]
            voided_ids = self._voided_event_ids()
        for row in rows:
            row["voided"] = int(row["event_id"]) in voided_ids
        rows.reverse()
        return rows

    def fetch_dashboard_snapshot(self) -> Dict[str, List[Dict[str, Any]]]:
        with self._lock:
            buyers = [
                dict(r)
                for r in self._conn.execute("SELECT * FROM buyers ORDER BY buyer_id").fetchall()
            ]
            events = [
                dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM ledger_events ORDER BY event_id DESC LIMIT 30"
                ).fetchall()
            ]
            voided_ids = self._voided_event_ids()
        for event in events:
            event["upi_link_visible"] = (
                event["status"] in _UPI_PAYABLE_STATUSES
                and bool(event["upi_payment_uri"])
                and int(event["event_id"]) not in voided_ids
            )
        return {"buyers": buyers, "events": events}
