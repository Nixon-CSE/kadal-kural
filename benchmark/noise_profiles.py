"""
Synthetic noise beds and RMS-based SNR mixing for the Noise & Silent-Error Benchmark Suite.

Honesty note: these are *synthetic, spectrally-shaped* stand-ins for harbour/market/
traffic/ice-crusher environments, generated with numpy FFT spectral shaping — this
project has no licensed real-world noise recordings available. They are built to be
plausible frequency-domain approximations (low rumble for harbour/traffic, broadband
mid-band "babble" for market, high-frequency grinding for ice-crusher), not acoustic
measurements of a real harbour. Report this as what it is — a controlled synthetic
degradation, not validated field noise — never as "real harbour conditions".

SNR calculation (RMS-based): for a signal x and a noise n of equal length,
    SNR_dB = 20 * log10(rms(x) / rms(scaled_n))
Mixing at a target SNR scales the noise so this holds, then adds it to the signal:
    scale = rms(x) / (rms(n) * 10 ** (target_snr_db / 20))
    mixed = x + scale * n
This is the standard RMS/power-ratio SNR definition used throughout speech-enhancement
literature (e.g. the VoiceBank-DEMAND / REVERB-style mixing recipes), and the one the
brief's acceptance criterion (measured output SNR within +/-0.5dB of target) checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal

import numpy as np
import numpy.typing as npt

NoiseProfileName = Literal["harbour", "market", "traffic", "ice_crusher"]
NOISE_PROFILE_NAMES: Final[tuple[NoiseProfileName, ...]] = (
    "harbour",
    "market",
    "traffic",
    "ice_crusher",
)
STANDARD_SNR_LEVELS_DB: Final[tuple[float, ...]] = (20.0, 15.0, 10.0, 5.0)

_EPS: Final[float] = 1e-12


def rms(samples: npt.NDArray[Any]) -> float:
    """Root-mean-square amplitude of a signal, computed in float64 to avoid int overflow."""
    x = samples.astype(np.float64)
    return float(np.sqrt(np.mean(x * x)) + _EPS)


def measured_snr_db(signal: npt.NDArray[Any], noise_component: npt.NDArray[Any]) -> float:
    """RMS-based SNR in dB of ``signal`` against an additive ``noise_component`` of equal length."""
    return 20.0 * float(np.log10(rms(signal) / rms(noise_component)))


def _spectrally_shaped_noise(
    num_samples: int,
    sample_rate: int,
    *,
    seed: int,
    low_hz: float,
    high_hz: float,
    rolloff_db_per_octave: float = 0.0,
) -> npt.NDArray[Any]:
    """
    Generates band-limited noise by FFT-shaping white noise: zeroes frequencies outside
    [low_hz, high_hz] and applies an optional per-octave rolloff inside the band, then
    normalizes to unit RMS. Pure numpy (no scipy dependency).
    """
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(num_samples)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(num_samples, d=1.0 / sample_rate)

    band_mask = (freqs >= low_hz) & (freqs <= high_hz)
    gain = np.zeros_like(freqs)
    if rolloff_db_per_octave != 0.0 and np.any(band_mask):
        band_freqs = np.where(freqs > 0, freqs, low_hz if low_hz > 0 else 1.0)
        octaves_above_low = np.log2(np.clip(band_freqs / max(low_hz, 1.0), 1e-6, None))
        gain[band_mask] = 10 ** ((rolloff_db_per_octave * octaves_above_low[band_mask]) / 20.0)
    else:
        gain[band_mask] = 1.0

    shaped_spectrum = spectrum * gain
    shaped = np.fft.irfft(shaped_spectrum, n=num_samples)
    shaped_rms = rms(shaped)
    return shaped / shaped_rms if shaped_rms > _EPS else shaped


def _add_periodic_impulses(
    base: npt.NDArray[Any], sample_rate: int, *, seed: int, rate_hz: float, decay_sec: float, gain: float
) -> npt.NDArray[Any]:
    """Adds sparse, randomly-jittered decaying impulses (engine knocks / ice-crusher crackle)."""
    rng = np.random.default_rng(seed + 1)
    out = base.copy()
    num_samples = len(base)
    avg_gap = sample_rate / max(rate_hz, 0.01)
    decay_samples = max(1, int(decay_sec * sample_rate))
    t = np.arange(decay_samples)
    envelope = np.exp(-t / max(decay_samples / 4, 1))
    pos = 0.0
    while True:
        pos += avg_gap * (0.6 + 0.8 * rng.random())
        idx = int(pos)
        if idx >= num_samples:
            break
        end = min(idx + decay_samples, num_samples)
        out[idx:end] += gain * envelope[: end - idx] * (rng.random() * 2 - 1)
    return out


def generate_noise_bed(
    profile: NoiseProfileName,
    num_samples: int,
    sample_rate: int,
    *,
    seed: int = 0,
) -> npt.NDArray[Any]:
    """
    Returns ``num_samples`` of unit-RMS synthetic noise for the given profile, as float64.
    Caller scales it to a target SNR with ``mix_at_snr`` before converting to int16 PCM.
    """
    if profile == "harbour":
        # Low-frequency rumble (water, engines, dock machinery) with broad low-mid energy.
        bed = _spectrally_shaped_noise(
            num_samples, sample_rate, seed=seed, low_hz=20, high_hz=1200, rolloff_db_per_octave=-3.0
        )
    elif profile == "market":
        # Broadband mid-band "babble" — crowd speech energy concentrates ~300-3000Hz.
        bed = _spectrally_shaped_noise(num_samples, sample_rate, seed=seed, low_hz=250, high_hz=3500)
    elif profile == "traffic":
        # Low rumble plus sparse low-frequency horn/engine impulses.
        bed = _spectrally_shaped_noise(
            num_samples, sample_rate, seed=seed, low_hz=30, high_hz=800, rolloff_db_per_octave=-4.0
        )
        bed = _add_periodic_impulses(
            bed, sample_rate, seed=seed, rate_hz=0.4, decay_sec=0.25, gain=2.5
        )
    elif profile == "ice_crusher":
        # High-frequency grinding plus sharp crackle impulses.
        bed = _spectrally_shaped_noise(
            num_samples, sample_rate, seed=seed, low_hz=1500, high_hz=min(7900, sample_rate // 2 - 1)
        )
        bed = _add_periodic_impulses(
            bed, sample_rate, seed=seed, rate_hz=6.0, decay_sec=0.03, gain=1.8
        )
    else:  # pragma: no cover - Literal type keeps this unreachable from type-checked callers
        raise ValueError(f"unknown noise profile: {profile!r}")

    bed_rms = rms(bed)
    return bed / bed_rms if bed_rms > _EPS else bed


def _tile_or_trim(noise: npt.NDArray[Any], length: int) -> npt.NDArray[Any]:
    if len(noise) >= length:
        return noise[:length]
    reps = int(np.ceil(length / len(noise)))
    return np.tile(noise, reps)[:length]


@dataclass(frozen=True)
class SnrMixResult:
    mixed_pcm_int16: npt.NDArray[np.int16]
    achieved_snr_db: float


def mix_pcm_at_snr(
    signal_pcm_int16: npt.NDArray[Any],
    noise_profile: NoiseProfileName,
    target_snr_db: float,
    *,
    sample_rate: int,
    seed: int = 0,
) -> SnrMixResult:
    """
    Mixes int16 PCM ``signal_pcm_int16`` with a synthetic noise bed from ``noise_profile``
    at ``target_snr_db``, using the standard RMS/power-ratio SNR definition (module
    docstring). Clips the result to the int16 range (clipping, if any, is reported via a
    lower achieved_snr_db than requested rather than silently distorting past it).
    """
    noise = _tile_or_trim(
        generate_noise_bed(noise_profile, len(signal_pcm_int16), sample_rate, seed=seed),
        len(signal_pcm_int16),
    )
    signal = signal_pcm_int16.astype(np.float64)
    signal_rms = rms(signal)
    noise_rms = rms(noise)
    scale = signal_rms / (noise_rms * (10 ** (target_snr_db / 20.0)))
    scaled_noise = noise * scale

    mixed = signal + scaled_noise
    mixed_clipped = np.clip(mixed, -32768, 32767)
    achieved = measured_snr_db(signal, mixed_clipped - signal)
    return SnrMixResult(
        mixed_pcm_int16=np.round(mixed_clipped).astype(np.int16),
        achieved_snr_db=achieved,
    )


def pcm16_bytes_to_array(pcm_bytes: bytes) -> npt.NDArray[Any]:
    return np.frombuffer(pcm_bytes, dtype=np.int16)


def array_to_pcm16_bytes(samples: npt.NDArray[Any]) -> bytes:
    return samples.astype(np.int16).tobytes()
