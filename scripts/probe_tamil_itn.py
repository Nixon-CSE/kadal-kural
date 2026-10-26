"""
Live Tamil Inverse-Text-Normalization (ITN) probe against Gnani's Sovereign Artha Stack.

Purpose
-------
`normalize_hybrid_tamil_numerals` (src/kadal_kural/domain/normalizer.py) assumes a specific
shape for the numerals Prisma v2.5 hands back in its transcript: either a pure Tamil number
WORD, a pure Arabic DIGIT string, or a hybrid "additive-prefix-word + digit/word" pair
(e.g. "எழுநூற்றி 40" or "ஐநூற்றி அறுபது"). That assumption was written without ever having
seen a real Prisma transcript for these phrases.

This script closes that gap end-to-end, using only the *production* client
(GnaniArthaSpeechClient) and zero mocks:

    1. For each candidate Tamil phrase, synthesize speech audio via Timbre v2.5 (TTS).
    2. Strip Timbre's WAV container down to raw 16-bit PCM.
    3. Stream that PCM into Prisma v2.5 (STT) through the same 1024-byte framing/pacing
       path production uses (PCM1024RingBufferPacer + stream_pcm_to_prisma_v25).
    4. Capture every transcript segment Prisma emits for that phrase.
    5. Append one JSON record per phrase to the output log:
           {"input_text": ..., "raw_transcript": ..., "stt_latency_ms": ..., "elapsed_s": ...}

Run (requires a live KADAL_GNANI_API_KEY in .env; this hits the real api.vachana.ai stack):

    python scripts/probe_tamil_itn.py
    python scripts/probe_tamil_itn.py --limit 5          # quick smoke test first
    python scripts/probe_tamil_itn.py --out my_run.jsonl

Nothing here is mocked. This is a one-shot research tool, not part of the test suite —
its output is the evidence base for the next edit to normalize_hybrid_tamil_numerals.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kadal_kural.config import AppSettings  # noqa: E402
from kadal_kural.infrastructure.gnani_client import (  # noqa: E402
    GnaniArthaSpeechClient,
    GnaniConfigurationError,
)

PROBE_SAMPLE_RATE = 16000

# Each entry: (label, phrase). Labels make the JSONL log scannable; they are not sent anywhere.
CANDIDATE_PHRASES: List[Tuple[str, str]] = [
    # --- Pure Tamil number WORDS (no digits at all) ---
    ("word_simple_25", "இருபத்தி ஐந்து பாக்ஸ் வஞ்சரம்"),
    ("word_additive_740", "எழுநூற்றி நாப்பது ரூபாய்"),
    ("word_additive_560", "ஐநூற்றி அறுபது ரூபாய்"),
    ("word_additive_215", "இருநூற்றி பதினைந்து ரூபாய்"),
    ("word_round_hundred", "நூறு பாக்ஸ்"),
    ("word_round_thousand", "ஆயிரம் ரூபாய்"),
    ("word_lakh_phrase", "ஒரு லட்சத்து இருபத்தி ஐயாயிரம் ரூபாய்"),
    # --- Pure ARABIC DIGITS spoken as digit strings ---
    ("digit_simple_25", "25 பாக்ஸ் வஞ்சரம்"),
    ("digit_740", "740 ரூபாய்"),
    ("digit_three_digit_rate", "செந்திலுக்கு 25 பாக்ஸ் வஞ்சரம் ரேட்டு 250"),
    # --- HYBRID: additive-prefix word immediately followed by a digit/word pair ---
    ("hybrid_740_digit", "எழுநூற்றி 40 ரூபாய்"),
    ("hybrid_560_digit", "ஐநூற்றி 60 ரூபாய்"),
    ("hybrid_215_word", "இருநூற்றி பதினைந்து ரூபாய் கணக்கில் போடு"),
    # --- Full realistic multi-trade utterances (what the matcher actually receives) ---
    ("trade_senthil_full", "செந்திலுக்கு இருபத்தி ஐந்து பாக்ஸ் வஞ்சரம் ரேட்டு இருநூற்று ஐம்பது"),
    ("trade_kumaran_full", "குமரனுக்கு பத்து கிலோ டைகர் பிரான் ரேட்டு எழுநூற்றி நாப்பது"),
    ("trade_barge_in_override", "செந்திலுக்கு இருபது பாக்ஸ் மட்டும் போடு"),
    ("trade_tanglish_mixed", "Senthil ku 25 box Vanjaram rate 250"),
    # --- Undo / cancel voice command, for completeness ---
    ("undo_command", "கடைசி ஆர்டர் கேன்சல்"),
]


def _wav_to_raw_pcm(wav_bytes: bytes) -> bytes:
    """
    Strips the WAV/RIFF container Timbre v2.5 wraps its audio in and returns the
    raw linear-PCM frame data, which is what stream_pcm_to_prisma_v25 (and the real
    browser/telephony callers) actually feed into Prisma.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_reader:
        return wav_reader.readframes(wav_reader.getnframes())


async def _probe_one_phrase(
    client: GnaniArthaSpeechClient,
    label: str,
    phrase: str,
) -> Dict[str, Any]:
    t_start = time.perf_counter()

    telemetry = await client.synthesize_timbre_v25(phrase, sample_rate=PROBE_SAMPLE_RATE)
    raw_pcm = _wav_to_raw_pcm(telemetry.audio_wav_bytes)

    collected_segments: List[Tuple[str, float]] = []

    async def _collect(transcript: str, stt_latency_ms: float) -> None:
        collected_segments.append((transcript, stt_latency_ms))

    await client.stream_pcm_to_prisma_v25(
        raw_pcm,
        _collect,
        sample_rate=PROBE_SAMPLE_RATE,
    )

    elapsed_s = round(time.perf_counter() - t_start, 2)
    raw_transcript = " ".join(seg[0] for seg in collected_segments).strip()
    mean_latency_ms = (
        round(sum(seg[1] for seg in collected_segments) / len(collected_segments), 1)
        if collected_segments
        else None
    )

    return {
        "label": label,
        "input_text": phrase,
        "raw_transcript": raw_transcript,
        "segment_count": len(collected_segments),
        "stt_latency_ms": mean_latency_ms,
        "tts_ttfb_ms": telemetry.ttfb_ms,
        "elapsed_s": elapsed_s,
    }


async def run_probe(limit: int, out_path: Path) -> None:
    settings = AppSettings()
    client = GnaniArthaSpeechClient(settings)

    phrases = CANDIDATE_PHRASES[: limit if limit > 0 else len(CANDIDATE_PHRASES)]
    print(f"Probing {len(phrases)} phrase(s) against live Gnani Artha stack...", file=sys.stderr)

    with out_path.open("w", encoding="utf-8") as fh:
        for i, (label, phrase) in enumerate(phrases, start=1):
            print(f"[{i}/{len(phrases)}] {label}: {phrase!r}", file=sys.stderr)
            try:
                record = await _probe_one_phrase(client, label, phrase)
            except Exception as exc:  # noqa: BLE001 - log and continue; this is a research tool
                record = {
                    "label": label,
                    "input_text": phrase,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                print(f"    ERROR: {record['error']}", file=sys.stderr)
            else:
                print(f"    -> {record['raw_transcript']!r}", file=sys.stderr)
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()

    print(f"\nDone. Results written to {out_path}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=0, help="Only probe the first N phrases (0 = all)."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tamil_itn_probe_results.jsonl"),
        help="Output JSONL path.",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_probe(args.limit, args.out))
    except GnaniConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()