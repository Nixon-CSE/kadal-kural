"""
Live probe: does Prisma v2.5 report per-word or per-segment confidence?

Streams one cached clean 8 kHz utterance (benchmark/.cache/*.clean8k.pcm) to Prisma and logs
every raw ``transcript`` event in full (via the client's DEBUG log), so the frame's complete
field list can be read off. One live STT call; no Timbre call.

    python scripts/probe_prisma_confidence.py [utterance_id]
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from kadal_kural.config import AppSettings  # noqa: E402
from kadal_kural.infrastructure.gnani_client import GnaniArthaSpeechClient  # noqa: E402

DEFAULT_UTTERANCE = "single_01"
TAIL_SILENCE_BYTES = 8000 * 2  # 1 s of 8 kHz int16 digital silence


async def _on_segment(text: str, latency_ms: float) -> None:
    """Prints the parsed segment the production callback receives."""
    print(f"PARSED segment: text={text!r} latency_ms={latency_ms}")


async def main(utterance_id: str) -> None:
    """Streams the cached clean audio for ``utterance_id`` and prints raw events."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout)
    logging.getLogger("kadal_kural.infrastructure.gnani_client").setLevel(logging.DEBUG)
    matches = sorted((_REPO_ROOT / "benchmark" / ".cache").glob(f"{utterance_id}.*.clean8k.pcm"))
    if not matches:
        raise SystemExit(f"no cached clean audio for {utterance_id}")
    pcm = matches[0].read_bytes() + bytes(TAIL_SILENCE_BYTES)
    client = GnaniArthaSpeechClient(AppSettings())
    await client.stream_pcm_to_prisma_v25(pcm, _on_segment, sample_rate=8000, append_trailing_silence=False)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_UTTERANCE))
