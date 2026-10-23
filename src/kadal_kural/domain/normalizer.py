"""
Stateless, deterministic Tamil/Tanglish numeral normalizer, case-suffix stripper,
and Timbre v2.5 currency prosody formatter.
"""

from __future__ import annotations

import re
from typing import Dict, Final, FrozenSet, List

TAMIL_ADDITIVE_PREFIXES: Final[Dict[str, int]] = {
    "நூற்றி": 100,
    "நூற்று": 100,
    "இருநூற்றி": 200,
    "இருநூற்று": 200,
    "முந்நூற்றி": 300,
    "முந்நூற்று": 300,
    "நானூற்றி": 400,
    "நானூற்று": 400,
    "ஐநூற்றி": 500,
    "ஐநூற்று": 500,
    "ஐந்நூற்றி": 500,
    "அறுநூற்றி": 600,
    "அறுநூற்று": 600,
    "எழுநூற்றி": 700,
    "எழுநூற்று": 700,
    "எண்ணூற்றி": 800,
    "எண்ணூற்று": 800,
    "தொள்ளாயிரத்தி": 900,
    "தொள்ளாயிரத்து": 900,
    "ஆயிரத்தி": 1000,
    "ஆயிரத்து": 1000,
}

TAMIL_NUMBER_WORDS: Final[Dict[str, int]] = {
    "ஒன்று": 1, "ஒன்னு": 1, "இரண்டு": 2, "ரெண்டு": 2, "மூன்று": 3, "மூணு": 3,
    "நான்கு": 4, "நாலு": 4, "ஐந்து": 5, "அஞ்சு": 5, "ஆறு": 6, "ஏழு": 7,
    "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10, "பதினைந்து": 15, "இருபது": 20,
    "இருபத்தி": 20, "முப்பது": 30, "முப்பத்தி": 30, "நாற்பது": 40, "நாப்பத்தி": 40,
    "ஐம்பது": 50, "அம்பத்தி": 50, "அறுபது": 60, "அறுபத்தி": 60, "எழுபது": 70,
    "எண்பது": 80, "தொண்ணூறு": 90, "நூறு": 100, "இருநூறு": 200, "முந்நூறு": 300,
    "நானூறு": 400, "ஐநூறு": 500, "அறுநூறு": 600, "எழுநூறு": 700, "எண்ணூறு": 800,
    "தொள்ளாயிரம்": 900, "ஆயிரம்": 1000,
    "irubathi": 20, "muppathi": 30, "naarpadhu": 40, "aimbadhu": 50,
    "arupadhu": 60, "ezhunootri": 700, "ainootri": 500, "anju": 5,
}

CANONICAL_UNIT_MAP: Final[Dict[str, str]] = {
    "பாக்ஸ்": "box", "பெட்டி": "box", "box": "box", "boxes": "box",
    "கிலோ": "kg", "கேஜி": "kg", "kilo": "kg", "kg": "kg",
    "செட்": "set", "set": "set", "பீஸ்": "pcs", "pieces": "pcs",
}

TRAILING_LEDGER_VERBS: Final[FrozenSet[str]] = frozenset({
    "கிரெடிட்டில்", "கிரெடிட்", "credit", "கணக்கில்", "லெட்ஜர்",
    "ஏற்று", "போடு", "யேத்து", "yethu", "podu", "rendume", "ரெண்டுமே",
})

BARGE_IN_OVERRIDE_MARKERS: Final[FrozenSet[str]] = frozenset({
    "மட்டும்", "mattum", "only", "மாத்து", "குறை",
})


def normalize_hybrid_tamil_numerals(utterance: str) -> str:
    """
    Deterministically resolves hybrid Tamil-word + Arabic-digit numerals emitted by
    Gnani Prisma V2.5 (e.g., 'எழுநூற்றி 40' -> '740', 'ஐநூற்றி 60' -> '560').
    """
    tokens = utterance.strip().split()
    resolved: List[str] = []
    idx = 0
    total = len(tokens)

    while idx < total:
        token = tokens[idx]
        if token in TAMIL_ADDITIVE_PREFIXES and idx + 1 < total:
            base_val = TAMIL_ADDITIVE_PREFIXES[token]
            next_tok = tokens[idx + 1]
            if next_tok.isdigit():
                resolved.append(str(base_val + int(next_tok)))
                idx += 2
                continue
            if next_tok in TAMIL_NUMBER_WORDS:
                resolved.append(str(base_val + TAMIL_NUMBER_WORDS[next_tok]))
                idx += 2
                continue

        if token in TAMIL_NUMBER_WORDS and idx + 1 < total:
            first_val = TAMIL_NUMBER_WORDS[token]
            next_tok = tokens[idx + 1]
            second_val = int(next_tok) if next_tok.isdigit() else TAMIL_NUMBER_WORDS.get(next_tok, 0)
            if first_val >= 20 and 0 < second_val < first_val:
                resolved.append(str(first_val + second_val))
                idx += 2
                continue

        if token in TAMIL_NUMBER_WORDS:
            resolved.append(str(TAMIL_NUMBER_WORDS[token]))
        else:
            resolved.append(token)
        idx += 1

    return " ".join(resolved)


def strip_tamil_dative_suffix(phrase: str) -> str:
    """
    Removes Tamil dative case suffixes (-க்கு, -னுக்கு, -லுக்கு, -உக்கு, -ku) attached to buyer names.
    Note: In Unicode, 'னுக்கு' is 6 codepoints (ன+ு+க+்+க+ு) and 'லுக்கு' is 6 codepoints (ல+ு+க+்+க+ு).
    """
    cleaned = phrase.strip()
    if cleaned.endswith("னுக்கு") and len(cleaned) > len("னுக்கு"):
        return cleaned[: -len("னுக்கு")] + "ன்"
    if cleaned.endswith("லுக்கு") and len(cleaned) > len("லுக்கு"):
        return cleaned[: -len("லுக்கு")] + "ல்"
    for suffix in ("க்கு", "உக்கு", "-ku", "ku"):
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix) + 1:
            return cleaned[: -len(suffix)].strip()
    return cleaned


def format_inr_for_timbre_prosody(amount_inr: int) -> str:
    """
    Formats integer INR values into explicit Tamil lakh/thousand phrases so
    Gnani Timbre v2.5 synthesizes amounts with natural Indian financial cadence.
    """
    if amount_inr >= 100_000:
        lakhs = amount_inr // 100_000
        remainder = amount_inr % 100_000
        thousands = remainder // 1_000
        hundreds = remainder % 1_000
        if thousands > 0 and hundreds > 0:
            return f"{lakhs} லட்சத்து {thousands} ஆயிரத்து {hundreds} ரூபாய்"
        if thousands > 0:
            return f"{lakhs} லட்சத்து {thousands} ஆயிரம் ரூபாய்"
        return f"{lakhs} லட்சம் ரூபாய்"
    return f"ரூபாய் {amount_inr:,}"


def split_multi_trade_clauses(normalized_text: str) -> List[str]:
    """Splits a single-breath utterance across rate boundary markers ('ரேட்டு', 'ரேட்', 'rate')."""
    raw_clauses = re.split(r"(?:ரேட்டு|ரேட்|rate)\s*", normalized_text, flags=re.IGNORECASE)
    valid_clauses: List[str] = []
    for clause in raw_clauses:
        cleaned = clause.strip(" ,.-")
        if not cleaned:
            continue
        words = cleaned.split()
        if all(w.lower() in TRAILING_LEDGER_VERBS for w in words):
            continue
        valid_clauses.append(cleaned)
    return valid_clauses