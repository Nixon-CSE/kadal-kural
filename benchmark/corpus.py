"""
Tamil/Tanglish trade-utterance corpus for the Noise & Silent-Error Benchmark Suite.

Varies buyer, SKU, quantity, rate (across four numeral spellings: plain digit, pure
Tamil word, additive-prefix hybrid, and romanized Tanglish), and single- vs.
multi-trade-per-breath structure, per the Phase 2 brief.

Ground truth deliberately carries only the *entities* each utterance encodes (buyer,
SKU, quantity, unit, rate) — never a pre-computed expected LedgerEventStatus or
trade_value_inr. Those are derived quantities the real PreDispatchCreditFirewallService
computes from catalog.json's live credit_limit/opening_balance; hand-duplicating that
arithmetic here would just be a second place for a ground-truth bug to hide. See
run_eval.py: every utterance is evaluated against a *fresh* ledger seeded from
catalog.json, so corpus ground truth never depends on run order — except within a single
multi-trade utterance, where the second clause's expected ledger balance genuinely does
depend on the first clause committing within that same evaluate_utterance() call, exactly
as the production firewall already handles it.

Clause convention (required by BilingualCatalogMatcher.parse_utterance /
split_multi_trade_clauses — confirmed against the existing passing integration test using
PLAYGROUND_SCREENSHOT_TRANSCRIPT): each trade clause is
    <buyer dative-form> <quantity> <unit> <sku> <rate> ரேட்டு
with "ரேட்டு" (or "ரேட்"/"rate") acting as the clause *terminator*, not a "here comes the
rate" prefix — normalize_hybrid_tamil_numerals runs on the whole utterance before the
split, so an additive-hybrid rate spelling before "ரேட்டு" is already a resolved digit by
the time the clause boundary is found. Multiple trades in one utterance are simply
multiple such clauses back to back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, List, Tuple

# ---------------------------------------------------------------------------- catalog refs
# Mirrors src/kadal_kural/data/catalog.json. Kept as plain constants (not a JSON read) so
# the corpus has no import-order dependency on the app package, and so a catalog edit is
# forced to be a deliberate, visible change here too.

BUY_SENTHIL: Final[str] = "BUY-101"
BUY_KUMARAN: Final[str] = "BUY-102"
SKU_VANJARAM: Final[str] = "Export Vanjaram"
SKU_PRAWN: Final[str] = "Tiger Prawn"

_BUYER_DATIVE_FORMS: Final[dict[str, Tuple[str, ...]]] = {
    BUY_SENTHIL: ("செந்திலுக்கு", "செந்தில் சீஃபுட்ஸ்க்கு"),
    BUY_KUMARAN: ("குமரனுக்கு",),
}
_SKU_PHRASES: Final[dict[str, Tuple[Tuple[str, str, str], ...]]] = {
    # (spoken SKU phrase, spoken Tamil unit word, canonical unit the matcher resolves to —
    # CANONICAL_UNIT_MAP always normalizes to the short English form regardless of input
    # script, so ground truth must store that, not the word actually spoken)
    # Vanjaram is quoted and sold per kg at Kasimedu (see ValueRange in models.py), so every
    # Vanjaram clause says கிலோ and its rate is a per-kg price inside catalog rate_range_inr.
    SKU_VANJARAM: (
        ("வஞ்சரம்", "கிலோ", "kg"),
        ("எக்ஸ்போர்ட் வஞ்சரம்", "கிலோ", "kg"),
    ),
    SKU_PRAWN: (("டைகர் பிரான்", "கிலோ", "kg"),),
}

# Every spelling below was individually verified against normalize_hybrid_tamil_numerals
# before being baked in as ground truth (see docs/itn_findings.md for why that matters —
# an ungrammatical hybrid compound silently resolves to the wrong number instead of
# erroring). Four numeral "styles" are rotated across the corpus so the benchmark exercises
# each STT-rendering shape confirmed live in Task 2, not just one.
_QTY_DIGIT: Final[dict[int, str]] = {q: str(q) for q in (10, 15, 20, 25, 30, 40, 50, 60)}
_QTY_WORD: Final[dict[int, str]] = {
    10: "பத்து", 15: "பதினைந்து", 20: "இருபது", 25: "இருபத்தி ஐந்து",
    30: "முப்பது", 40: "நாற்பது", 50: "ஐம்பது", 60: "அறுபது",
}
_QTY_TANGLISH: Final[dict[int, str]] = {20: "irubathi", 30: "muppathi", 40: "naarpadhu", 50: "aimbadhu"}

# Every rate is inside its SKU's catalog rate_range_inr (Vanjaram ₹400–1,600/kg, Tiger Prawn
# ₹300–1,500/kg); see test_every_corpus_amount_is_inside_its_catalog_band.
_RATE_DIGIT: Final[dict[int, str]] = {
    r: str(r) for r in (500, 600, 700, 800, 950, 1200)
}
_RATE_WORD: Final[dict[int, str]] = {
    450: "நானூற்றி ஐம்பது", 650: "அறுநூற்றி ஐம்பது", 700: "எழுநூறு", 800: "எண்ணூறு",
    900: "தொள்ளாயிரம்", 600: "அறுநூறு",
}
_RATE_HYBRID: Final[dict[int, str]] = {
    # additive-prefix word + digit remainder — the shape Prisma emits most often per the
    # live ITN probe (docs/itn_findings.md, Finding 1 & 2)
    560: "ஐநூற்று 60", 740: "எழுநூற்றி 40", 350: "முந்நூற்றி 50", 1050: "ஆயிரத்தி 50",
}


@dataclass(frozen=True)
class GroundTruthTrade:
    """The true entities one trade clause encodes, independent of any pipeline run."""

    buyer_id: str
    sku_canonical_name: str
    quantity: int
    unit: str
    rate_inr: int


@dataclass(frozen=True)
class BenchmarkUtterance:
    """One corpus item: clean Tamil/Tanglish speech text plus its entity ground truth."""

    utterance_id: str
    spoken_text: str
    ground_truth_trades: Tuple[GroundTruthTrade, ...]
    category: str  # e.g. "single_digit", "single_word", "multi_trade", "tanglish"


def _clause(
    buyer_id: str,
    buyer_phrase: str,
    quantity: int,
    qty_phrase: str,
    sku_id: str,
    sku_phrase: str,
    spoken_unit: str,
    canonical_unit: str,
    rate: int,
    rate_phrase: str,
) -> Tuple[str, GroundTruthTrade]:
    text = f"{buyer_phrase} {qty_phrase} {spoken_unit} {sku_phrase} {rate_phrase} ரேட்டு"
    truth = GroundTruthTrade(
        buyer_id=buyer_id,
        sku_canonical_name=sku_id,
        quantity=quantity,
        unit=canonical_unit,
        rate_inr=rate,
    )
    return text, truth


def _build_single_trade_utterances() -> List[BenchmarkUtterance]:
    utterances: List[BenchmarkUtterance] = []
    combos = [
        (BUY_SENTHIL, 0, SKU_VANJARAM, 0, 10, 800, "single_digit", _QTY_DIGIT, _RATE_DIGIT),
        (BUY_SENTHIL, 1, SKU_VANJARAM, 0, 40, 740, "single_hybrid", _QTY_DIGIT, _RATE_HYBRID),
        (BUY_SENTHIL, 0, SKU_PRAWN, 0, 15, 560, "single_hybrid", _QTY_WORD, _RATE_HYBRID),
        (BUY_SENTHIL, 0, SKU_VANJARAM, 1, 20, 1050, "single_hybrid", _QTY_WORD, _RATE_HYBRID),
        (BUY_SENTHIL, 1, SKU_PRAWN, 0, 10, 700, "single_word", _QTY_WORD, _RATE_WORD),
        (BUY_SENTHIL, 0, SKU_VANJARAM, 0, 30, 600, "single_digit", _QTY_DIGIT, _RATE_DIGIT),
        (BUY_SENTHIL, 0, SKU_PRAWN, 0, 30, 450, "single_word", _QTY_WORD, _RATE_WORD),
        (BUY_SENTHIL, 1, SKU_VANJARAM, 0, 60, 800, "single_digit", _QTY_DIGIT, _RATE_DIGIT),
        (BUY_KUMARAN, 0, SKU_PRAWN, 0, 10, 500, "single_digit", _QTY_DIGIT, _RATE_DIGIT),
        (BUY_KUMARAN, 0, SKU_VANJARAM, 0, 20, 900, "single_word", _QTY_WORD, _RATE_WORD),
        (BUY_KUMARAN, 0, SKU_PRAWN, 0, 60, 740, "single_hybrid", _QTY_DIGIT, _RATE_HYBRID),
        (BUY_KUMARAN, 0, SKU_VANJARAM, 1, 15, 800, "single_word", _QTY_WORD, _RATE_WORD),
        (BUY_KUMARAN, 0, SKU_PRAWN, 0, 25, 560, "single_hybrid", _QTY_WORD, _RATE_HYBRID),
        (BUY_KUMARAN, 0, SKU_VANJARAM, 0, 40, 600, "single_digit", _QTY_DIGIT, _RATE_DIGIT),
        (BUY_KUMARAN, 0, SKU_PRAWN, 0, 50, 650, "single_word", _QTY_WORD, _RATE_WORD),
        (BUY_KUMARAN, 0, SKU_VANJARAM, 0, 30, 1200, "single_digit", _QTY_DIGIT, _RATE_DIGIT),
    ]
    for idx, (buyer_id, buyer_variant, sku_id, sku_variant, qty, rate, category, qty_map, rate_map) in enumerate(
        combos, start=1
    ):
        buyer_phrase = _BUYER_DATIVE_FORMS[buyer_id][buyer_variant % len(_BUYER_DATIVE_FORMS[buyer_id])]
        sku_phrase, spoken_unit, canonical_unit = _SKU_PHRASES[sku_id][
            sku_variant % len(_SKU_PHRASES[sku_id])
        ]
        text, truth = _clause(
            buyer_id, buyer_phrase, qty, qty_map[qty], sku_id, sku_phrase,
            spoken_unit, canonical_unit, rate, rate_map[rate],
        )
        utterances.append(
            BenchmarkUtterance(
                utterance_id=f"single_{idx:02d}",
                spoken_text=text,
                ground_truth_trades=(truth,),
                category=category,
            )
        )

    # Tanglish-mixed single-trade utterances (English buyer/unit/rate words interleaved) —
    # deliberately exercises the known strip_tamil_dative_suffix gap on bare "கு" flagged in
    # docs/itn_findings.md Finding 4, so the benchmark measures its real-world impact.
    tanglish_combos = [
        (BUY_SENTHIL, SKU_VANJARAM, 20, "kg", 950),
        (BUY_KUMARAN, SKU_PRAWN, 30, "kg", 500),
        (BUY_SENTHIL, SKU_PRAWN, 40, "kg", 700),
        (BUY_KUMARAN, SKU_VANJARAM, 50, "kg", 700),
    ]
    for idx, (buyer_id, sku_id, qty, unit_en, rate) in enumerate(tanglish_combos, start=1):
        buyer_short = "Senthil" if buyer_id == BUY_SENTHIL else "Kumaran"
        sku_en = "Vanjaram" if sku_id == SKU_VANJARAM else "Prawn"
        # split_multi_trade_clauses matches "rate"/"ரேட்டு"/"ரேட்" case-insensitively as a
        # raw substring (no word-boundary anchor), so only ONE such token may appear per
        # clause or it splits the rate digits into their own buyer-less clause (caught by
        # the corpus's own clean-text validation below). "ரேட்டு" is used as the sole
        # terminator, placed after the digit like every other clause in this corpus.
        text = f"{buyer_short} ku {_QTY_TANGLISH.get(qty, str(qty))} {unit_en} {sku_en} {rate} ரேட்டு"
        truth = GroundTruthTrade(
            buyer_id=buyer_id, sku_canonical_name=sku_id, quantity=qty, unit=unit_en, rate_inr=rate
        )
        utterances.append(
            BenchmarkUtterance(
                utterance_id=f"tanglish_{idx:02d}",
                spoken_text=text,
                ground_truth_trades=(truth,),
                category="tanglish",
            )
        )
    return utterances


def _build_multi_trade_utterances() -> List[BenchmarkUtterance]:
    first_combos = [
        (BUY_SENTHIL, 0, SKU_VANJARAM, 0, 10, 800, _QTY_DIGIT, _RATE_DIGIT),
        (BUY_SENTHIL, 1, SKU_PRAWN, 0, 15, 560, _QTY_WORD, _RATE_HYBRID),
        (BUY_KUMARAN, 0, SKU_VANJARAM, 1, 40, 740, _QTY_DIGIT, _RATE_HYBRID),
        (BUY_SENTHIL, 0, SKU_VANJARAM, 0, 30, 600, _QTY_WORD, _RATE_WORD),
        (BUY_KUMARAN, 0, SKU_PRAWN, 0, 20, 350, _QTY_WORD, _RATE_HYBRID),
    ]
    second_combos = [
        (BUY_KUMARAN, 0, SKU_PRAWN, 0, 10, 500, _QTY_DIGIT, _RATE_DIGIT),
        (BUY_KUMARAN, 0, SKU_VANJARAM, 0, 10, 800, _QTY_WORD, _RATE_WORD),
        (BUY_SENTHIL, 0, SKU_PRAWN, 0, 30, 450, _QTY_WORD, _RATE_WORD),
        (BUY_KUMARAN, 0, SKU_PRAWN, 0, 60, 740, _QTY_DIGIT, _RATE_HYBRID),
        (BUY_SENTHIL, 1, SKU_VANJARAM, 0, 40, 600, _QTY_DIGIT, _RATE_DIGIT),
    ]
    utterances: List[BenchmarkUtterance] = []
    idx = 0
    for first in first_combos:
        for second in second_combos:
            idx += 1
            fb_id, fb_var, fs_id, fs_var, fq, fr, fqm, frm = first
            sb_id, sb_var, ss_id, ss_var, sq, sr, sqm, srm = second
            fb_phrase = _BUYER_DATIVE_FORMS[fb_id][fb_var % len(_BUYER_DATIVE_FORMS[fb_id])]
            fs_phrase, f_spoken_unit, f_canonical_unit = _SKU_PHRASES[fs_id][
                fs_var % len(_SKU_PHRASES[fs_id])
            ]
            sb_phrase = _BUYER_DATIVE_FORMS[sb_id][sb_var % len(_BUYER_DATIVE_FORMS[sb_id])]
            ss_phrase, s_spoken_unit, s_canonical_unit = _SKU_PHRASES[ss_id][
                ss_var % len(_SKU_PHRASES[ss_id])
            ]

            first_text, first_truth = _clause(
                fb_id, fb_phrase, fq, fqm[fq], fs_id, fs_phrase,
                f_spoken_unit, f_canonical_unit, fr, frm[fr],
            )
            second_text, second_truth = _clause(
                sb_id, sb_phrase, sq, sqm[sq], ss_id, ss_phrase,
                s_spoken_unit, s_canonical_unit, sr, srm[sr],
            )
            utterances.append(
                BenchmarkUtterance(
                    utterance_id=f"multi_{idx:02d}",
                    spoken_text=f"{first_text} {second_text}",
                    ground_truth_trades=(first_truth, second_truth),
                    category="multi_trade",
                )
            )
    return utterances


def build_corpus() -> List[BenchmarkUtterance]:
    """Returns the full benchmark corpus: single-trade + Tanglish + multi-trade utterances."""
    return _build_single_trade_utterances() + _build_multi_trade_utterances()


if __name__ == "__main__":
    corpus = build_corpus()
    counts: dict[str, int] = {}
    for u in corpus:
        counts[u.category] = counts.get(u.category, 0) + 1
    print(f"Corpus size: {len(corpus)}")
    for cat, n in sorted(counts.items()):
        print(f"  {cat}: {n}")
