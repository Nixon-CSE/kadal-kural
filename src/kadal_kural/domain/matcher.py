"""Bilingual fuzzy/phonetic entity resolution and deterministic multi-trade parser."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from rapidfuzz import fuzz, process

from kadal_kural.config import (
    AMOUNT_CONFIDENCE_FLOOR,
    AMOUNT_IN_RANGE_CONFIDENCE,
    AMOUNT_OUT_OF_RANGE_SLOPE,
    DEFAULT_ASSUMED_UNIT_CONFIDENCE,
    NO_SKU_FALLBACK_UNIT,
    UNPRICED_UNIT_RATE_CONFIDENCE,
)
from kadal_kural.domain.models import (
    BuyerProfile,
    HeldTradeContext,
    SKUProfile,
    TradeIntent,
    ValueRange,
)
from kadal_kural.domain.normalizer import (
    BARGE_IN_OVERRIDE_MARKERS,
    CANONICAL_UNIT_MAP,
    TRAILING_LEDGER_VERBS,
    normalize_hybrid_tamil_numerals,
    split_multi_trade_clauses,
    strip_numeral_decoration,
    strip_tamil_dative_suffix,
)


def range_confidence(value: int, band: ValueRange) -> float:
    """
    Scores a spoken amount against its sanity band: 1.0 inside [min, max] (inclusive),
    then falling linearly with the relative distance past the nearer bound, down to
    AMOUNT_CONFIDENCE_FLOOR. Non-positive values score the floor.
    """
    if band.min <= value <= band.max:
        return AMOUNT_IN_RANGE_CONFIDENCE
    if value <= 0:
        return AMOUNT_CONFIDENCE_FLOOR
    excess = value / band.max - 1.0 if value > band.max else band.min / value - 1.0
    score = AMOUNT_IN_RANGE_CONFIDENCE - AMOUNT_OUT_OF_RANGE_SLOPE * excess
    return round(max(AMOUNT_CONFIDENCE_FLOOR, score), 3)


class BilingualCatalogMatcher:
    """Matches Tamil and Latin script buyer and SKU phrases against a domain catalog."""

    def __init__(
        self,
        catalog_path: Union[str, Path],
        assumed_unit_confidence: float = DEFAULT_ASSUMED_UNIT_CONFIDENCE,
    ) -> None:
        self.assumed_unit_confidence = assumed_unit_confidence
        raw_data = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
        self.domain_id: str = raw_data["domain_id"]
        self.domain_title: str = raw_data["domain_title"]

        self.buyers: Dict[str, BuyerProfile] = {
            item["buyer_id"]: BuyerProfile(**item) for item in raw_data["buyers"]
        }
        self.skus: Dict[str, SKUProfile] = {
            item["sku_id"]: SKUProfile(**item) for item in raw_data["skus"]
        }
        self.unit_quantity_ranges: Dict[str, ValueRange] = {
            unit: ValueRange(**band) for unit, band in raw_data["unit_quantity_ranges"].items()
        }
        required_units = set(CANONICAL_UNIT_MAP.values()) | {s.default_unit for s in self.skus.values()}
        missing_units = required_units - set(self.unit_quantity_ranges)
        if missing_units:
            raise ValueError(f"catalog unit_quantity_ranges missing units: {sorted(missing_units)}")

        self._buyer_alias_index: Dict[str, str] = {}
        for buyer in self.buyers.values():
            for alias in buyer.aliases:
                self._buyer_alias_index[alias.lower().strip()] = buyer.buyer_id

        self._sku_alias_index: Dict[str, str] = {}
        for sku in self.skus.values():
            for alias in sku.aliases:
                self._sku_alias_index[alias.lower().strip()] = sku.sku_id

    def resolve_buyer(self, raw_phrase: str) -> Tuple[Optional[BuyerProfile], float]:
        """Resolves a buyer phrase (after dative suffix stripping) with confidence [0.0, 1.0]."""
        cleaned = strip_tamil_dative_suffix(raw_phrase).lower().strip()
        if not cleaned:
            return None, 0.0
        result = process.extractOne(
            cleaned,
            list(self._buyer_alias_index.keys()),
            scorer=fuzz.WRatio,
        )
        if result is None:
            return None, 0.0
        matched_alias, score, _ = result
        buyer = self.buyers[self._buyer_alias_index[matched_alias]]
        return buyer, round(float(score) / 100.0, 3)

    def resolve_sku(self, raw_phrase: str) -> Tuple[Optional[SKUProfile], float]:
        """Resolves a commodity/SKU phrase with confidence [0.0, 1.0]."""
        cleaned = raw_phrase.lower().strip()
        if not cleaned:
            return None, 0.0
        result = process.extractOne(
            cleaned,
            list(self._sku_alias_index.keys()),
            scorer=fuzz.WRatio,
        )
        if result is None:
            return None, 0.0
        matched_alias, score, _ = result
        sku = self.skus[self._sku_alias_index[matched_alias]]
        return sku, round(float(score) / 100.0, 3)

    def parse_utterance(
        self,
        raw_utterance: str,
        held_context: Optional[HeldTradeContext] = None,
    ) -> List[TradeIntent]:
        """
        Extracts 1..N structured TradeIntent objects from a single spoken utterance.
        Supports contextual barge-in quantity overrides (e.g., 'செந்திலுக்கு 25 பாக்ஸ் மட்டும் போடு').
        """
        normalized_full = normalize_hybrid_tamil_numerals(raw_utterance)
        clauses = split_multi_trade_clauses(normalized_full)
        intents: List[TradeIntent] = []

        for clause in clauses:
            tokens = clause.split()
            # normalize_hybrid_tamil_numerals already resolves Prisma's '₹'/comma-decorated
            # digit tokens, but strip_numeral_decoration is applied again here defensively
            # in case any decorated token slips through unresolved (e.g. a shape not yet
            # covered by that normalizer) rather than silently vanishing from numeric_positions.
            numeric_positions: List[Tuple[int, int]] = []
            for i, tok in enumerate(tokens):
                bare_digits = strip_numeral_decoration(tok)
                if bare_digits is not None:
                    numeric_positions.append((i, int(bare_digits)))
            if not numeric_positions:
                continue

            is_override = any(tok.lower() in BARGE_IN_OVERRIDE_MARKERS for tok in tokens)
            qty_token_idx, quantity = numeric_positions[0]
            rate_inr: Optional[int] = (
                numeric_positions[1][1]
                if len(numeric_positions) >= 2
                else (held_context.rate_inr if (held_context and is_override) else None)
            )

            # An unrecognised word after the quantity leaves unit unresolved; it falls back
            # to the matched SKU's default_unit below, at reduced unit confidence.
            heard_unit: Optional[str] = None
            unit_end_idx = qty_token_idx
            if qty_token_idx + 1 < len(tokens):
                candidate_unit = tokens[qty_token_idx + 1].lower()
                if candidate_unit in CANONICAL_UNIT_MAP:
                    heard_unit = CANONICAL_UNIT_MAP[candidate_unit]
                    unit_end_idx = qty_token_idx + 1

            buyer_phrase = " ".join(tokens[:qty_token_idx]).strip()
            buyer, buyer_conf = self.resolve_buyer(buyer_phrase)
            if buyer is None and held_context and is_override:
                buyer = self.buyers.get(held_context.buyer_id)
                buyer_conf = 0.92

            sku_end_idx = numeric_positions[1][0] if len(numeric_positions) >= 2 else len(tokens)
            sku_tokens = [
                t
                for t in tokens[unit_end_idx + 1 : sku_end_idx]
                if t.lower() not in BARGE_IN_OVERRIDE_MARKERS
                and t.lower() not in TRAILING_LEDGER_VERBS
            ]
            sku_phrase = " ".join(sku_tokens).strip()
            sku, sku_conf = self.resolve_sku(sku_phrase)
            sku_inherited = False
            if sku is None and held_context and is_override:
                sku = self.skus.get(held_context.sku_id)
                sku_conf = 0.92
                sku_inherited = sku is not None

            if heard_unit is not None:
                unit, unit_conf = heard_unit, 1.0
            elif sku is not None:
                unit = sku.default_unit
                # A barge-in override inherits the held trade's SKU, so its default unit is
                # carried context (same 0.92 as the inherited SKU), not a guess.
                unit_conf = sku_conf if sku_inherited else self.assumed_unit_confidence
            else:
                unit, unit_conf = NO_SKU_FALLBACK_UNIT, self.assumed_unit_confidence

            total_val = (quantity or 0) * (rate_inr or 0)
            qty_conf = range_confidence(quantity, self.unit_quantity_ranges[unit])
            if rate_inr is None or rate_inr <= 0:
                rate_conf = 0.0
            elif sku is None:
                rate_conf = 1.0  # no SKU, no band to check against; sku_conf already gates it
            elif unit not in sku.rate_range_inr:
                rate_conf = UNPRICED_UNIT_RATE_CONFIDENCE  # e.g. Vanjaram quoted per box
            else:
                rate_conf = range_confidence(rate_inr, sku.rate_range_inr[unit])
            overall_conf = round(min(buyer_conf, sku_conf, unit_conf, qty_conf, rate_conf), 3)

            intents.append(
                TradeIntent(
                    raw_utterance=raw_utterance,
                    normalized_clause=clause,
                    buyer_id=buyer.buyer_id if buyer else None,
                    buyer_name=buyer.canonical_name if buyer else (buyer_phrase or "Unknown Buyer"),
                    buyer_confidence=buyer_conf,
                    sku_id=sku.sku_id if sku else None,
                    sku_name=sku.canonical_name if sku else (sku_phrase or "Unknown Item"),
                    sku_confidence=sku_conf,
                    quantity=quantity,
                    unit=unit,
                    rate_inr=rate_inr,
                    total_value_inr=total_val,
                    overall_confidence=overall_conf,
                    is_barge_in_override=is_override,
                )
            )

        return intents