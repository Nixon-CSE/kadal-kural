"""
Pure scoring logic for the Noise & Silent-Error Benchmark (no network, no audio).

Definitions used everywhere in the report:

* **WER** — ``jiwer`` word error rate of the Prisma transcript against the clean spoken text,
  reported twice: ``raw`` (as Prisma wrote it) and ``normalized`` (both sides passed through
  ``normalize_hybrid_tamil_numerals`` first). The corpus spells numbers out as words while
  Prisma's ITN emits digits, so ``raw`` WER is inflated by formatting alone; ``normalized``
  is the fairer acoustic signal.
* **Per-entity accuracy** — for each ground-truth trade, is the matcher-extracted buyer / SKU /
  quantity / unit / rate correct? Extracted intents are assigned to ground-truth trades by
  best field overlap (greedy), so a dropped clause does not shift every later comparison.
* **Silent financial error** — a ``BOOKED`` / ``BOOKED_AFTER_BARGE_IN`` decision that does not
  correspond to any not-yet-matched ground-truth trade (buyer, SKU, quantity, unit and rate
  all equal). Each ground-truth trade can legitimise at most one booking, so a duplicated or
  hallucinated booking is an error. Missing trades are *omissions*, not silent errors.
* **Without the confidence gate** — the same firewall with ``confidence_threshold`` set to 0.
  The structural checks (a trade with no resolved buyer / SKU / rate / quantity can never be
  booked) stay on, because there is nothing to book without them.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import jiwer

from kadal_kural.config import AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import CreditGateDecision, LedgerEventStatus, TradeIntent
from kadal_kural.domain.normalizer import normalize_hybrid_tamil_numerals
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

from benchmark.corpus import BenchmarkUtterance, GroundTruthTrade

ENTITY_FIELDS: Tuple[str, ...] = ("buyer", "sku", "quantity", "unit", "rate")
BOOKED_STATUSES = frozenset({LedgerEventStatus.BOOKED, LedgerEventStatus.BOOKED_AFTER_BARGE_IN})
NO_GATE_THRESHOLD: float = 0.0
MS_PER_SECOND: float = 1000.0


@dataclass(frozen=True)
class GateOutcome:
    """What one firewall configuration did with one transcript."""

    booked: int
    silent_errors: int
    correct_bookings: int
    decision_ms: float


@dataclass(frozen=True)
class UtteranceScore:
    """All metrics for one (utterance, profile, SNR) transcript."""

    n_truth_trades: int
    n_parsed_trades: int
    entity_correct: Dict[str, int]
    wer_raw: float
    wer_normalized: float
    gated: GateOutcome
    ungated: GateOutcome


def word_error_rate(reference: str, hypothesis: str) -> float:
    """jiwer WER; an empty hypothesis is a total miss (1.0)."""
    if not hypothesis.strip():
        return 1.0
    return float(jiwer.wer(reference, hypothesis))


def _intent_matches_truth(intent: TradeIntent, truth: GroundTruthTrade, sku_name: Optional[str]) -> Dict[str, bool]:
    return {
        "buyer": intent.buyer_id == truth.buyer_id,
        "sku": sku_name == truth.sku_canonical_name,
        "quantity": intent.quantity == truth.quantity,
        "unit": intent.unit == truth.unit,
        "rate": intent.rate_inr == truth.rate_inr,
    }


def score_entities(
    intents: Sequence[TradeIntent],
    truths: Sequence[GroundTruthTrade],
    matcher: BilingualCatalogMatcher,
) -> Dict[str, int]:
    """
    Counts correct entities per field. Intents are paired with truth trades by repeatedly taking the
    globally best-overlapping unused (truth, intent) pair, so a dropped clause can't shift the rest.
    """
    sku_names = [matcher.skus[i.sku_id].canonical_name if i.sku_id else None for i in intents]
    hits = {
        (ti, ii): _intent_matches_truth(intent, truth, sku_names[ii])
        for ti, truth in enumerate(truths)
        for ii, intent in enumerate(intents)
    }
    correct = {name: 0 for name in ENTITY_FIELDS}
    free_truths, free_intents = set(range(len(truths))), set(range(len(intents)))
    while free_truths and free_intents:
        ti, ii = max(
            ((t, i) for t in sorted(free_truths) for i in sorted(free_intents)),
            key=lambda pair: sum(hits[pair].values()),
        )
        for name, ok in hits[(ti, ii)].items():
            correct[name] += int(ok)
        free_truths.remove(ti)
        free_intents.remove(ii)
    return correct


def classify_bookings(
    decisions: Sequence[CreditGateDecision], truths: Sequence[GroundTruthTrade]
) -> Tuple[int, int, int]:
    """Returns (booked, silent_errors, correct_bookings) for a decision list vs ground truth."""
    remaining = list(truths)
    booked = errors = correct = 0
    for decision in decisions:
        if decision.status not in BOOKED_STATUSES:
            continue
        booked += 1
        match = next(
            (
                t
                for t in remaining
                if decision.buyer_id == t.buyer_id
                and decision.sku_name == t.sku_canonical_name
                and decision.quantity == t.quantity
                and decision.unit == t.unit
                and decision.rate_inr == t.rate_inr
            ),
            None,
        )
        if match is None:
            errors += 1
        else:
            remaining.remove(match)
            correct += 1
    return booked, errors, correct


class FreshLedgerFirewall:
    """A firewall + SQLite ledger that is reset to catalog seed state before every utterance."""

    def __init__(self, settings: AppSettings, matcher: BilingualCatalogMatcher, db_path: Path) -> None:
        self.repo = AppendOnlyLedgerRepository(str(db_path), list(matcher.buyers.values()))
        self.service = PreDispatchCreditFirewallService(settings, matcher, self.repo)

    def evaluate(
        self, transcript: str, truths: Sequence[GroundTruthTrade], stt_latency_ms: float
    ) -> GateOutcome:
        """Resets the ledger, evaluates ``transcript`` and classifies every booking."""
        self.repo.reset_to_seed_state()
        self.service.held_context = None
        t0 = time.perf_counter()
        decisions = self.service.evaluate_utterance(transcript, stt_latency_ms=stt_latency_ms)
        decision_ms = (time.perf_counter() - t0) * MS_PER_SECOND
        booked, errors, correct = classify_bookings(decisions, truths)
        return GateOutcome(booked, errors, correct, round(decision_ms, 3))


class Scorer:
    """Scores transcripts with the gate on (production threshold) and off (threshold 0)."""

    def __init__(self, settings: AppSettings, workdir: Optional[Path] = None) -> None:
        self.settings = settings
        self.matcher = BilingualCatalogMatcher(settings.catalog_path)
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name) if workdir is None else workdir
        self.gated = FreshLedgerFirewall(settings, self.matcher, base / "gated.db")
        self.ungated = FreshLedgerFirewall(
            settings.model_copy(update={"confidence_threshold": NO_GATE_THRESHOLD}),
            self.matcher,
            base / "ungated.db",
        )

    def with_threshold(self, threshold: float) -> FreshLedgerFirewall:
        """A throwaway firewall at an arbitrary confidence threshold (for the sensitivity sweep)."""
        sub = Path(tempfile.mkdtemp(dir=self._tmp.name))
        return FreshLedgerFirewall(
            self.settings.model_copy(update={"confidence_threshold": threshold}),
            self.matcher,
            sub / "tau.db",
        )

    def score(
        self, utterance: BenchmarkUtterance, transcript: str, stt_latency_ms: float
    ) -> UtteranceScore:
        """Computes WER, entity accuracy and gated/ungated silent-error counts for one transcript."""
        truths = utterance.ground_truth_trades
        intents = self.matcher.parse_utterance(transcript) if transcript.strip() else []
        return UtteranceScore(
            n_truth_trades=len(truths),
            n_parsed_trades=len(intents),
            entity_correct=score_entities(intents, truths, self.matcher),
            wer_raw=word_error_rate(utterance.spoken_text, transcript),
            wer_normalized=word_error_rate(
                normalize_hybrid_tamil_numerals(utterance.spoken_text),
                normalize_hybrid_tamil_numerals(transcript),
            ),
            gated=self.gated.evaluate(transcript, truths, stt_latency_ms),
            ungated=self.ungated.evaluate(transcript, truths, stt_latency_ms),
        )
