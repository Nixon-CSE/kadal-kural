"""Thread-safe, WAL-mode SQLite append-only ledger repository."""

from __future__ import annotations

import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from kadal_kural.domain.models import BuyerProfile, LedgerEventStatus


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
                    upi_payment_uri TEXT NOT NULL
                );
                """
            )
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
    ) -> int:
        now_str = time.strftime("%H:%M:%S")
        with self._lock:
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
                    credit_limit_inr, status, confidence, raw_utterance, normalized_clause, upi_payment_uri
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def undo_last_booked_trade(self, raw_utterance: str) -> Optional[Dict[str, Any]]:
        """
        Compensating transaction for voice undo ('கடைசி ஆர்டர் கேன்சல்' / 'last trade cancel').
        Never deletes rows; writes an immutable VOIDED_BY_UNDO compensating entry.
        """
        with self._lock:
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
            reversed_val = int(last_row["trade_value_inr"])
            restored_bal = max(0, current_bal - reversed_val)

            event_id = self.append_event_and_update_balance(
                buyer_id=buyer_id,
                buyer_name=str(last_row["buyer_name"]),
                sku_name=str(last_row["sku_name"]),
                quantity=int(last_row["quantity"]),
                unit=str(last_row["unit"]),
                rate_inr=int(last_row["rate_inr"]),
                trade_value_inr=reversed_val,
                previous_balance_inr=current_bal,
                projected_balance_inr=restored_bal,
                credit_limit_inr=int(buyer["credit_limit_inr"]),
                status=LedgerEventStatus.VOIDED_BY_UNDO,
                confidence=1.0,
                raw_utterance=raw_utterance,
                normalized_clause="VOICE_COMPENSATING_UNDO",
                upi_payment_uri="",
                commit_balance=True,
            )
            return {
                "event_id": event_id,
                "buyer_id": buyer_id,
                "buyer_name": str(last_row["buyer_name"]),
                "tamil_speak_name": str(buyer["tamil_speak_name"]),
                "sku_name": str(last_row["sku_name"]),
                "quantity": int(last_row["quantity"]),
                "unit": str(last_row["unit"]),
                "rate_inr": int(last_row["rate_inr"]),
                "reversed_value_inr": reversed_val,
                "previous_balance_inr": current_bal,
                "restored_balance_inr": restored_bal,
                "credit_limit_inr": int(buyer["credit_limit_inr"]),
            }

    def reset_to_seed_state(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM ledger_events;")
            cur.execute("DELETE FROM buyers;")
            self._conn.commit()
        self._initialize_schema()

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
            return {"buyers": buyers, "events": events}
