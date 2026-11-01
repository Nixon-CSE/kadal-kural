"""
Live end-to-end measurement of the /ws/live-audio path, reading to_first_audio_ms from the
gateway's own JSON timing lines.

Starts the real gateway on a private port with a temporary ledger, then for each sampled
corpus utterance acts as the browser would: opens the WebSocket, streams the cached clean
speech in paced 1,024-byte frames, keeps streaming digital silence like an open mic, and
stops once the credit decision arrives. Real Prisma and Timbre calls.

    python scripts/measure_live_path.py --label before --utterances 12

Appends one JSON object per utterance to --out and logs P50/P95 for the run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import uvicorn
import websockets

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT / "src"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from benchmark.corpus import build_corpus  # noqa: E402
from benchmark.run_eval import LEAD_IN_MS, DiskCache, sample_corpus  # noqa: E402
from kadal_kural.api.main import create_app  # noqa: E402
from kadal_kural.config import (  # noqa: E402
    LIVE_MIC_SAMPLE_RATE,
    PCM_FRAME_BYTES,
    TIMING_LOGGER_NAME,
    AppSettings,
    frame_pace_seconds,
)

logger = logging.getLogger("live_path")
PORT = 8765
DECISION_TIMEOUT_SEC = 45.0
P50, P95 = 50.0, 95.0


class _TimingLines(logging.Handler):
    """Collects the gateway's JSON timing lines."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


async def stream_one(pcm: bytes) -> Dict[str, object]:
    """Streams one utterance like the browser mic; returns the decision message."""
    pace = frame_pace_seconds(LIVE_MIC_SAMPLE_RATE)
    frames = [pcm[i : i + PCM_FRAME_BYTES].ljust(PCM_FRAME_BYTES, b"\x00") for i in range(0, len(pcm), PCM_FRAME_BYTES)]
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws/live-audio", max_size=None) as ws:
        while json.loads(await ws.recv()).get("type") != "prisma_connected":
            pass

        async def _send() -> None:
            index = 0
            while True:
                await ws.send(frames[index] if index < len(frames) else bytes(PCM_FRAME_BYTES))
                index += 1
                await asyncio.sleep(pace)

        sender = asyncio.create_task(_send())
        try:
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=DECISION_TIMEOUT_SEC))
                if msg.get("type") == "error":
                    raise RuntimeError(str(msg.get("message")))
                if msg.get("type") == "credit_decisions":
                    return dict(msg)
        finally:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)


async def main_async(args: argparse.Namespace) -> int:
    logging.getLogger(TIMING_LOGGER_NAME).propagate = False
    capture = _TimingLines()
    logging.getLogger(TIMING_LOGGER_NAME).addHandler(capture)
    with tempfile.TemporaryDirectory() as tmp:
        settings = AppSettings(db_path=str(Path(tmp) / "live_path.db"))
        tail_ms = settings.min_silence_ms + settings.stt_trailing_silence_margin_ms
        cache = DiskCache(args.cache_dir, settings, LEAD_IN_MS, tail_ms)
        server = uvicorn.Server(uvicorn.Config(create_app(settings), port=PORT, log_level="warning"))
        serving = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.05)
        firsts: List[float] = []
        try:
            for utterance in sample_corpus(build_corpus(), args.utterances):
                clean = cache.load_clean(utterance)
                if clean is None:
                    raise SystemExit(f"no cached clean audio for {utterance.utterance_id}")
                pcm = np.zeros(LIVE_MIC_SAMPLE_RATE * LEAD_IN_MS // 1000, dtype=np.int16).tobytes() + clean.tobytes()
                before = len(capture.lines)
                record: Dict[str, object] = {"label": args.label, "utterance_id": utterance.utterance_id}
                try:
                    message = await stream_one(pcm)
                    record["decisions"] = [d["status"] for d in message["decisions"]]  # type: ignore[attr-defined]
                except Exception as exc:  # recorded, not raised: one failure must not end the run
                    record["error"] = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(args.settle_sec)
                new_lines = capture.lines[before:]
                record["timing"] = json.loads(new_lines[0]) if new_lines else None
                record["timing_lines"] = len(new_lines)
                with args.out.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                timing = record["timing"]
                first = timing.get("to_first_audio_ms") if isinstance(timing, dict) else None
                if first is not None:
                    firsts.append(float(first))
                logger.info("%s: to_first_audio_ms=%s %s", utterance.utterance_id, first, record.get("error", ""))
        finally:
            server.should_exit = True
            await serving
    if not firsts:
        logger.error("no utterance produced a timing line with first audio")
        return 1
    logger.info(
        "%s: n=%d to_first_audio_ms P50 %.0f, P95 %.0f, min %.0f, max %.0f", args.label, len(firsts),
        float(np.percentile(firsts, P50)), float(np.percentile(firsts, P95)), min(firsts), max(firsts),
    )
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Live /ws/live-audio to_first_audio_ms from the JSON timing lines")
    p.add_argument("--label", required=True)
    p.add_argument("--utterances", type=int, default=12)
    p.add_argument("--settle-sec", type=float, default=0.3)
    p.add_argument("--cache-dir", type=Path, default=_REPO_ROOT / "benchmark" / ".cache")
    p.add_argument("--out", type=Path, default=_REPO_ROOT / "benchmark" / "live_path_timing.jsonl")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
    return asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
