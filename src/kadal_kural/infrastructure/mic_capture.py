"""
Opt-in capture of raw live-mic audio, for diagnosing speech-start clipping.

When ``AppSettings.mic_capture_dir`` is set, every /ws/live-audio session writes the exact PCM
the browser sent (before framing) to ``mic_<timestamp>.wav`` and, on close, a sidecar
``mic_<timestamp>.json`` listing each Prisma segment with where in that audio it arrived. A
clipped utterance can then be cut out and replayed with scripts/replay_mic_capture.py.
Off by default: these files are recordings of real voices.
"""

from __future__ import annotations

import json
import time
import wave
from pathlib import Path
from typing import Callable, Dict, List, Optional

from kadal_kural.config import NS_PER_MS, PCM_SAMPLE_WIDTH_BYTES

MS_PER_SECOND = 1000


class MicCaptureRecorder:
    """Writes one live session's raw mic PCM to a WAV and its segment arrivals to a JSON sidecar."""

    def __init__(
        self,
        directory: Path,
        sample_rate: int,
        clock: Callable[[], int] = time.perf_counter_ns,
        stamp: Optional[str] = None,
    ) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        name = f"mic_{stamp or time.strftime('%Y%m%d_%H%M%S')}"
        self.wav_path = directory / f"{name}.wav"
        self.sidecar_path = directory / f"{name}.json"
        self._sample_rate = sample_rate
        self._clock = clock
        self._started_ns = clock()
        self._bytes = 0
        self._segments: List[Dict[str, object]] = []
        self._wav = wave.open(str(self.wav_path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(PCM_SAMPLE_WIDTH_BYTES)
        self._wav.setframerate(sample_rate)

    def audio_ms(self) -> float:
        """How much audio has been captured so far, in milliseconds."""
        return self._bytes / (self._sample_rate * PCM_SAMPLE_WIDTH_BYTES) * MS_PER_SECOND

    def write(self, pcm: bytes) -> None:
        self._wav.writeframes(pcm)
        self._bytes += len(pcm)

    def mark_segment(self, text: str, reported_latency_ms: float) -> None:
        """Records a Prisma segment against the audio captured so far (it was spoken before this point)."""
        self._segments.append(
            {
                "text": text,
                "reported_latency_ms": reported_latency_ms,
                "audio_ms_at_arrival": round(self.audio_ms(), 1),
                "session_ms_at_arrival": round((self._clock() - self._started_ns) / NS_PER_MS, 1),
            }
        )

    def close(self) -> None:
        self._wav.close()
        sidecar = {
            "wav": self.wav_path.name,
            "sample_rate": self._sample_rate,
            "audio_ms": round(self.audio_ms(), 1),
            "segments": self._segments,
        }
        self.sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
