"""
Live barge-in stop-time trials against Gnani Timbre v2.5.

Each trial starts a real synthesis of the firewall's credit-hold alert (the reply a trader
is most likely to interrupt), waits for the first audio byte, sleeps a seeded-random delay
inside the stream's measured streaming window, calls trigger_barge_in_abort(), and records
SynthesisTelemetry.abort_to_close_ms: abort triggered -> Timbre socket closed. A trial in
which Timbre finished streaming before the trigger fired is recorded as
``completed_before_trigger`` and does not count toward --trials.

    python scripts/measure_barge_in.py --trials 24 --label before_fix

Appends one JSON object per trial to --out and logs the P50/P95 of the counted trials.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from kadal_kural.config import AppSettings  # noqa: E402
from kadal_kural.domain.matcher import BilingualCatalogMatcher  # noqa: E402
from kadal_kural.domain.models import LedgerEventStatus  # noqa: E402
from kadal_kural.domain.service import PreDispatchCreditFirewallService  # noqa: E402
from kadal_kural.infrastructure.gnani_client import GnaniArthaSpeechClient  # noqa: E402
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository  # noqa: E402

logger = logging.getLogger("barge_in_trials")
HOLD_TRANSCRIPT = "செந்தில் சீஃபுட்ஸ்க்கு 40 கிலோ எக்ஸ்போர்ட் வஞ்சரம் எழுநூற்றி 40 ரேட்டு"
CALIBRATION_RUNS = 2
WINDOW_FRACTION = 0.9  # trigger inside the first 90% of the streaming window
MAX_ATTEMPTS_PER_TRIAL = 3
MS_PER_SECOND = 1000.0
P50, P95 = 50.0, 95.0


def credit_hold_alert_text(settings: AppSettings) -> str:
    """The real Tamil alert the firewall speaks for the playground credit hold."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = settings.model_copy(update={"db_path": str(Path(tmp) / "alert.db")})
        matcher = BilingualCatalogMatcher(cfg.catalog_path)
        repo = AppendOnlyLedgerRepository(cfg.db_path, list(matcher.buyers.values()))
        (decision,) = PreDispatchCreditFirewallService(cfg, matcher, repo).evaluate_utterance(HOLD_TRANSCRIPT)
    if decision.status != LedgerEventStatus.CREDIT_HOLD_BREACH:
        raise RuntimeError(f"expected a credit hold, got {decision.status}")
    return decision.tts_response_tamil


async def streaming_window_ms(settings: AppSettings, text: str) -> float:
    """Median first-audio-byte -> last-chunk time of uninterrupted syntheses."""
    windows: List[float] = []
    for _ in range(CALIBRATION_RUNS):
        telemetry = await GnaniArthaSpeechClient(settings).synthesize_timbre_v25(text)
        windows.append(telemetry.total_synthesis_ms - telemetry.ttfb_ms)
    return statistics.median(windows)


async def one_trial(settings: AppSettings, text: str, delay_ms: float) -> Dict[str, object]:
    """Triggers barge-in ``delay_ms`` after the first audio byte and reports what happened."""
    client = GnaniArthaSpeechClient(settings)
    first_audio = asyncio.Event()
    started_epoch = time.time()
    task = asyncio.create_task(client.synthesize_timbre_v25(text, on_first_audio=first_audio.set))
    record: Dict[str, object] = {"delay_ms": round(delay_ms, 1), "started_epoch": round(started_epoch, 3)}
    try:
        await asyncio.wait_for(first_audio.wait(), timeout=settings.gnani_read_timeout_sec)
        await asyncio.sleep(delay_ms / MS_PER_SECOND)
        if task.done():
            record["completed_before_trigger"] = True
        else:
            client.trigger_barge_in_abort()
        telemetry = await task
    except Exception as exc:
        task.cancel()
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record
    record.update(
        ttfb_ms=telemetry.ttfb_ms,
        total_synthesis_ms=telemetry.total_synthesis_ms,
        was_interrupted=telemetry.was_interrupted,
        abort_to_close_ms=telemetry.abort_to_close_ms,
    )
    record.setdefault("completed_before_trigger", not telemetry.was_interrupted)
    return record


async def main_async(args: argparse.Namespace) -> int:
    settings = AppSettings()
    text = credit_hold_alert_text(settings)
    window_ms = await streaming_window_ms(settings, text)
    logger.info("alert is %d characters; streaming window %.0f ms (median of %d)", len(text), window_ms, CALIBRATION_RUNS)
    rng = random.Random(args.seed)
    counted: List[float] = []
    ttfbs: List[float] = []
    args.out.parent.mkdir(parents=True, exist_ok=True)
    trial = 0
    while len(counted) < args.trials and trial < args.trials * MAX_ATTEMPTS_PER_TRIAL:
        trial += 1
        delay_ms = rng.uniform(0.0, WINDOW_FRACTION * window_ms)
        record = await one_trial(settings, text, delay_ms)
        record.update(label=args.label, trial=trial, seed=args.seed, streaming_window_ms=round(window_ms, 1))
        with args.out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        if record.get("ttfb_ms"):
            ttfbs.append(float(str(record["ttfb_ms"])))
        stop_ms = record.get("abort_to_close_ms")
        if stop_ms is not None and not record.get("completed_before_trigger"):
            counted.append(float(str(stop_ms)))
        logger.info("trial %d: delay %.0f ms -> %s", trial, delay_ms, {k: record.get(k) for k in (
            "abort_to_close_ms", "completed_before_trigger", "error")})
    if not counted:
        logger.error("no counted trials")
        return 1
    logger.info(
        "%s: %d counted trials, abort->close P50 %.1f ms, P95 %.1f ms, max %.1f ms; TTFB P50 %.0f ms, P95 %.0f ms",
        args.label, len(counted), float(np.percentile(counted, P50)), float(np.percentile(counted, P95)),
        max(counted), float(np.percentile(ttfbs, P50)), float(np.percentile(ttfbs, P95)),
    )
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Live Timbre barge-in stop-time trials")
    p.add_argument("--trials", type=int, default=24, help="counted trials wanted (at least 20 for the report)")
    p.add_argument("--label", required=True)
    p.add_argument("--seed", type=int, default=20261031)
    p.add_argument("--out", type=Path, default=_REPO_ROOT / "benchmark" / "barge_in_trials.jsonl")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
    return asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
