"""
Live false-detection probe for Prisma's VAD threshold: streams audio containing no speech and
counts what Prisma detects in it.

Each stream is the noise-only signal of a benchmark item at 5 dB (the mix minus its speech, so
the same noise realisation and level the sweep uses). Digital silence is the control.

    python scripts/measure_vad_false_detections.py --thresholds 0.5,0.6,0.7,0.78

Appends one JSON object per stream to --out and logs a per-threshold summary. Retries are off,
so a speech_start that never gets a transcript is recorded as such rather than re-streamed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT / "src"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from benchmark.corpus import build_corpus  # noqa: E402
from benchmark.noise_profiles import NOISE_PROFILE_NAMES  # noqa: E402
from benchmark.run_eval import (  # noqa: E402
    LEAD_IN_MS,
    STT_SAMPLE_RATE,
    DiskCache,
    _stable_seed,
    build_stt_audio,
    sample_corpus,
)
from kadal_kural.config import AppSettings  # noqa: E402
from kadal_kural.infrastructure.gnani_client import GnaniArthaSpeechClient, GnaniProtocolError  # noqa: E402

logger = logging.getLogger("vad_false_detections")
SNR_DB = 5.0
SILENCE = "silence"


def noise_only_pcm(clean: np.ndarray, profile: str, seed: int, tail_ms: int) -> bytes:  # type: ignore[type-arg]
    """The benchmark's 5 dB mix for ``clean`` with the speech subtracted back out."""
    pcm, _ = build_stt_audio(clean, profile, SNR_DB, seed=seed, lead_ms=LEAD_IN_MS, tail_ms=tail_ms)
    mix = np.frombuffer(pcm, dtype=np.int16).astype(np.int32)
    lead_n = STT_SAMPLE_RATE * LEAD_IN_MS // 1000
    mix[lead_n : lead_n + len(clean)] -= clean.astype(np.int32)
    return np.clip(mix, -32768, 32767).astype(np.int16).tobytes()


async def one_stream(threshold: float, pcm: bytes) -> Dict[str, object]:
    settings = AppSettings(vad_threshold=threshold, gnani_max_attempts=1)
    texts: List[str] = []

    async def _on_segment(text: str, latency_ms: float) -> None:
        if text.strip():
            texts.append(text.strip())

    try:
        telemetry = await GnaniArthaSpeechClient(settings).stream_pcm_to_prisma_v25(
            pcm, _on_segment, sample_rate=STT_SAMPLE_RATE, append_trailing_silence=False, enable_boosting=False
        )
    except asyncio.TimeoutError:  # a speech_start Prisma never transcribed
        return {"speech_starts": None, "open_without_transcript": True, "texts": texts}
    except GnaniProtocolError as exc:  # a server fault says nothing about the threshold
        return {"speech_starts": None, "open_without_transcript": False, "texts": texts, "error": str(exc)}
    starts = sum(e.event_type == "speech_start" for e in telemetry.events)
    return {"speech_starts": starts, "open_without_transcript": False, "texts": texts}


async def main_async(args: argparse.Namespace) -> int:
    settings = AppSettings()
    tail_ms = settings.min_silence_ms + settings.stt_trailing_silence_margin_ms
    cache = DiskCache(args.cache_dir, settings, LEAD_IN_MS, tail_ms)
    jobs: List[Tuple[float, str, str, bytes]] = []
    for utterance in sample_corpus(build_corpus(), args.items_per_profile):
        clean = cache.load_clean(utterance)
        if clean is None:
            raise SystemExit(f"no cached clean audio for {utterance.utterance_id}")
        for threshold in args.thresholds:
            jobs.append((threshold, SILENCE, utterance.utterance_id, bytes(len(clean) * 2)))
            for profile in NOISE_PROFILE_NAMES:
                seed = _stable_seed(utterance.utterance_id, profile)
                jobs.append((threshold, profile, utterance.utterance_id, noise_only_pcm(clean, profile, seed, tail_ms)))

    sem = asyncio.Semaphore(args.concurrency)
    summary: Dict[float, "Counter[str]"] = {t: Counter() for t in args.thresholds}

    async def _run(threshold: float, profile: str, utterance_id: str, pcm: bytes) -> None:
        async with sem:
            result = await one_stream(threshold, pcm)
        record = {"vad_threshold": threshold, "profile": profile, "utterance_id": utterance_id, **result}
        with args.out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        tally = summary[threshold]
        if "error" in result:
            tally["server_errors"] += 1
            return
        tally["streams"] += 1
        tally["detected"] += bool(result["open_without_transcript"] or result["speech_starts"])
        tally["false_transcripts"] += bool(result["texts"])

    await asyncio.gather(*(_run(*job) for job in jobs))
    for threshold in args.thresholds:
        logger.info("vad_threshold %.2f: %s", threshold, dict(summary[threshold]))
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Count Prisma detections on speech-free audio per VAD threshold")
    p.add_argument("--thresholds", type=lambda s: [float(v) for v in s.split(",")], default=[0.5, 0.6, 0.7, 0.78])
    p.add_argument("--items-per-profile", type=int, default=6)
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--cache-dir", type=Path, default=_REPO_ROOT / "benchmark" / ".cache")
    p.add_argument("--out", type=Path, default=_REPO_ROOT / "benchmark" / "vad_sweep" / "false_detections.jsonl")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
    args = parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
