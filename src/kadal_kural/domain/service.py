"""Deterministic Pre-Dispatch Credit Firewall & Confidence Gate application service."""

from __future__ import annotations

from typing import FrozenSet, List, Optional
import urllib.parse

from kadal_kural.config import SPAN_DECIDE, SPAN_MATCH, SPAN_NORMALIZE, SPAN_UNDO, AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import (
    CreditGateDecision,
    HeldTradeContext,
    LedgerEventStatus,
    TradeIntent,
)
from kadal_kural.domain.normalizer import format_inr_for_timbre_prosody
from kadal_kural.domain.telemetry import (
    NullSpanRecorder,
    SpanRecorderFactory,
    UtteranceEvaluation,
    recorded_span,
)
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

UNDO_COMMAND_TRIGGERS: FrozenSet[str] = frozenset({
    "கேன்சல்", "ரத்து", "cancel", "undo", "வேண்டாம்", "வேணாம்",
})


class PreDispatchCreditFirewallService:
    """
    Coordinates deterministic trade extraction, confidence gating, credit-limit checks,
    voice undo compensating transactions, and barge-in quantity overrides.
    Arithmetic is never delegated to an LLM.

    Pipeline timing is injected: ``span_recorder_factory`` builds one SpanRecorder per
    utterance (no-op by default), and evaluate_utterance_timed returns its PipelineTelemetry
    next to the decisions.
    """

    def __init__(
        self,
        settings: AppSettings,
        matcher: BilingualCatalogMatcher,
        repository: AppendOnlyLedgerRepository,
        span_recorder_factory: SpanRecorderFactory = NullSpanRecorder,
    ) -> None:
        self._settings = settings
        self.matcher = matcher
        self.repository = repository
        self.held_context: Optional[HeldTradeContext] = None
        self._span_recorder_factory = span_recorder_factory

    def _generate_upi_uri(self, buyer_name: str, amount_inr: int) -> str:
        query = urllib.parse.urlencode(
            {
                "pa": self._settings.merchant_upi_vpa,
                "pn": self._settings.merchant_name,
                "am": f"{amount_inr:.2f}",
                "cu": "INR",
                "tn": f"Dispatch-{buyer_name}",
            }
        )
        return f"upi://pay?{query}"

    def evaluate_utterance(
        self, raw_utterance: str, stt_latency_ms: float = 0.0
    ) -> List[CreditGateDecision]:
        """The decisions for one utterance; evaluate_utterance_timed also returns timings."""
        return list(self.evaluate_utterance_timed(raw_utterance, stt_latency_ms).decisions)

    def evaluate_utterance_timed(
        self, raw_utterance: str, stt_latency_ms: float = 0.0
    ) -> UtteranceEvaluation:
        """Evaluates one utterance, timing normalize, match and decide (incl. the SQLite write)."""
        spans = self._span_recorder_factory()
        tokens = set(raw_utterance.lower().split())
        has_digits = any(char.isdigit() for char in raw_utterance)

        # Check for pure Voice Undo command ('கடைசி ஆர்டர் கேன்சல்' / 'last trade cancel')
        if not has_digits and (tokens & UNDO_COMMAND_TRIGGERS):
            with recorded_span(spans, SPAN_UNDO):
                undo_info = self.repository.undo_last_booked_trade(raw_utterance)
            if undo_info is not None:
                tts_msg = (
                    f"கடைசி ஆர்டர் ரத்து செய்யப்பட்டது. {undo_info['tamil_speak_name']} "
                    f"புதிய பாக்கி {format_inr_for_timbre_prosody(undo_info['restored_balance_inr'])}."
                )
                undo_decision = CreditGateDecision(
                    event_id=undo_info["event_id"],
                    status=LedgerEventStatus.VOIDED_BY_UNDO,
                    buyer_id=undo_info["buyer_id"],
                    buyer_name=undo_info["buyer_name"],
                    sku_name=undo_info["sku_name"],
                    quantity=undo_info["quantity"],
                    unit=undo_info["unit"],
                    rate_inr=undo_info["rate_inr"],
                    trade_value_inr=undo_info["reversed_value_inr"],
                    previous_balance_inr=undo_info["previous_balance_inr"],
                    projected_balance_inr=undo_info["restored_balance_inr"],
                    credit_limit_inr=undo_info["credit_limit_inr"],
                    excess_amount_inr=0,
                    confidence=1.0,
                    tts_response_tamil=tts_msg,
                    upi_payment_uri="",
                    stt_latency_ms=stt_latency_ms,
                )
                return UtteranceEvaluation(decisions=(undo_decision,), telemetry=spans.telemetry())

        with recorded_span(spans, SPAN_NORMALIZE):
            normalized = self.matcher.normalize(raw_utterance)
        with recorded_span(spans, SPAN_MATCH):
            intents = self.matcher.parse_normalized(
                normalized, raw_utterance, held_context=self.held_context
            )
        with recorded_span(spans, SPAN_DECIDE):
            decisions = tuple(
                self._evaluate_single_intent(intent, stt_latency_ms=stt_latency_ms) for intent in intents
            )
        return UtteranceEvaluation(decisions=decisions, telemetry=spans.telemetry())

    def _evaluate_single_intent(
        self, intent: TradeIntent, stt_latency_ms: float = 0.0
    ) -> CreditGateDecision:
        # 1. CONFIDENCE GATE: Block silent financial errors before touching the ledger
        if (
            intent.overall_confidence < self._settings.confidence_threshold
            or intent.buyer_id is None
            or intent.sku_id is None
            or intent.rate_inr is None
            or intent.quantity is None
        ):
            event_id = self.repository.append_event_and_update_balance(
                buyer_id=intent.buyer_id or "UNVERIFIED",
                buyer_name=intent.buyer_name,
                sku_name=intent.sku_name,
                quantity=intent.quantity or 0,
                unit=intent.unit,
                rate_inr=intent.rate_inr or 0,
                trade_value_inr=intent.total_value_inr,
                previous_balance_inr=0,
                projected_balance_inr=0,
                credit_limit_inr=0,
                status=LedgerEventStatus.PENDING_CLARIFICATION,
                confidence=intent.overall_confidence,
                raw_utterance=intent.raw_utterance,
                normalized_clause=intent.normalized_clause,
                upi_payment_uri="",
                commit_balance=False,
            )
            tts_msg = "பெயர் அல்லது விலை தெளிவாக இல்லை. தயவுசெய்து மீண்டும் சொல்லுங்கள்."
            return CreditGateDecision(
                event_id=event_id,
                status=LedgerEventStatus.PENDING_CLARIFICATION,
                buyer_id=intent.buyer_id or "UNVERIFIED",
                buyer_name=intent.buyer_name,
                sku_name=intent.sku_name,
                quantity=intent.quantity or 0,
                unit=intent.unit,
                rate_inr=intent.rate_inr or 0,
                trade_value_inr=intent.total_value_inr,
                previous_balance_inr=0,
                projected_balance_inr=0,
                credit_limit_inr=0,
                excess_amount_inr=0,
                confidence=intent.overall_confidence,
                tts_response_tamil=tts_msg,
                upi_payment_uri="",
                stt_latency_ms=stt_latency_ms,
            )

        # 2. DETERMINISTIC BALANCE & LIMIT VERIFICATION
        buyer_row = self.repository.get_buyer_row(intent.buyer_id)
        prev_balance = int(buyer_row["running_balance_inr"])
        credit_limit = int(buyer_row["credit_limit_inr"])
        tamil_buyer = str(buyer_row["tamil_speak_name"])
        projected_balance = prev_balance + intent.total_value_inr
        upi_uri = self._generate_upi_uri(intent.buyer_name, intent.total_value_inr)

        # 3. PRE-DISPATCH CREDIT BREACH GATE
        if projected_balance > credit_limit:
            excess_inr = projected_balance - credit_limit
            event_id = self.repository.append_event_and_update_balance(
                buyer_id=intent.buyer_id,
                buyer_name=intent.buyer_name,
                sku_name=intent.sku_name,
                quantity=intent.quantity,
                unit=intent.unit,
                rate_inr=intent.rate_inr,
                trade_value_inr=intent.total_value_inr,
                previous_balance_inr=prev_balance,
                projected_balance_inr=projected_balance,
                credit_limit_inr=credit_limit,
                status=LedgerEventStatus.CREDIT_HOLD_BREACH,
                confidence=intent.overall_confidence,
                raw_utterance=intent.raw_utterance,
                normalized_clause=intent.normalized_clause,
                upi_payment_uri=upi_uri,
                commit_balance=False,
            )
            self.held_context = HeldTradeContext(
                buyer_id=intent.buyer_id,
                sku_id=intent.sku_id,
                rate_inr=intent.rate_inr,
                blocked_event_id=event_id,
            )
            tts_msg = (
                f"அலர்ட்! {tamil_buyer} பழைய பாக்கி {format_inr_for_timbre_prosody(prev_balance)}. "
                f"இந்த {format_inr_for_timbre_prosody(intent.total_value_inr)} சேர்த்தால் "
                f"கிரெடிட் லிமிட் {format_inr_for_timbre_prosody(credit_limit)} தாண்டுகிறது. "
                f"சரக்கு நிறுத்தப்பட்டுள்ளது. அளவை குறைக்கவா அல்லது கேன்சல் செய்யவா?"
            )
            return CreditGateDecision(
                event_id=event_id,
                status=LedgerEventStatus.CREDIT_HOLD_BREACH,
                buyer_id=intent.buyer_id,
                buyer_name=intent.buyer_name,
                sku_name=intent.sku_name,
                quantity=intent.quantity,
                unit=intent.unit,
                rate_inr=intent.rate_inr,
                trade_value_inr=intent.total_value_inr,
                previous_balance_inr=prev_balance,
                projected_balance_inr=projected_balance,
                credit_limit_inr=credit_limit,
                excess_amount_inr=excess_inr,
                confidence=intent.overall_confidence,
                tts_response_tamil=tts_msg,
                upi_payment_uri=upi_uri,
                stt_latency_ms=stt_latency_ms,
            )

        # 4. APPROVED DISPATCH (WITHIN CREDIT LIMIT)
        status = (
            LedgerEventStatus.BOOKED_AFTER_BARGE_IN
            if intent.is_barge_in_override
            else LedgerEventStatus.BOOKED
        )
        event_id = self.repository.append_event_and_update_balance(
            buyer_id=intent.buyer_id,
            buyer_name=intent.buyer_name,
            sku_name=intent.sku_name,
            quantity=intent.quantity,
            unit=intent.unit,
            rate_inr=intent.rate_inr,
            trade_value_inr=intent.total_value_inr,
            previous_balance_inr=prev_balance,
            projected_balance_inr=projected_balance,
            credit_limit_inr=credit_limit,
            status=status,
            confidence=intent.overall_confidence,
            raw_utterance=intent.raw_utterance,
            normalized_clause=intent.normalized_clause,
            upi_payment_uri=upi_uri,
            commit_balance=True,
        )
        if intent.is_barge_in_override:
            self.held_context = None

        prefix = "அப்டேட் செய்யப்பட்டது. " if intent.is_barge_in_override else ""
        tts_msg = (
            f"{prefix}{tamil_buyer}, {intent.quantity} {intent.unit} {intent.sku_name}, "
            f"{format_inr_for_timbre_prosody(intent.total_value_inr)} கணக்கில் ஏற்றப்பட்டது."
        )
        return CreditGateDecision(
            event_id=event_id,
            status=status,
            buyer_id=intent.buyer_id,
            buyer_name=intent.buyer_name,
            sku_name=intent.sku_name,
            quantity=intent.quantity,
            unit=intent.unit,
            rate_inr=intent.rate_inr,
            trade_value_inr=intent.total_value_inr,
            previous_balance_inr=prev_balance,
            projected_balance_inr=projected_balance,
            credit_limit_inr=credit_limit,
            excess_amount_inr=0,
            confidence=intent.overall_confidence,
            tts_response_tamil=tts_msg,
            upi_payment_uri=upi_uri,
            stt_latency_ms=stt_latency_ms,
        )
