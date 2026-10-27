"""
Clean-text (zero-noise) sanity gate for the benchmark corpus.

Before the corpus can be trusted as *ground truth* for the noise/silent-error benchmark,
every utterance must parse correctly through the real matcher on its own clean, unnoised
text. This caught two real corpus-authoring bugs during development (ground truth storing
the spoken Tamil unit word instead of the matcher's canonicalized unit, and a Tanglish
phrase with two clause-terminator tokens causing a spurious split) — this test exists so a
future corpus edit can't reintroduce either without the test suite catching it.
"""

from __future__ import annotations

from kadal_kural.config import AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher

from benchmark.corpus import build_corpus

_MIN_CORPUS_SIZE = 40
_MAX_CORPUS_SIZE = 60


def test_corpus_size_within_brief_range() -> None:
    corpus = build_corpus()
    assert _MIN_CORPUS_SIZE <= len(corpus) <= _MAX_CORPUS_SIZE, (
        f"corpus has {len(corpus)} utterances; brief calls for {_MIN_CORPUS_SIZE}-{_MAX_CORPUS_SIZE}"
    )


def test_corpus_utterance_ids_are_unique() -> None:
    corpus = build_corpus()
    ids = [u.utterance_id for u in corpus]
    assert len(ids) == len(set(ids))


def test_corpus_covers_both_single_and_multi_trade() -> None:
    categories = {u.category for u in build_corpus()}
    assert "multi_trade" in categories
    assert categories - {"multi_trade"}, "corpus has no single-trade categories"


def test_corpus_ground_truth_matches_clean_text_parse() -> None:
    """
    Every utterance's ground truth must be exactly what the real matcher extracts from its
    own clean, unnoised spoken_text — buyer, SKU, quantity, canonical unit, and rate — at
    confidence >= the production threshold. If this fails, the corpus's ground truth
    itself is wrong (not the normalizer/matcher), since noise hasn't entered the picture.
    """
    settings = AppSettings()
    matcher = BilingualCatalogMatcher(settings.catalog_path)

    failures = []
    for utterance in build_corpus():
        intents = matcher.parse_utterance(utterance.spoken_text)
        if len(intents) != len(utterance.ground_truth_trades):
            failures.append(
                f"{utterance.utterance_id}: extracted {len(intents)} trade(s), "
                f"expected {len(utterance.ground_truth_trades)} — {utterance.spoken_text!r}"
            )
            continue
        for i, (intent, truth) in enumerate(zip(intents, utterance.ground_truth_trades)):
            sku_name = matcher.skus[intent.sku_id].canonical_name if intent.sku_id else None
            mismatches = []
            if intent.buyer_id != truth.buyer_id:
                mismatches.append(f"buyer {intent.buyer_id!r} != {truth.buyer_id!r}")
            if sku_name != truth.sku_canonical_name:
                mismatches.append(f"sku {sku_name!r} != {truth.sku_canonical_name!r}")
            if intent.quantity != truth.quantity:
                mismatches.append(f"qty {intent.quantity!r} != {truth.quantity!r}")
            if intent.rate_inr != truth.rate_inr:
                mismatches.append(f"rate {intent.rate_inr!r} != {truth.rate_inr!r}")
            if intent.unit != truth.unit:
                mismatches.append(f"unit {intent.unit!r} != {truth.unit!r}")
            if intent.overall_confidence < settings.confidence_threshold:
                mismatches.append(f"confidence {intent.overall_confidence} below threshold")
            if mismatches:
                failures.append(f"{utterance.utterance_id}[{i}]: {'; '.join(mismatches)}")

    assert not failures, "corpus ground-truth mismatches on clean text:\n" + "\n".join(failures)
