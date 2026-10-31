"""
Live diagnosis of Prisma v2.5 STT latency spikes.

Replays benchmark items' exact audio (the cached clean Timbre speech, the same noise seed,
lead-in and noisy/silent tail that run_eval.py streams) through the production client and
records client-side timing for every stream: retry attempts, connect, audio send, drain,
and when each Prisma event arrived relative to the last audio frame sent, next to the
latency Prisma itself reports. ``--extra-silence-ms`` appends digital silence after the
benchmark tail, to test whether more trailing audio lets Prisma close an utterance sooner.

    python scripts/diagnose_stt_latency.py --items single_04:clean,multi_07:ice_crusher:5 \\
        --repeats 3 --out benchmark/stt_latency_diagnosis.jsonl

Writes one JSON object per stream to --out (appending) and logs a one-line summary each.
Every stream is one live Prisma call; no Timbre calls (clean audio must already be cached).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT / "src"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from benchmark.corpus import BenchmarkUtterance, build_corpus  # noqa: E402
from benchmark.run_eval import (  # noqa: E402
    CLEAN_PROFILE,
    LEAD_IN_MS,
    STT_SAMPLE_RATE,
    DiskCache,
    _stable_seed,
    build_stt_audio,
)
from kadal_kural.config import PCM_SAMPLE_WIDTH_BYTES, AppSettings  # noqa: E402
from kadal_kural.infrastructure.gnani_client import GnaniArthaSpeechClient  # noqa: E402

logger = logging.getLogger("stt_diagnosis")
MS_PER_SECOND = 1000


def parse_item(spec: str) -> Tuple[str, str, Optional[float]]:
    """'single_04:clean' or 'multi_07:ice_crusher:5' -> (utterance id, profile, snr or None)."""
    parts = spec.split(":")
    if len(parts) == 2 and parts[1] == CLEAN_PROFILE:
        return parts[0], CLEAN_PROFILE, None
    if len(parts) == 3:
        return parts[0], parts[1], float(parts[2])
    raise ValueError(f"bad item {spec!r}; use utterance:clean or utterance:profile:snr")


async def diagnose_one(
    settings: AppSettings,
    utterance: BenchmarkUtterance,
    clean_8k: bytes,
    profile: str,
    snr_db: Optional[float],
    extra_silence_ms: int,
) -> Dict[str, object]:
    """Streams one item once and returns its timing record."""
    tail_ms = settings.min_silence_ms + settings.stt_trailing_silence_margin_ms
    pcm, _ = build_stt_audio(
        np.frombuffer(clean_8k, dtype=np.int16),
        profile,
        snr_db,
        seed=_stable_seed(utterance.utterance_id, profile),
        lead_ms=LEAD_IN_MS,
        tail_ms=tail_ms,
    )
    pcm += bytes(STT_SAMPLE_RATE * PCM_SAMPLE_WIDTH_BYTES * extra_silence_ms // MS_PER_SECOND)
    segments: List[str] = []

    async def _on_segment(text: str, latency_ms: float) -> None:
        if text.strip():
            segments.append(text.strip())

    started_epoch = time.time()
    t0 = time.perf_counter()
    record: Dict[str, object] = {
        "utterance_id": utterance.utterance_id,
        "profile": profile,
        "snr_db": "clean" if snr_db is None else snr_db,
        "extra_silence_ms": extra_silence_ms,
        "audio_ms": round(len(pcm) / (STT_SAMPLE_RATE * PCM_SAMPLE_WIDTH_BYTES) * MS_PER_SECOND, 1),
        "started_epoch": round(started_epoch, 3),
    }
    try:
        telemetry = await GnaniArthaSpeechClient(settings).stream_pcm_to_prisma_v25(
            pcm, _on_segment, sample_rate=STT_SAMPLE_RATE, append_trailing_silence=False
        )
    except Exception as exc:  # recorded, not raised: one failed stream must not end the run
        record["error"] = f"{type(exc).__name__}: {exc}"
    else:
        record.update(asdict(telemetry))
        record["final_transcript_after_audio_ms"] = telemetry.final_transcript_after_audio_ms
        record["reported_latency_ms"] = [
            e.reported_latency_ms for e in telemetry.events if e.event_type == "transcript"
        ]
    record["wall_ms"] = round((time.perf_counter() - t0) * MS_PER_SECOND, 1)
    record["transcript"] = " ".join(segments)
    return record


async def main_async(args: argparse.Namespace) -> int:
    settings = AppSettings()
    corpus = {u.utterance_id: u for u in build_corpus()}
    tail_ms = settings.min_silence_ms + settings.stt_trailing_silence_margin_ms
    cache = DiskCache(args.cache_dir, settings, LEAD_IN_MS, tail_ms)
    items = [parse_item(s) for s in args.items.split(",") if s.strip()]
    clean: Dict[str, bytes] = {}
    for utt_id, _, _ in items:
        audio = cache.load_clean(corpus[utt_id])
        if audio is None:
            logger.error("no cached clean audio for %s; run run_eval.py for it first", utt_id)
            return 2
        clean[utt_id] = audio.tobytes()

    sem = asyncio.Semaphore(args.concurrency)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    async def _run(utt_id: str, profile: str, snr: Optional[float], repeat: int) -> None:
        async with sem:
            record = await diagnose_one(settings, corpus[utt_id], clean[utt_id], profile, snr, args.extra_silence_ms)
        record["repeat"] = repeat
        record["label"] = args.label
        with args.out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(
            "%s %s/%s rep %d: attempts=%s reported=%s final_after_audio=%s drain=%s wall=%s %s",
            utt_id, profile, record["snr_db"], repeat, record.get("attempts"), record.get("reported_latency_ms"),
            record.get("final_transcript_after_audio_ms"), record.get("drain_ms"), record["wall_ms"],
            record.get("error", ""),
        )

    jobs = [(u, p, s, r) for r in range(1, args.repeats + 1) for (u, p, s) in items]
    await asyncio.gather(*(_run(*job) for job in jobs))
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Diagnose Prisma STT latency spikes with client-side timing")
    p.add_argument("--items", required=True, help="comma list of utterance:clean or utterance:profile:snr")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--extra-silence-ms", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--label", default="baseline", help="free-text tag stored on every record")
    p.add_argument("--cache-dir", type=Path, default=_REPO_ROOT / "benchmark" / ".cache")
    p.add_argument("--out", type=Path, default=_REPO_ROOT / "benchmark" / "stt_latency_diagnosis.jsonl")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
    return asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
