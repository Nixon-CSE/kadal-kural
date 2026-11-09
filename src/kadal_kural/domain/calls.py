"""Groups phone-channel ledger entries into calls for the phone line's call log.

A Gnani Agent Builder agent forwards one caller sentence per request. When it sends a call or
conversation id, entries are grouped by that id. Otherwise entries are grouped by time: a gap of
more than ``gap_seconds`` between two entries starts a new call. Pure functions, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from kadal_kural.domain.models import LedgerEventStatus

DEFAULT_CALL_GAP_SECONDS = 300

_BOOKED = {LedgerEventStatus.BOOKED.value, LedgerEventStatus.BOOKED_AFTER_BARGE_IN.value}
_KIND = {
    LedgerEventStatus.BOOKED.value: "booked",
    LedgerEventStatus.BOOKED_AFTER_BARGE_IN.value: "booked",
    LedgerEventStatus.CREDIT_HOLD_BREACH.value: "held",
    LedgerEventStatus.PENDING_CLARIFICATION.value: "asked_again",
    LedgerEventStatus.VOIDED_BY_UNDO.value: "undone",
}
_TURN_FIELDS = (
    "event_id", "recorded_at", "created_at", "raw_utterance", "status", "buyer_id", "buyer_name",
    "sku_name", "quantity", "unit", "rate_inr", "trade_value_inr", "voided",
)


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


@dataclass
class PhoneCall:
    """One call: its entries in order, and what they added up to."""

    key: str
    call_id: Optional[str]
    turns: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        counts = {"booked": 0, "held": 0, "asked_again": 0, "undone": 0}
        for turn in self.turns:
            counts[_KIND.get(str(turn["status"]), "asked_again")] += 1
        booked_value = sum(
            int(t["trade_value_inr"]) for t in self.turns if t["status"] in _BOOKED and not t.get("voided")
        )
        return {
            "key": self.key,
            "call_id": self.call_id,
            "started_at": self.turns[0].get("recorded_at"),
            "ended_at": self.turns[-1].get("recorded_at"),
            "turns": [{k: t.get(k) for k in _TURN_FIELDS} for t in self.turns],
            "counts": counts,
            "booked_value_inr": booked_value,
        }


def group_phone_calls(
    entries: Sequence[Mapping[str, Any]], gap_seconds: int = DEFAULT_CALL_GAP_SECONDS
) -> List[PhoneCall]:
    """
    ``entries`` are phone-channel ledger rows, oldest first. Returns calls, most recent first.
    An entry without a parsable ``recorded_at`` and without a call id becomes a call of its own.
    """
    by_id: Dict[str, PhoneCall] = {}
    calls: List[PhoneCall] = []
    open_call: Optional[PhoneCall] = None
    open_until: Optional[datetime] = None
    for row in entries:
        entry = dict(row)
        call_id = entry.get("call_id") or None
        if call_id:
            call = by_id.get(call_id)
            if call is None:
                call = by_id[call_id] = PhoneCall(key=f"id:{call_id}", call_id=call_id)
                calls.append(call)
            call.turns.append(entry)
            continue
        at = _parse_time(entry.get("recorded_at"))
        if open_call is None or at is None or open_until is None or (at - open_until).total_seconds() > gap_seconds:
            open_call = PhoneCall(key=f"t:{entry['event_id']}", call_id=None)
            calls.append(open_call)
        open_call.turns.append(entry)
        open_until = at
    calls.sort(key=lambda c: int(c.turns[-1]["event_id"]), reverse=True)
    return calls
