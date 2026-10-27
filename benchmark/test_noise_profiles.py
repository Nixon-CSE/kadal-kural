"""Unit tests for the RMS-based SNR mixing function (Task 3 acceptance: within +/-0.5dB of target)."""

from __future__ import annotations

import numpy as np
import pytest

from benchmark.noise_profiles import (
    NOISE_PROFILE_NAMES,
    STANDARD_SNR_LEVELS_DB,
    generate_noise_bed,
    measured_snr_db,
    mix_pcm_at_snr,
    rms,
)

_SAMPLE_RATE = 8000
_DURATION_SEC = 2.0
_NUM_SAMPLES = int(_SAMPLE_RATE * _DURATION_SEC)
_SNR_TOLERANCE_DB = 0.5

# Speech-like test tone: 220Hz fundamental, moderate amplitude so mixing at low SNR
# (more added noise) still stays well within the int16 range without clipping.
_TEST_TONE = (
    8000.0 * np.sin(2.0 * np.pi * 220.0 * np.arange(_NUM_SAMPLES) / _SAMPLE_RATE)
).astype(np.int16)


@pytest.mark.parametrize("profile", NOISE_PROFILE_NAMES)
@pytest.mark.parametrize("target_snr_db", STANDARD_SNR_LEVELS_DB)
def test_mix_pcm_at_snr_achieves_target_within_tolerance(
    profile: str, target_snr_db: float
) -> None:
    result = mix_pcm_at_snr(
        _TEST_TONE, profile, target_snr_db, sample_rate=_SAMPLE_RATE, seed=42  # type: ignore[arg-type]
    )
    assert abs(result.achieved_snr_db - target_snr_db) <= _SNR_TOLERANCE_DB, (
        f"{profile} @ {target_snr_db}dB: achieved {result.achieved_snr_db:.2f}dB "
        f"(tolerance +/-{_SNR_TOLERANCE_DB}dB)"
    )


def test_mix_pcm_at_snr_does_not_clip_moderate_amplitude_signal() -> None:
    result = mix_pcm_at_snr(_TEST_TONE, "market", 5.0, sample_rate=_SAMPLE_RATE, seed=1)
    assert np.max(np.abs(result.mixed_pcm_int16)) < 32767, "signal clipped at the lowest tested SNR"


def test_measured_snr_db_is_zero_for_equal_rms_signals() -> None:
    rng = np.random.default_rng(0)
    a = rng.standard_normal(1000) * 100
    b = a.copy()
    assert abs(measured_snr_db(a, b)) < 1e-6


def test_generate_noise_bed_has_unit_rms() -> None:
    for profile in NOISE_PROFILE_NAMES:
        bed = generate_noise_bed(profile, 4000, _SAMPLE_RATE, seed=7)
        assert abs(rms(bed) - 1.0) < 1e-6, profile


def test_generate_noise_bed_is_deterministic_for_same_seed() -> None:
    a = generate_noise_bed("harbour", 2000, _SAMPLE_RATE, seed=5)
    b = generate_noise_bed("harbour", 2000, _SAMPLE_RATE, seed=5)
    np.testing.assert_array_equal(a, b)


def test_generate_noise_bed_differs_across_profiles() -> None:
    harbour = generate_noise_bed("harbour", 4000, _SAMPLE_RATE, seed=3)
    ice = generate_noise_bed("ice_crusher", 4000, _SAMPLE_RATE, seed=3)
    assert not np.allclose(harbour, ice)
