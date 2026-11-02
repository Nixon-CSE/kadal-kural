"""
Replays a slice of a raw mic capture (KADAL_MIC_CAPTURE_DIR) through live Prisma at several VAD
thresholds, to test whether a clipped utterance's first syllable comes back at a lower one.

    python scripts/replay_mic_capture.py mic_captures/mic_20261102_101500.wav \\
        --start-ms 12000 --end-ms 17500 --thresholds 0.78,0.6,0.5 --repeats 2

The sidecar JSON next to the WAV lists where each Prisma segment arrived in the audio; pick a
window that starts a little before the clipped utterance (Prisma needs some lead-in) and ends
after it. Logs one line per stream; one live Prisma call each.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import wave
from pathlib import Path
from typing import List, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from kadal_kural.config import PCM_SAMPLE_WIDTH_BYTES, AppSettings  # noqa: E402
from kadal_kural.infrastructure.gnani_client import GnaniArthaSpeechClient  # noqa: E402

logger = logging.getLogger("replay_mic_capture")
MS_PER_SECOND = 1000


def read_slice(path: Path, start_ms: int, end_ms: Optional[int]) -> tuple[bytes, int]:
    """PCM between start_ms and end_ms (end of file if None), and its sample rate."""
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        if wf.getnchannels() != 1 or wf.getsampwidth() != PCM_SAMPLE_WIDTH_BYTES:
            raise SystemExit("expected a mono 16-bit capture")
        pcm = wf.readframes(wf.getnframes())
    bytes_per_ms = rate * PCM_SAMPLE_WIDTH_BYTES // MS_PER_SECOND
    end = len(pcm) if end_ms is None else end_ms * bytes_per_ms
    return pcm[start_ms * bytes_per_ms : end], rate


async def main_async(args: argparse.Namespace) -> int:
    pcm, rate = read_slice(args.wav, args.start_ms, args.end_ms)
    logger.info("%s: %.0f ms of audio at %d Hz", args.wav.name, len(pcm) / (rate * PCM_SAMPLE_WIDTH_BYTES) * 1000, rate)
    for threshold in args.thresholds:
        for repeat in range(1, args.repeats + 1):
            segments: List[str] = []

            async def _on_segment(text: str, latency_ms: float) -> None:
                if text.strip():
                    segments.append(text.strip())

            try:
                await GnaniArthaSpeechClient(AppSettings(vad_threshold=threshold)).stream_pcm_to_prisma_v25(
                    pcm, _on_segment, sample_rate=rate
                )
                outcome = " | ".join(segments) or "(no transcript)"
            except Exception as exc:  # recorded, not raised: compare every threshold even if one fails
                outcome = f"failed: {type(exc).__name__}: {exc}"
            logger.info("vad_threshold %.2f rep %d: %s", threshold, repeat, outcome)
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay a raw mic capture through Prisma at several VAD thresholds")
    p.add_argument("wav", type=Path)
    p.add_argument("--start-ms", type=int, default=0)
    p.add_argument("--end-ms", type=int)
    p.add_argument("--thresholds", type=lambda s: [float(v) for v in s.split(",")], default=[0.78, 0.6, 0.5])
    p.add_argument("--repeats", type=int, default=2)
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
    return asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
