"""Strict, immutable domain entities and value objects for the Kadal Kural engine."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class LedgerEventStatus(str, Enum):
    """Deterministic outcomes produced by the Pre-Dispatch Credit Firewall."""

    BOOKED = "BOOKED"
    BOOKED_AFTER_BARGE_IN = "BOOKED_AFTER_BARGE_IN"
    CREDIT_HOLD_BREACH = "CREDIT_HOLD_BREACH"
    PENDING_CLARIFICATION = "PENDING_CLARIFICATION"
    VOIDED_BY_UNDO = "VOIDED_BY_UNDO"


class BuyerProfile(BaseModel):
    """Registered B2B wholesale buyer entity."""

    model_config = ConfigDict(frozen=True)

    buyer_id: str
    canonical_name: str
    tamil_speak_name: str
    credit_limit_inr: int = Field(ge=0)
    opening_balance_inr: int = Field(ge=0)
    phone_e164: str
    aliases: List[str]


class ValueRange(BaseModel):
    """
    Inclusive [min, max] sanity band for a spoken amount (catalog.json rate_range_inr per
    SKU and unit_quantity_ranges per unit).

    The catalog bands were set from how Kasimedu wholesale trade works, decided before
    looking at any benchmark results, and are deliberately wide: they exist to catch gross
    misparses (a dropped hundreds word, a misheard quantity), not to police prices.
      - Export Vanjaram ₹400–1,600 per kg (catalog default_unit 'kg'). Kasimedu quotes seer
        fish per kg, never per box: DT Next reported Rs 950/kg on 26 Oct 2026 ("Kasimedu fish
        prices rise amid low supply; seer fish sells at Rs 950 per kg"), Rs 1,200–1,400/kg the
        Sunday after the 2026 fishing ban, down from Rs 2,300/kg the week before ("Chennai: Fish
        prices dip by Rs 100–Rs 300 as supply returns to normal", 28 Jun 2026), and whole fish
        bought by weight at roughly Rs 500–600/kg ("Fisheye view of Kasimedu", 2016). A
        ban-end spike above ₹1,600 is deliberately left to score below the gate and be held.
      - Tiger Prawn ₹300–1,500/kg: the same 26 Oct 2026 DT Next price list gives rock/tiger
        prawns at Rs 1,200/kg; smaller counts sell lower.
      - Quantity per trade: kg 1–1,000 (a tonne is an exporter-sized lot); box 1–200, set
        1–100 and pcs 1–500 are unsourced generous caps for the mandi's non-fish lines.
    """

    model_config = ConfigDict(frozen=True)

    min: int = Field(gt=0)
    max: int = Field(gt=0)

    @model_validator(mode="after")
    def _check_bounds_ordered(self) -> "ValueRange":
        if self.min > self.max:
            raise ValueError(f"range min {self.min} exceeds max {self.max}")
        return self


class SKUProfile(BaseModel):
    """Registered B2B wholesale commodity or spare-part SKU."""

    model_config = ConfigDict(frozen=True)

    sku_id: str
    canonical_name: str
    tamil_speak_name: str
    default_unit: str
    rate_range_inr: ValueRange
    aliases: List[str]


class TradeIntent(BaseModel):
    """Structured trade tuple extracted from normalized Tamil/Tanglish speech."""

    model_config = ConfigDict(frozen=True)

    raw_utterance: str
    normalized_clause: str
    buyer_id: Optional[str] = None
    buyer_name: str
    buyer_confidence: float = Field(ge=0.0, le=1.0)
    sku_id: Optional[str] = None
    sku_name: str
    sku_confidence: float = Field(ge=0.0, le=1.0)
    quantity: Optional[int] = None
    unit: str
    rate_inr: Optional[int] = None
    total_value_inr: int = Field(ge=0)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    is_barge_in_override: bool = False


class HeldTradeContext(BaseModel):
    """Short-lived state of a blocked trade awaiting barge-in quantity modification."""

    model_config = ConfigDict(frozen=True)

    buyer_id: str
    sku_id: str
    rate_inr: int
    blocked_event_id: int


class CreditGateDecision(BaseModel):
    """Result returned by the Credit Firewall for a single TradeIntent."""

    model_config = ConfigDict(frozen=True)

    event_id: int
    status: LedgerEventStatus
    buyer_id: str
    buyer_name: str
    sku_name: str
    quantity: int
    unit: str
    rate_inr: int
    trade_value_inr: int
    previous_balance_inr: int
    projected_balance_inr: int
    credit_limit_inr: int
    excess_amount_inr: int
    confidence: float
    tts_response_tamil: str
    upi_payment_uri: str
    stt_latency_ms: float = 0.0
    timbre_ttfb_ms: float = 0.0
