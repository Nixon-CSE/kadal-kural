"""
Stateless, deterministic Tamil/Tanglish numeral normalizer, case-suffix stripper,
and Timbre v2.5 currency prosody formatter.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, Final, FrozenSet, List, Optional, Tuple

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
    "தொள்ளாயிரம்": 900, "ஆயிரம்": 1000, "ஐயாயிரம்": 5000,
    "ஒரு": 1, "லட்சம்": 100_000,
    "irubathi": 20, "muppathi": 30, "naarpadhu": 40, "aimbadhu": 50,
    "arupadhu": 60, "ezhunootri": 700, "ainootri": 500, "anju": 5,
}

# Case endings Prisma sometimes glues onto an additive-prefix word, e.g. live multi_09 output
# turned 'ஐநூற்று 60' into 'ஐநூற்றுக்கு 60'. Longest first so 'க்கும்' wins over 'க்கு'.
# 'உக்கு' covers the rare spelling with an independent vowel instead of the 'ு' sign.
TAMIL_PREFIX_CASE_ENDINGS: Final[Tuple[str, ...]] = (
    "க்கும்", "உக்கு", "க்கு", "ஆல்", "இல்", "ஓட",
)

# Connector word used in "<multiplier-word> லட்சத்து <remainder>" lakh-scale phrases,
# e.g. "ஒரு லட்சத்து இருபத்தி ஐயாயிரம்" (one lakh twenty five-thousand). Distinct from the
# standalone "லட்சம்" (bare "one lakh") handled as an ordinary TAMIL_NUMBER_WORDS entry.
TAMIL_LAKH_CONNECTOR: Final[str] = "லட்சத்து"

# "<tens>த்தி <N>-thousand word" means (tens + N) thousand, e.g. "இருபத்தி ஐயாயிரம்" is
# 20 + 5 thousand = 25,000 (not 20 + 5,000). Only the connective "-த்தி" tens forms are
# affected; a bare "இருபது ஆயிரம்" is ordinary multiplication and is left alone.
TAMIL_CONNECTIVE_TENS_SUFFIX: Final[str] = "த்தி"
THOUSAND: Final[int] = 1000
CONNECTIVE_TENS_MIN: Final[int] = 20
CONNECTIVE_TENS_MAX: Final[int] = 90
MULTI_THOUSAND_MIN: Final[int] = 2 * THOUSAND
MULTI_THOUSAND_MAX: Final[int] = 9 * THOUSAND

CANONICAL_UNIT_MAP: Final[Dict[str, str]] = {
    "பாக்ஸ்": "box", "பெட்டி": "box", "box": "box", "boxes": "box",
    "கிலோ": "kg", "கேஜி": "kg", "kilo": "kg", "kg": "kg",
    "செட்": "set", "set": "set", "பீஸ்": "pcs", "pieces": "pcs",
}

_RATE_WORD_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?:ரேட்டு|ரேட்|rate)", re.IGNORECASE)
_RATE_WORD_MARK: Final[str] = "\x00RATE\x00"

TRAILING_LEDGER_VERBS: Final[FrozenSet[str]] = frozenset({
    "கிரெடிட்டில்", "கிரெடிட்", "credit", "கணக்கில்", "லெட்ஜர்",
    "ஏற்று", "போடு", "யேத்து", "yethu", "podu", "rendume", "ரெண்டுமே",
})

BARGE_IN_OVERRIDE_MARKERS: Final[FrozenSet[str]] = frozenset({
    "மட்டும்", "mattum", "only", "மாத்து", "குறை",
})


def strip_numeral_decoration(token: str) -> Optional[str]:
    """
    Strips live Gnani Prisma v2.5 ITN decoration from a token and returns the bare digit
    string, or None if what remains isn't purely digits.

    Confirmed against live Prisma output: whenever the word 'ரூபாய்' (rupee) appears near
    a number, Prisma drops the literal word and instead prefixes the digits with '₹'
    (e.g. '40' -> '₹40'), and for larger amounts also applies Indian-style comma grouping
    ('1000' -> '1,000', '100000' -> '1,00,000'). Plain str.isdigit() returns False for all
    of these and silently breaks numeral/rate extraction downstream — use this instead
    anywhere a token might carry that decoration.
    """
    stripped = token.lstrip("₹").replace(",", "")
    return stripped if stripped.isdigit() else None


def _additive_prefix_value(token: str) -> Optional[int]:
    """
    Returns the TAMIL_ADDITIVE_PREFIXES value for token, first as-is and then with one
    case ending from TAMIL_PREFIX_CASE_ENDINGS stripped ('ஐநூற்றுக்கு' -> 500), or None.
    """
    value = TAMIL_ADDITIVE_PREFIXES.get(token)
    if value is not None:
        return value
    for ending in TAMIL_PREFIX_CASE_ENDINGS:
        if token.endswith(ending):
            value = TAMIL_ADDITIVE_PREFIXES.get(token[: -len(ending)])
            if value is not None:
                return value
    return None


def _fold_connective_tens_with_thousands(token: str, next_tok: str) -> Optional[int]:
    """
    Returns (tens + N) * 1000 for "<tens>த்தி <N-thousand word>" (e.g. 'இருபத்தி ஐயாயிரம்'
    -> 25000), or None if the pair doesn't have that shape.
    """
    tens = TAMIL_NUMBER_WORDS.get(token)
    thousands = TAMIL_NUMBER_WORDS.get(next_tok)
    if tens is None or thousands is None or not token.endswith(TAMIL_CONNECTIVE_TENS_SUFFIX):
        return None
    if not CONNECTIVE_TENS_MIN <= tens <= CONNECTIVE_TENS_MAX or tens % 10 != 0:
        return None
    if not MULTI_THOUSAND_MIN <= thousands <= MULTI_THOUSAND_MAX or thousands % THOUSAND != 0:
        return None
    return (tens + thousands // THOUSAND) * THOUSAND


def _sum_trailing_number_words(tokens: List[str], start_idx: int) -> Tuple[int, int]:
    """
    Greedily consumes consecutive still-unresolved Tamil number-word (and additive-prefix
    pair) tokens starting at start_idx and returns their summed value plus how many tokens
    were consumed. Stops at the first token that isn't a recognizable number word.

    This exists because Prisma sometimes pre-resolves only the leading (often lakh-scale)
    portion of an amount into a single decorated/grouped digit token and leaves the
    remainder as untouched Tamil words it never adds in itself, e.g.:
        'ஒரு லட்சத்து இருபத்தி ஐயாயிரம் ரூபாய்' -> '1,00,000 இருபத்தி ஐயாயிரம் ரூபாய்'
    This is a best-effort additive fold of the trailing words, not full Indian-numbering
    grammar — it has only been validated against the lakh-phrase sample above (live probe
    label 'word_lakh_phrase', see tamil_itn_probe_results.jsonl).
    """
    idx = start_idx
    total = len(tokens)
    running_sum = 0
    consumed = 0

    while idx < total:
        token = tokens[idx]

        prefix_val = _additive_prefix_value(token)
        if prefix_val is not None and idx + 1 < total:
            base_val = prefix_val
            next_tok = tokens[idx + 1]
            bare = strip_numeral_decoration(next_tok)
            if bare is not None:
                running_sum += base_val + int(bare)
                idx += 2
                consumed += 2
                continue
            if next_tok in TAMIL_NUMBER_WORDS:
                running_sum += base_val + TAMIL_NUMBER_WORDS[next_tok]
                idx += 2
                consumed += 2
                continue

        if token in TAMIL_NUMBER_WORDS:
            first_val = TAMIL_NUMBER_WORDS[token]
            if idx + 1 < total:
                next_tok = tokens[idx + 1]
                folded = _fold_connective_tens_with_thousands(token, next_tok)
                if folded is not None:
                    running_sum += folded
                    idx += 2
                    consumed += 2
                    continue
                bare = strip_numeral_decoration(next_tok)
                second_val = int(bare) if bare is not None else TAMIL_NUMBER_WORDS.get(next_tok, 0)
                if first_val >= 20 and 0 < second_val < first_val:
                    running_sum += first_val + second_val
                    idx += 2
                    consumed += 2
                    continue
            running_sum += first_val
            idx += 1
            consumed += 1
            continue

        break

    return running_sum, consumed


def normalize_hybrid_tamil_numerals(utterance: str) -> str:
    """
    Deterministically resolves hybrid Tamil-word + Arabic-digit numerals emitted by
    Gnani Prisma V2.5 (e.g., 'எழுநூற்றி 40' -> '740', 'ஐநூற்றி 60' -> '560'), including
    Prisma's live currency/grouping decoration ('எழுநூற்றி ₹40' -> '740', '₹1,000' -> '1000')
    and lakh-scale phrases ('ஒரு லட்சத்து இருபத்தி ஐயாயிரம்' -> '125000').

    Live-probe findings this is built against (see scripts/probe_tamil_itn.py):
      - Without the word 'ரூபாய்' present, hybrid additive phrases already arrive exactly
        as the digit/word shapes below expect.
      - With 'ரூபாய்' present, Prisma either (a) keeps the additive-prefix word literal and
        ₹-decorates only the remainder ('எழுநூற்றி ₹40'), or (b) fully pre-resolves the
        whole amount into one decorated/grouped token ('₹215', '₹1,000') and drops the
        prefix word entirely. Both are handled below.
      - Lakh-scale amounts only get the leading lakh portion digit-converted; the additive
        remainder is left as unconverted words and is folded in by _sum_trailing_number_words
        ('1,00,000 இருபத்தி ஐயாயிரம் ரூபாய்' is one lakh twenty-five thousand = 125000).
    """
    tokens = utterance.strip().split()
    resolved: List[str] = []
    idx = 0
    total = len(tokens)

    while idx < total:
        token = tokens[idx]

        # Lakh-scale: "<multiplier-word> லட்சத்து <additive remainder>"
        if (
            idx + 1 < total
            and tokens[idx + 1] == TAMIL_LAKH_CONNECTOR
            and token in TAMIL_NUMBER_WORDS
        ):
            lakh_base = TAMIL_NUMBER_WORDS[token] * 100_000
            idx += 2
            remainder, consumed = _sum_trailing_number_words(tokens, idx)
            idx += consumed
            resolved.append(str(lakh_base + remainder))
            continue

        # Hybrid: "<hundred/thousand-prefix word> <digit | ₹/comma-decorated digit | word>"
        # (a case ending glued onto the prefix word is tolerated: 'ஐநூற்றுக்கு 60' -> '560')
        prefix_val = _additive_prefix_value(token)
        if prefix_val is not None and idx + 1 < total:
            base_val = prefix_val
            next_tok = tokens[idx + 1]
            bare = strip_numeral_decoration(next_tok)
            if bare is not None:
                resolved.append(str(base_val + int(bare)))
                idx += 2
                continue
            if next_tok in TAMIL_NUMBER_WORDS:
                resolved.append(str(base_val + TAMIL_NUMBER_WORDS[next_tok]))
                idx += 2
                continue

        # Connective tens + N-thousand word, e.g. "இருபத்தி ஐயாயிரம்" -> 25000
        if idx + 1 < total:
            folded = _fold_connective_tens_with_thousands(token, tokens[idx + 1])
            if folded is not None:
                resolved.append(str(folded))
                idx += 2
                continue

        # Compound tens+units word pair, e.g. "இருபத்தி ஐந்து" -> 25
        if token in TAMIL_NUMBER_WORDS and idx + 1 < total:
            first_val = TAMIL_NUMBER_WORDS[token]
            next_tok = tokens[idx + 1]
            bare = strip_numeral_decoration(next_tok)
            second_val = int(bare) if bare is not None else TAMIL_NUMBER_WORDS.get(next_tok, 0)
            if first_val >= 20 and 0 < second_val < first_val:
                resolved.append(str(first_val + second_val))
                idx += 2
                continue

        if token in TAMIL_NUMBER_WORDS:
            resolved.append(str(TAMIL_NUMBER_WORDS[token]))
            idx += 1
            continue

        # Standalone Prisma-decorated digit token with no preceding additive-prefix word,
        # e.g. '₹215', '₹1,000', or a bare lakh-grouped '1,00,000' with no leading '₹'.
        bare = strip_numeral_decoration(token)
        if bare is not None:
            total_val = int(bare)
            idx += 1
            remainder, consumed = _sum_trailing_number_words(tokens, idx)
            total_val += remainder
            idx += consumed
            resolved.append(str(total_val))
            continue

        resolved.append(token)
        idx += 1

    return " ".join(resolved)


def strip_tamil_dative_suffix(phrase: str) -> str:
    """
    Removes Tamil dative case suffixes (-க்கு, -னுக்கு, -லுக்கு, -உக்கு, -ku, bare -கு) attached to buyer names.
    Note: In Unicode, 'னுக்கு' is 6 codepoints (ன+ு+க+்+க+ு) and 'லுக்கு' is 6 codepoints (ல+ு+க+்+க+ு).
    The bare 'கு' is how Prisma writes Tanglish 'ku' glued to a name ('Senthil ku' -> 'செந்தில்கு');
    it is tried last, after every suffix that itself ends in 'கு'.
    """
    cleaned = phrase.strip()
    if cleaned.endswith("னுக்கு") and len(cleaned) > len("னுக்கு"):
        return cleaned[: -len("னுக்கு")] + "ன்"
    if cleaned.endswith("லுக்கு") and len(cleaned) > len("லுக்கு"):
        return cleaned[: -len("லுக்கு")] + "ல்"
    for suffix in ("க்கு", "உக்கு", "-ku", "ku", "கு"):
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


def _is_number(token: str) -> bool:
    return strip_numeral_decoration(token) is not None


def ends_with_rate_terminator(normalized_text: str) -> bool:
    """True for '... 740 ரேட்டு' and '... ரேட்டு 740': the last clause was closed by its rate word."""
    tokens = normalized_text.split()
    if not tokens:
        return False
    if _RATE_WORD_PATTERN.fullmatch(tokens[-1]):
        return True
    return len(tokens) >= 2 and _is_number(tokens[-1]) and bool(_RATE_WORD_PATTERN.fullmatch(tokens[-2]))


def split_multi_trade_clauses(
    normalized_text: str,
    buyer_phrase_length: Optional[Callable[[Optional[str], str], int]] = None,
) -> List[str]:
    """
    Splits a single-breath utterance into one clause per trade. Boundaries:

    - The rate word ('ரேட்டு', 'ரேட், 'rate') ends a clause, whichever side of it the rate is on:
      '... 740 ரேட்டு' and '... ரேட்டு 740' both give a clause holding quantity and rate. A number
      after the rate word is taken as the rate only while the clause still lacks one, and not
      when a unit follows it ('ரேட்டு 30 கிலோ' starts the next trade's quantity).
    - A buyer name starts a new clause once the current one holds a number, even with no rate
      word before it (Prisma sometimes mishears the rate word). ``buyer_phrase_length(previous,
      token)`` says whether ``token`` ends a buyer phrase: 0 no, 1 by itself, 2 with the word
      before it (``previous``, None when that word is a number).

    Misspelled rate words are deliberately not matched.
    """
    tokens = _RATE_WORD_PATTERN.sub(f" {_RATE_WORD_MARK} ", normalized_text).split()
    clauses: List[List[str]] = []
    current: List[str] = []
    numbers = 0
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token == _RATE_WORD_MARK:
            following = tokens[idx + 1] if idx + 1 < len(tokens) else ""
            after_following = tokens[idx + 2].lower() if idx + 2 < len(tokens) else ""
            if numbers == 1 and _is_number(following) and after_following not in CANONICAL_UNIT_MAP:
                current.append(following)
                idx += 1
            clauses.append(current)
            current, numbers = [], 0
        else:
            if numbers and buyer_phrase_length is not None:
                previous = current[-1] if not _is_number(current[-1]) else None
                length = buyer_phrase_length(previous, token)
                if length:
                    carried = [current.pop()] if length == 2 else []
                    clauses.append(current)
                    current, numbers = carried, 0
            current.append(token)
            numbers += _is_number(token)
        idx += 1
    clauses.append(current)

    valid_clauses: List[str] = []
    for words in clauses:
        cleaned = " ".join(words).strip(" ,.-")
        if cleaned and not all(w.lower() in TRAILING_LEDGER_VERBS for w in cleaned.split()):
            valid_clauses.append(cleaned)
    return valid_clauses