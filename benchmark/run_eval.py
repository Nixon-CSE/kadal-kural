"""
Live Noise & Silent-Error Benchmark orchestrator.

For every (utterance x noise profile x SNR) item this script runs the real pipeline:

    corpus text --Timbre v2.5 TTS--> clean speech --resample to 8 kHz--> mix synthetic noise at the
    target RMS SNR (noise also fills a lead-in and a tail, so the VAD must close the utterance
    *through* the noise) --1,024-byte paced frames--> Prisma v2.5 STT --> normalizer -> matcher ->
    confidence-gated credit firewall (fresh seeded ledger per utterance).

Timbre is only the *speaker* here (a repeatable stand-in for a person); the system under test is
STT -> firewall. Each clean utterance is synthesized once and cached; STT transcripts are cached
per item, so re-running (or ``--analyze-only``) costs no API calls. Noise beds are synthetic (see
benchmark/noise_profiles.py) and the report says so.

Usage (needs a live KADAL_GNANI_API_KEY in .env for anything not already cached):

    python benchmark/run_eval.py --limit 4 --snrs 10 --profiles harbour    # cheap smoke test
    python benchmark/run_eval.py --yes                                     # full sweep
    python benchmark/run_eval.py --analyze-only                            # re-score from cache
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import logging
import sys
import wave
import zlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple

import numpy as np
import numpy.typing as npt

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT / "src"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from benchmark.corpus import BenchmarkUtterance, build_corpus  # noqa: E402
from benchmark.noise_profiles import (  # noqa: E402
    NOISE_PROFILE_NAMES,
    STANDARD_SNR_LEVELS_DB,
    NoiseProfileName,
    generate_noise_bed,
    mix_pcm_at_snr,
    rms,
)
from benchmark.scoring import ENTITY_FIELDS, Scorer, UtteranceScore  # noqa: E402
from kadal_kural.config import AppSettings  # noqa: E402
from kadal_kural.infrastructure.gnani_client import (  # noqa: E402
    GnaniArthaSpeechClient,
    GnaniConfigurationError,
)

logger = logging.getLogger("benchmark")

CLEAN_PROFILE = "clean"
STT_SAMPLE_RATE = 8000  # production microphone/telephony rate (config.LIVE_MIC_SAMPLE_RATE)
TTS_SAMPLE_RATE = 16000  # rate proven live in the Task 1 round-trip test
LEAD_IN_MS = 300
RESAMPLE_TAPS = 63
RESAMPLE_CUTOFF_HZ = 3600.0
INT16_MIN, INT16_MAX = -32768, 32767
DEFAULT_CONCURRENCY = 3
LIVE_CALLS_NEEDING_CONFIRMATION = 100
BASE_SEED = 20261026
THRESHOLD_GRID: Tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.82, 0.9, 0.95)
P50, P95 = 50.0, 95.0
FAILURE_EXAMPLES = 3
Pcm = npt.NDArray[np.int16]


# ------------------------------------------------------------------------------ audio helpers


def resample_16k_to_8k(samples: Pcm) -> Pcm:
    """Windowed-sinc low-pass at 3.6 kHz, then 2:1 decimation (pure numpy; audioop is gone in 3.13)."""
    n = np.arange(RESAMPLE_TAPS) - (RESAMPLE_TAPS - 1) / 2.0
    taps = np.sinc(2.0 * RESAMPLE_CUTOFF_HZ / TTS_SAMPLE_RATE * n) * np.hamming(RESAMPLE_TAPS)
    taps /= taps.sum()
    filtered = np.convolve(samples.astype(np.float64), taps, mode="same")[::2]
    out: Pcm = np.clip(np.round(filtered), INT16_MIN, INT16_MAX).astype(np.int16)
    return out


def wav_bytes_to_8k(wav_bytes: bytes) -> Pcm:
    """Decodes Timbre's mono 16-bit WAV and returns 8 kHz int16 samples."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        rate = wf.getframerate()
        samples = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    if rate == STT_SAMPLE_RATE:
        return samples
    if rate == TTS_SAMPLE_RATE:
        return resample_16k_to_8k(samples)
    raise ValueError(f"unexpected Timbre sample rate {rate}")


def _stable_seed(utterance_id: str, profile: str) -> int:
    """Same noise realisation for an (utterance, profile) pair across SNR levels (paired design)."""
    return zlib.crc32(f"{BASE_SEED}:{utterance_id}:{profile}".encode()) & 0x7FFFFFFF


def build_stt_audio(
    clean_8k: Pcm,
    profile: str,
    snr_db: Optional[float],
    *,
    seed: int,
    lead_ms: int,
    tail_ms: int,
) -> Tuple[bytes, Optional[float]]:
    """
    Returns (PCM bytes, achieved speech-segment SNR dB). The speech is mixed at ``snr_db`` using the
    RMS definition; the lead-in and tail carry noise at the *same absolute level* (zeros for the
    clean baseline), so end-of-speech detection is also tested under noise.
    """
    lead_n = STT_SAMPLE_RATE * lead_ms // 1000
    tail_n = STT_SAMPLE_RATE * tail_ms // 1000
    if profile == CLEAN_PROFILE or snr_db is None:
        speech: Pcm = clean_8k
        lead: Pcm = np.zeros(lead_n, dtype=np.int16)
        tail: Pcm = np.zeros(tail_n, dtype=np.int16)
        achieved: Optional[float] = None
    else:
        name: NoiseProfileName = profile  # type: ignore[assignment]
        mix = mix_pcm_at_snr(clean_8k, name, snr_db, sample_rate=STT_SAMPLE_RATE, seed=seed)
        speech = mix.mixed_pcm_int16
        level = rms(speech.astype(np.float64) - clean_8k.astype(np.float64))

        def _noise(n: int, offset: int) -> Pcm:
            bed = generate_noise_bed(name, n, STT_SAMPLE_RATE, seed=seed + offset) * level
            noise: Pcm = np.clip(np.round(bed), INT16_MIN, INT16_MAX).astype(np.int16)
            return noise

        lead, tail = _noise(lead_n, 2), _noise(tail_n, 1)
        achieved = mix.achieved_snr_db
    return np.concatenate([lead, speech, tail]).astype(np.int16).tobytes(), achieved


# ------------------------------------------------------------------------------ speech backend


@dataclass(frozen=True)
class WorkItem:
    """One (utterance, profile, SNR) benchmark cell. ``snr_db`` is None for the clean baseline."""

    utterance: BenchmarkUtterance
    profile: str
    snr_db: Optional[float]

    @property
    def snr_label(self) -> str:
        return "clean" if self.snr_db is None else f"{self.snr_db:g}"


@dataclass(frozen=True)
class TranscriptOutcome:
    """STT result for one item (or the reason it failed)."""

    transcript: str
    stt_latency_ms: float
    segment_count: int
    error: Optional[str] = None


class SpeechBackend(Protocol):
    """The two live services the benchmark needs; tests substitute a fake."""

    async def synthesize_clean_8k(self, text: str) -> Pcm: ...

    async def transcribe(self, pcm_8k: bytes) -> TranscriptOutcome: ...


class LiveGnaniBackend:
    """Real Timbre v2.5 + Prisma v2.5 over the production client (retries/timeouts included)."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def synthesize_clean_8k(self, text: str) -> Pcm:
        """Synthesizes ``text`` with Timbre and returns 8 kHz int16 speech."""
        client = GnaniArthaSpeechClient(self._settings)  # one per call: abort events are per-client
        telemetry = await client.synthesize_timbre_v25(text, sample_rate=TTS_SAMPLE_RATE)
        return wav_bytes_to_8k(telemetry.audio_wav_bytes)

    async def transcribe(self, pcm_8k: bytes) -> TranscriptOutcome:
        """Streams ``pcm_8k`` to Prisma; segments are merged like the production /upload-wav path."""
        client = GnaniArthaSpeechClient(self._settings)
        segments: List[str] = []
        latencies: List[float] = []

        async def _on_segment(text: str, latency_ms: float) -> None:
            if text.strip():
                segments.append(text.strip())
                latencies.append(latency_ms)

        await client.stream_pcm_to_prisma_v25(
            pcm_8k,
            _on_segment,
            sample_rate=STT_SAMPLE_RATE,
            append_trailing_silence=False,  # the benchmark supplies a noisy tail itself
        )
        mean_latency = sum(latencies) / len(latencies) if latencies else 0.0
        return TranscriptOutcome(" ".join(segments), round(mean_latency, 1), len(segments))


# ------------------------------------------------------------------------------ cache


class DiskCache:
    """Caches clean TTS audio per utterance and STT transcripts per item, keyed by run parameters."""

    def __init__(self, root: Path, settings: AppSettings, lead_ms: int, tail_ms: int) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        tts_key = f"{settings.timbre_default_voice}|{TTS_SAMPLE_RATE}"
        stt_key = (
            f"{tts_key}|{BASE_SEED}|{lead_ms}|{tail_ms}|{settings.vad_threshold}|"
            f"{settings.min_speech_ms}|{settings.min_silence_ms}"
        )
        self._tts_tag = hashlib.sha1(tts_key.encode()).hexdigest()[:8]
        self._stt_tag = hashlib.sha1(stt_key.encode()).hexdigest()[:8]

    def _clean_path(self, utterance_id: str) -> Path:
        return self.root / f"{utterance_id}.{self._tts_tag}.clean8k.pcm"

    def _transcript_path(self, item: WorkItem) -> Path:
        name = f"{item.utterance.utterance_id}__{item.profile}__{item.snr_label}.{self._stt_tag}.json"
        return self.root / name

    def load_clean(self, utterance_id: str) -> Optional[Pcm]:
        path = self._clean_path(utterance_id)
        return np.frombuffer(path.read_bytes(), dtype=np.int16) if path.exists() else None

    def save_clean(self, utterance_id: str, samples: Pcm) -> None:
        self._clean_path(utterance_id).write_bytes(samples.tobytes())

    def load_transcript(self, item: WorkItem) -> Optional[TranscriptOutcome]:
        path = self._transcript_path(item)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return TranscriptOutcome(
            str(data["transcript"]), float(data["stt_latency_ms"]), int(data["segment_count"])
        )

    def save_transcript(self, item: WorkItem, outcome: TranscriptOutcome) -> None:
        self._transcript_path(item).write_text(
            json.dumps(
                {
                    "transcript": outcome.transcript,
                    "stt_latency_ms": outcome.stt_latency_ms,
                    "segment_count": outcome.segment_count,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


# ------------------------------------------------------------------------------ sweep


def build_work_items(
    corpus: Sequence[BenchmarkUtterance],
    profiles: Sequence[str],
    snrs: Sequence[float],
    include_clean: bool,
) -> List[WorkItem]:
    """Cross product of utterances x noise profiles x SNRs, plus one clean baseline per utterance."""
    items = [WorkItem(u, CLEAN_PROFILE, None) for u in corpus] if include_clean else []
    items += [WorkItem(u, p, s) for u in corpus for p in profiles for s in snrs]
    return items


def sample_corpus(corpus: Sequence[BenchmarkUtterance], limit: Optional[int]) -> List[BenchmarkUtterance]:
    """Deterministic evenly-strided sample so a small ``--limit`` still spans every category."""
    if limit is None or limit >= len(corpus):
        return list(corpus)
    stride = len(corpus) / limit
    return [corpus[int(i * stride)] for i in range(limit)]


async def gather_transcripts(
    items: Sequence[WorkItem],
    backend: Optional[SpeechBackend],
    cache: DiskCache,
    settings: AppSettings,
    concurrency: int,
) -> Dict[Tuple[str, str, str], TranscriptOutcome]:
    """Fetches (from cache, else live) a transcript for every item. Failures are recorded, not raised."""
    sem = asyncio.Semaphore(concurrency)
    tail_ms = settings.min_silence_ms + settings.stt_trailing_silence_margin_ms
    results: Dict[Tuple[str, str, str], TranscriptOutcome] = {}
    clean_locks: Dict[str, asyncio.Lock] = {}
    done = 0

    async def _clean_for(utt: BenchmarkUtterance) -> Pcm:
        cached = cache.load_clean(utt.utterance_id)
        if cached is not None:
            return cached
        if backend is None:
            raise LookupError("clean audio not cached (--analyze-only)")
        lock = clean_locks.setdefault(utt.utterance_id, asyncio.Lock())
        async with lock:
            cached = cache.load_clean(utt.utterance_id)
            if cached is None:
                async with sem:
                    cached = await backend.synthesize_clean_8k(utt.spoken_text)
                cache.save_clean(utt.utterance_id, cached)
        return cached

    async def _one(item: WorkItem) -> None:
        nonlocal done
        key = (item.utterance.utterance_id, item.profile, item.snr_label)
        outcome = cache.load_transcript(item)
        if outcome is None and backend is not None:
            try:
                clean = await _clean_for(item.utterance)
                pcm, _ = build_stt_audio(
                    clean,
                    item.profile,
                    item.snr_db,
                    seed=_stable_seed(item.utterance.utterance_id, item.profile),
                    lead_ms=LEAD_IN_MS,
                    tail_ms=tail_ms,
                )
                async with sem:
                    outcome = await backend.transcribe(pcm)
                cache.save_transcript(item, outcome)
            except GnaniConfigurationError:
                raise
            except Exception as exc:  # per-item isolation: one bad call must not sink the sweep
                logger.error("%s failed: %s: %s", key, type(exc).__name__, exc)
                outcome = TranscriptOutcome("", 0.0, 0, error=f"{type(exc).__name__}: {exc}")
        elif outcome is None:
            outcome = TranscriptOutcome("", 0.0, 0, error="not cached (--analyze-only)")
        results[key] = outcome
        done += 1
        if done % 10 == 0 or done == len(items):
            logger.info("progress: %d/%d items", done, len(items))

    await asyncio.gather(*(_one(i) for i in items))
    return results


# ------------------------------------------------------------------------------ rows & aggregation


@dataclass(frozen=True)
class EvalRow:
    """One scored benchmark cell (a CSV row)."""

    item: WorkItem
    outcome: TranscriptOutcome
    score: Optional[UtteranceScore]


def score_rows(
    items: Sequence[WorkItem],
    transcripts: Dict[Tuple[str, str, str], TranscriptOutcome],
    scorer: Scorer,
) -> List[EvalRow]:
    """Runs the scorer over every successfully transcribed item."""
    rows: List[EvalRow] = []
    for item in items:
        outcome = transcripts[(item.utterance.utterance_id, item.profile, item.snr_label)]
        score = (
            None
            if outcome.error
            else scorer.score(item.utterance, outcome.transcript, outcome.stt_latency_ms)
        )
        rows.append(EvalRow(item, outcome, score))
    return rows


CSV_COLUMNS = [
    "utterance_id", "category", "profile", "snr_db", "n_truth_trades", "n_parsed_trades",
    *[f"{f}_correct" for f in ENTITY_FIELDS],
    "wer_raw", "wer_normalized", "stt_latency_ms",
    "gated_booked", "gated_silent_errors", "gated_correct_bookings", "gated_decision_ms",
    "ungated_booked", "ungated_silent_errors", "ungated_correct_bookings", "ungated_decision_ms",
    "error", "spoken_text", "transcript",
]


def write_csv(rows: Sequence[EvalRow], path: Path) -> None:
    """Writes one line per (utterance, profile, SNR) cell."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in rows:
            rec: Dict[str, object] = {
                "utterance_id": r.item.utterance.utterance_id,
                "category": r.item.utterance.category,
                "profile": r.item.profile,
                "snr_db": r.item.snr_label,
                "error": r.outcome.error or "",
                "spoken_text": r.item.utterance.spoken_text,
                "transcript": r.outcome.transcript,
            }
            s = r.score
            if s is not None:
                rec.update(
                    n_truth_trades=s.n_truth_trades,
                    n_parsed_trades=s.n_parsed_trades,
                    wer_raw=round(s.wer_raw, 4),
                    wer_normalized=round(s.wer_normalized, 4),
                    stt_latency_ms=r.outcome.stt_latency_ms,
                    gated_booked=s.gated.booked,
                    gated_silent_errors=s.gated.silent_errors,
                    gated_correct_bookings=s.gated.correct_bookings,
                    gated_decision_ms=s.gated.decision_ms,
                    ungated_booked=s.ungated.booked,
                    ungated_silent_errors=s.ungated.silent_errors,
                    ungated_correct_bookings=s.ungated.correct_bookings,
                    ungated_decision_ms=s.ungated.decision_ms,
                )
                for f in ENTITY_FIELDS:
                    rec[f"{f}_correct"] = s.entity_correct[f]
            writer.writerow(rec)


def percentile(values: Sequence[float], q: float) -> float:
    """Percentile of ``values`` (0.0 for an empty list)."""
    return float(np.percentile(values, q)) if values else 0.0


@dataclass(frozen=True)
class CellSummary:
    """Aggregate metrics for a group of rows (one profile x SNR cell, or a roll-up)."""

    label: str
    n: int
    failed: int
    trades: int
    wer_raw: float
    wer_normalized: float
    entity_accuracy: Dict[str, float]
    stt_p50: float
    stt_p95: float
    decision_p50: float
    decision_p95: float
    booked_gated: int
    errors_gated: int
    booked_ungated: int
    errors_ungated: int

    @property
    def sfer_gated(self) -> float:
        return self.errors_gated / self.trades if self.trades else 0.0

    @property
    def sfer_ungated(self) -> float:
        return self.errors_ungated / self.trades if self.trades else 0.0


def summarize(label: str, rows: Sequence[EvalRow]) -> CellSummary:
    """Aggregates rows: means for WER, pooled counts for accuracy/SFER, percentiles for latency."""
    ok = [r for r in rows if r.score is not None]
    scores = [r.score for r in ok if r.score is not None]
    trades = sum(s.n_truth_trades for s in scores)
    return CellSummary(
        label=label,
        n=len(ok),
        failed=len(rows) - len(ok),
        trades=trades,
        wer_raw=float(np.mean([s.wer_raw for s in scores])) if scores else 0.0,
        wer_normalized=float(np.mean([s.wer_normalized for s in scores])) if scores else 0.0,
        entity_accuracy={
            f: (sum(s.entity_correct[f] for s in scores) / trades if trades else 0.0)
            for f in ENTITY_FIELDS
        },
        stt_p50=percentile([r.outcome.stt_latency_ms for r in ok], P50),
        stt_p95=percentile([r.outcome.stt_latency_ms for r in ok], P95),
        decision_p50=percentile([s.gated.decision_ms for s in scores], P50),
        decision_p95=percentile([s.gated.decision_ms for s in scores], P95),
        booked_gated=sum(s.gated.booked for s in scores),
        errors_gated=sum(s.gated.silent_errors for s in scores),
        booked_ungated=sum(s.ungated.booked for s in scores),
        errors_ungated=sum(s.ungated.silent_errors for s in scores),
    )


def _group(rows: Sequence[EvalRow], keyfn: Callable[[EvalRow], str]) -> Dict[str, List[EvalRow]]:
    out: Dict[str, List[EvalRow]] = {}
    for r in rows:
        out.setdefault(keyfn(r), []).append(r)
    return out


def threshold_sweep(rows: Sequence[EvalRow], scorer: Scorer) -> List[Tuple[float, int, int, int, int]]:
    """For each tau: (tau, booked, silent_errors, correct_bookings, truth_trades) over noisy rows."""
    noisy = [r for r in rows if r.score is not None and r.item.profile != CLEAN_PROFILE]
    out: List[Tuple[float, int, int, int, int]] = []
    for tau in THRESHOLD_GRID:
        fw = scorer.with_threshold(tau)
        booked = errors = correct = trades = 0
        for r in noisy:
            o = fw.evaluate(r.outcome.transcript, r.item.utterance.ground_truth_trades, 0.0)
            booked += o.booked
            errors += o.silent_errors
            correct += o.correct_bookings
            trades += len(r.item.utterance.ground_truth_trades)
        out.append((tau, booked, errors, correct, trades))
    return out


def _pct(x: float) -> str:
    return f"{100.0 * x:.1f}%"


def render_report(
    rows: Sequence[EvalRow],
    sweep: Sequence[Tuple[float, int, int, int, int]],
    settings: AppSettings,
    meta: Dict[str, str],
) -> str:
    """Builds benchmark/REPORT.md from scored rows."""
    cells: List[CellSummary] = []
    by_cell = _group(rows, lambda r: f"{r.item.profile}|{r.item.snr_label}")
    order = [CLEAN_PROFILE] + list(NOISE_PROFILE_NAMES)
    snr_order = [f"{s:g}" for s in sorted({r.item.snr_db for r in rows if r.item.snr_db}, reverse=True)]
    for prof in order:
        for snr in (["clean"] if prof == CLEAN_PROFILE else snr_order):
            group = by_cell.get(f"{prof}|{snr}")
            if group:
                cells.append(summarize("clean (no noise)" if prof == CLEAN_PROFILE else f"{prof} @ {snr} dB", group))
    by_snr = _group([r for r in rows if r.item.profile != CLEAN_PROFILE], lambda r: r.item.snr_label)
    rollups = [summarize(f"all profiles @ {s} dB", by_snr[s]) for s in snr_order if s in by_snr]
    noisy_all = summarize("**all noisy cells**", [r for r in rows if r.item.profile != CLEAN_PROFILE])

    head = ("| Condition | n | WER (norm.) | WER (raw) | buyer | SKU | qty | unit | rate | STT P50 / P95 ms "
            "| firewall P50 / P95 ms | SFER gate ON | SFER gate OFF |")
    rule = "|" + "---|" * 13

    def line(c: CellSummary) -> str:
        e = c.entity_accuracy
        return (
            f"| {c.label} | {c.n}{f' (+{c.failed} failed)' if c.failed else ''} | {_pct(c.wer_normalized)} "
            f"| {_pct(c.wer_raw)} | {_pct(e['buyer'])} | {_pct(e['sku'])} | {_pct(e['quantity'])} "
            f"| {_pct(e['unit'])} | {_pct(e['rate'])} | {c.stt_p50:.0f} / {c.stt_p95:.0f} "
            f"| {c.decision_p50:.2f} / {c.decision_p95:.2f} "
            f"| {_pct(c.sfer_gated)} ({c.errors_gated}/{c.trades}) "
            f"| {_pct(c.sfer_ungated)} ({c.errors_ungated}/{c.trades}) |"
        )

    verdict = _acceptance_text(noisy_all, settings)
    return "\n".join(
        [
            "# Kadal Kural — Noise & Silent-Error Benchmark",
            "",
            f"Generated {meta['date']} by `benchmark/run_eval.py` — {meta['scope']}.",
            "",
            "## Method (read this before the numbers)",
            "",
            "- **Speaker:** Gnani Timbre v2.5 synthesizes each corpus utterance (once, cached). This is a "
            "repeatable stand-in for a human speaker, not a recording of a trader: real accents, "
            "disfluencies and Lombard effect are **not** represented.",
            "- **Noise:** *synthetic*, spectrally shaped beds (harbour/market/traffic/ice-crusher; see "
            "`benchmark/noise_profiles.py`), mixed at a target **RMS SNR** over the speech segment. A "
            "noise-only lead-in and tail at the same absolute level surround the speech so the VAD must "
            "end the utterance through the noise. These are not field recordings of a harbour.",
            f"- **Pipeline:** 8 kHz PCM, 1,024-byte paced frames → Prisma v2.5 → merge segments → "
            f"normalizer → matcher → firewall on a fresh catalog-seeded ledger per utterance "
            f"(τ = {settings.confidence_threshold} with the gate; τ = 0 without).",
            "- **WER:** `jiwer`. *Normalized* passes both sides through `normalize_hybrid_tamil_numerals` "
            "(the corpus spells numbers as words; Prisma emits digits, so *raw* WER is inflated by "
            "formatting). Means over utterances.",
            "- **Entity accuracy:** pooled over ground-truth trades; extracted intents are matched to "
            "trades by best field overlap.",
            "- **Silent Financial Error Rate (SFER):** booked trades (`BOOKED` / `BOOKED_AFTER_BARGE_IN`) "
            "that match no ground-truth trade, divided by ground-truth trades attempted. Omitted trades "
            "are not silent errors. Without the gate, structural checks (unresolved buyer/SKU/rate/qty) "
            "still block booking.",
            "- **Latency:** *STT* is the latency Prisma reports per segment (mean per utterance); "
            "*firewall* is the measured wall time of `evaluate_utterance` (normalizer + matcher + "
            "decision + SQLite write). Timbre time-to-first-byte and barge-in flush are measured in Task 4.",
            "",
            "## Results",
            "",
            head,
            rule,
            *[line(c) for c in cells],
            "",
            "### Roll-up by SNR (all four noise profiles)",
            "",
            head,
            rule,
            *[line(c) for c in rollups],
            line(noisy_all),
            "",
            "## Does the confidence gate help?",
            "",
            verdict,
            "",
            "### Threshold sensitivity (all noisy cells, in-sample)",
            "",
            "τ was *not* tuned on a held-out set; this table is the same data the headline uses, so treat "
            "it as sensitivity, not as an out-of-sample claim.",
            "",
            "| τ | booked | silent errors | SFER | correct bookings |",
            "|---|---|---|---|---|",
            *[
                f"| {tau:g}{' (production)' if abs(tau - settings.confidence_threshold) < 1e-9 else ''} "
                f"| {b} | {e} | {_pct(e / t if t else 0.0)} | {c} |"
                for tau, b, e, c, t in sweep
            ],
            "",
            "## Failure modes",
            "",
            _failure_paragraph(rows, cells, noisy_all),
            "",
        ]
    )


def _acceptance_text(noisy: CellSummary, settings: AppSettings) -> str:
    on, off = noisy.errors_gated, noisy.errors_ungated
    if off == 0:
        return (
            f"Without the gate there were **no** silent errors across {noisy.trades} noisy trades, so this "
            "run cannot show a gate benefit (the pipeline made no confident mistakes to block)."
        )
    if on < off:
        return (
            f"**Yes, measurably.** Across all noisy cells the gate (τ = {settings.confidence_threshold}) "
            f"cut silent financial errors from {off} to {on} of {noisy.trades} attempted trades "
            f"({_pct(noisy.sfer_ungated)} → {_pct(noisy.sfer_gated)})."
        )
    return (
        f"**Not shown at τ = {settings.confidence_threshold}.** Gate ON: {on} silent errors, gate OFF: "
        f"{off}, of {noisy.trades} trades. The sensitivity table below shows whether a different "
        "threshold separates them; do not report the gate benefit from this run until that is resolved."
    )


def _failure_paragraph(rows: Sequence[EvalRow], cells: Sequence[CellSummary], noisy: CellSummary) -> str:
    noisy_cells = [c for c in cells if not c.label.startswith("clean") and c.n]
    if not noisy_cells:
        return "No noisy cells were evaluated in this run."
    worst = max(noisy_cells, key=lambda c: c.wer_normalized)
    weakest = min(ENTITY_FIELDS, key=lambda f: noisy.entity_accuracy[f])
    failed = sum(1 for r in rows if r.score is None)
    examples = [
        r for r in rows
        if r.score is not None and r.score.gated.silent_errors > 0
    ][:FAILURE_EXAMPLES]
    parts = [
        f"Across {noisy.n} noisy runs the weakest extracted entity was **{weakest}** "
        f"({_pct(noisy.entity_accuracy[weakest])} correct) and the worst cell by normalized WER was "
        f"**{worst.label}** ({_pct(worst.wer_normalized)}). "
        f"{failed} item(s) failed outright (API error or timeout) and are excluded from the averages."
    ]
    if examples:
        parts.append(
            "Silent errors that survived the gate (confident but wrong), spoken → heard: "
            + "; ".join(
                f"`{e.item.utterance.utterance_id}` @ {e.item.profile}/{e.item.snr_label} dB: "
                f"“{e.item.utterance.spoken_text}” → “{e.outcome.transcript}”"
                for e in examples
            )
            + "."
        )
    else:
        parts.append("No silent error survived the gate in this run.")
    parts.append(
        "Caveats: synthetic noise and a synthetic speaker bound how far these numbers transfer to a real "
        "harbour; the corpus uses two buyers and two SKUs, so entity accuracy is easier than it would be "
        "against a large catalog."
    )
    return " ".join(parts)


# ------------------------------------------------------------------------------ CLI


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kadal Kural noise & silent-error benchmark")
    p.add_argument("--limit", type=int, help="evaluate only N utterances (evenly strided sample)")
    p.add_argument("--profiles", nargs="+", default=list(NOISE_PROFILE_NAMES), choices=NOISE_PROFILE_NAMES)
    p.add_argument("--snrs", nargs="+", type=float, default=list(STANDARD_SNR_LEVELS_DB))
    p.add_argument("--no-clean", action="store_true", help="skip the zero-noise baseline row")
    p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    p.add_argument("--cache-dir", type=Path, default=_REPO_ROOT / "benchmark" / ".cache")
    p.add_argument("--out-dir", type=Path, default=_REPO_ROOT / "benchmark")
    p.add_argument("--analyze-only", action="store_true", help="never call the API; score cached transcripts")
    p.add_argument("--yes", action="store_true", help="confirm a large live run")
    return p.parse_args(argv)


async def main_async(args: argparse.Namespace) -> int:
    settings = AppSettings()
    corpus = sample_corpus(build_corpus(), args.limit)
    items = build_work_items(corpus, args.profiles, args.snrs, not args.no_clean)
    tail_ms = settings.min_silence_ms + settings.stt_trailing_silence_margin_ms
    cache = DiskCache(args.cache_dir, settings, LEAD_IN_MS, tail_ms)

    pending_stt = [i for i in items if cache.load_transcript(i) is None]
    needs_tts = {i.utterance.utterance_id for i in pending_stt}
    pending_tts = [u for u in corpus if u.utterance_id in needs_tts and cache.load_clean(u.utterance_id) is None]
    logger.info(
        "plan: %d items over %d utterances; live calls needed: %d STT + %d TTS (rest cached)",
        len(items), len(corpus), len(pending_stt), len(pending_tts),
    )

    backend: Optional[SpeechBackend] = None
    if not args.analyze_only and pending_stt:
        if len(pending_stt) + len(pending_tts) > LIVE_CALLS_NEEDING_CONFIRMATION and not args.yes:
            logger.error("refusing %d live calls without --yes (try --limit for a smoke test)",
                         len(pending_stt) + len(pending_tts))
            return 2
        if not settings.gnani_api_key.strip() or settings.gnani_api_key == "your_gnani_api_key_here":
            logger.error("KADAL_GNANI_API_KEY is not set in .env; use --analyze-only or set the key")
            return 2
        backend = LiveGnaniBackend(settings)

    transcripts = await gather_transcripts(items, backend, cache, settings, args.concurrency)
    scorer = Scorer(settings)
    rows = score_rows(items, transcripts, scorer)
    sweep = threshold_sweep(rows, scorer)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.out_dir / "results.csv")
    scope = (
        f"{len(corpus)} utterances × {len(args.profiles)} profiles × {len(args.snrs)} SNR levels"
        f"{'' if args.no_clean else ' + clean baseline'} = {len(items)} items"
        f"{' (SAMPLE RUN — not the full sweep)' if args.limit else ''}"
    )
    report = render_report(rows, sweep, settings, {"date": date.today().isoformat(), "scope": scope})
    (args.out_dir / "REPORT.md").write_text(report, encoding="utf-8")
    logger.info("wrote %s and %s", args.out_dir / "results.csv", args.out_dir / "REPORT.md")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    return asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
