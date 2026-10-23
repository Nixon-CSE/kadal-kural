"""Strict, immutable domain entities and value objects for the Kadal Kural engine."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


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


class SKUProfile(BaseModel):
    """Registered B2B wholesale commodity or spare-part SKU."""

    model_config = ConfigDict(frozen=True)

    sku_id: str
    canonical_name: str
    tamil_speak_name: str
    default_unit: str
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
