"""Unit and integration tests for the Kadal Kural Pre-Dispatch Credit Firewall."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from kadal_kural.config import AppSettings
from kadal_kural.domain.matcher import BilingualCatalogMatcher
from kadal_kural.domain.models import LedgerEventStatus
from kadal_kural.domain.normalizer import (
    format_inr_for_timbre_prosody,
    normalize_hybrid_tamil_numerals,
    strip_tamil_dative_suffix,
)
from kadal_kural.domain.service import PreDispatchCreditFirewallService
from kadal_kural.infrastructure.persistence import AppendOnlyLedgerRepository

PLAYGROUND_SCREENSHOT_TRANSCRIPT = (
    "செந்தில் சீஃபுட்ஸ்க்கு 40 பாக்ஸ் எக்ஸ்போர்ட் வஞ்சரம் எழுநூற்றி 40 ரேட்டு "
    "குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு கிரெடிட்டில் ஏற்று"
)

PROBE_RESULTS_PATH = Path(__file__).resolve().parents[1] / "tamil_itn_probe_results.jsonl"

# Expected normalizer output for the raw Prisma v2.5 transcript captured under each probe label
# (scripts/probe_tamil_itn.py, live API). Each value was checked by hand against the spoken input.
EXPECTED_NORMALIZED_OUTPUT_BY_LABEL = {
    "word_simple_25": "25 பாக்ஸ் வஞ்சரம்",
    "word_additive_740": "740",
    "word_additive_560": "560",
    "word_additive_215": "215",
    "word_round_hundred": "100 பாக்ஸ்",
    "word_round_thousand": "1000",
    "digit_simple_25": "25 பாக்ஸ் வஞ்சரம்",
    "digit_740": "740",
    "digit_three_digit_rate": "செந்திலுக்கு 25 பாக்ஸ் வஞ்சரம் ரேட்டு 250",
    "hybrid_740_digit": "740",
    "hybrid_560_digit": "560",
    "hybrid_215_word": "215 கணக்கில் போடு",
    "trade_senthil_full": "செந்திலுக்கு 25 பாக்ஸ் வஞ்சிரம் ரேட்டு 250",
    "trade_kumaran_full": "குமரனுக்கு 10 கிலோ டைகர் பிரான் ரேட் 740",
    "trade_barge_in_override": "செந்திலுக்கு 20 பாக்ஸ் மட்டும் போடு",
    "trade_tanglish_mixed": "செந்தில்கு 25 பாக்ஸ் வஞ்சரம் ரேட் 250",
    "undo_command": "கடைசி ஆர்டர் கேன்சல்",
}


def _load_probe_transcripts() -> dict[str, str]:
    records = [json.loads(line) for line in PROBE_RESULTS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {str(rec["label"]): str(rec["raw_transcript"]) for rec in records}


def test_normalize_hybrid_tamil_numerals_against_live_probe_transcripts() -> None:
    transcripts = _load_probe_transcripts()
    assert len(EXPECTED_NORMALIZED_OUTPUT_BY_LABEL) >= 10
    missing = set(EXPECTED_NORMALIZED_OUTPUT_BY_LABEL) - set(transcripts)
    assert not missing, f"labels absent from {PROBE_RESULTS_PATH.name}: {sorted(missing)}"
    for label, expected in EXPECTED_NORMALIZED_OUTPUT_BY_LABEL.items():
        assert normalize_hybrid_tamil_numerals(transcripts[label]) == expected, label


def test_normalize_lakh_remainder_from_live_probe() -> None:
    raw = _load_probe_transcripts()["word_lakh_phrase"]  # '1,00,000 இருபத்தி ஐயாயிரம் ரூபாய்'
    assert normalize_hybrid_tamil_numerals(raw) == "125000 ரூபாய்"


# Clean-condition Prisma transcript for multi_09, copied verbatim from benchmark/results.csv.
# Prisma glued a dative case ending onto the additive prefix ('ஐநூற்று 60' -> 'ஐநூற்றுக்கு 60'),
# which used to leave the first rate parsed as 60 instead of 560.
MULTI_09_CLEAN_TRANSCRIPT = (
    "செந்தில் சீஃபுட்ஸ் 15 கிலோ டைகர் பிரான் ஐநூற்றுக்கு 60 ரேட்டு "
    "குமரனுக்கு 60 கிலோ டைகர் பிரான் எழுநூற்றி 40 ரேட்டு"
)


def test_normalize_additive_prefix_with_case_ending_multi_09() -> None:
    assert normalize_hybrid_tamil_numerals(MULTI_09_CLEAN_TRANSCRIPT) == (
        "செந்தில் சீஃபுட்ஸ் 15 கிலோ டைகர் பிரான் 560 ரேட்டு "
        "குமரனுக்கு 60 கிலோ டைகர் பிரான் 740 ரேட்டு"
    )


# Harbour-condition (10 dB and 5 dB) Prisma transcript for tanglish_02, copied verbatim from
# benchmark/results.csv. Spoken 'kg' came back as 'கார்', which isn't a unit word, and the
# matcher used to fall back to 'box' silently instead of the prawn SKU's default 'kg'.
TANGLISH_02_HARBOUR_TRANSCRIPT = "குமரன்க்கு முப்பத்தி கார் ஜப்ரான் 500 ரேட்டு"


def test_unrecognised_unit_falls_back_to_sku_default_tanglish_02() -> None:
    settings = AppSettings()
    matcher = BilingualCatalogMatcher(settings.catalog_path, settings.assumed_unit_confidence)
    (intent,) = matcher.parse_utterance(TANGLISH_02_HARBOUR_TRANSCRIPT)
    assert intent.sku_id == "SKU-PRW-TIG"
    assert intent.quantity == 30
    assert intent.rate_inr == 500
    assert intent.unit == "kg"
    assert settings.assumed_unit_confidence < 1.0
    assert intent.overall_confidence <= settings.assumed_unit_confidence


def test_recognised_unit_does_not_cap_confidence() -> None:
    settings = AppSettings()
    matcher = BilingualCatalogMatcher(settings.catalog_path, settings.assumed_unit_confidence)
    (intent,) = matcher.parse_utterance("குமரனுக்கு 30 கிலோ டைகர் பிரான் 500 ரேட்டு")
    assert intent.unit == "kg"
    assert intent.overall_confidence > settings.assumed_unit_confidence


def test_strip_tamil_dative_suffixes() -> None:
    assert strip_tamil_dative_suffix("செந்தில் சீஃபுட்ஸ்க்கு") == "செந்தில் சீஃபுட்ஸ்"
    assert strip_tamil_dative_suffix("குமரனுக்கு") == "குமரன்"
    assert strip_tamil_dative_suffix("செந்திலுக்கு") == "செந்தில்"


def test_format_inr_for_timbre_prosody() -> None:
    assert format_inr_for_timbre_prosody(128000) == "1 லட்சத்து 28 ஆயிரம் ரூபாய்"
    assert format_inr_for_timbre_prosody(150000) == "1 லட்சத்து 50 ஆயிரம் ரூபாய்"
    assert format_inr_for_timbre_prosody(29600) == "ரூபாய் 29,600"


def test_end_to_end_credit_firewall_and_barge_in(tmp_path: Path) -> None:
    db_file = tmp_path / "test_kadal.db"
    settings = AppSettings(db_path=str(db_file))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    service = PreDispatchCreditFirewallService(settings, matcher, repo)

    decisions = service.evaluate_utterance(PLAYGROUND_SCREENSHOT_TRANSCRIPT, stt_latency_ms=288.0)
    assert len(decisions) == 2

    senthil_decision, kumaran_decision = decisions
    assert senthil_decision.status == LedgerEventStatus.CREDIT_HOLD_BREACH
    assert senthil_decision.trade_value_inr == 29_600
    assert senthil_decision.projected_balance_inr == 157_600
    assert senthil_decision.excess_amount_inr == 7_600

    assert kumaran_decision.status == LedgerEventStatus.BOOKED
    assert kumaran_decision.trade_value_inr == 33_600
    assert kumaran_decision.projected_balance_inr == 75_600

    # Verify Senthil balance was NOT committed during credit hold
    assert repo.get_buyer_row("BUY-101")["running_balance_inr"] == 128_000

    # Step 2: Barge-in quantity override
    override_decisions = service.evaluate_utterance("செந்திலுக்கு 25 பாக்ஸ் மட்டும் போடு")
    assert len(override_decisions) == 1
    override = override_decisions[0]
    assert override.status == LedgerEventStatus.BOOKED_AFTER_BARGE_IN
    assert override.trade_value_inr == 18_500
    assert override.projected_balance_inr == 146_500
    assert repo.get_buyer_row("BUY-101")["running_balance_inr"] == 146_500


def test_voice_undo_compensating_transaction(tmp_path: Path) -> None:
    db_file = tmp_path / "test_undo.db"
    settings = AppSettings(db_path=str(db_file))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    service = PreDispatchCreditFirewallService(settings, matcher, repo)

    # Book Kumaran stores (42,000 + 33,600 = 75,600)
    service.evaluate_utterance(
        "குமரனுக்கு 60 கிலோ டைகர் ஃப்ராண்ட் ஐநூற்றி 60 ரேட்டு கிரெடிட்டில் ஏற்று"
    )
    assert repo.get_buyer_row("BUY-102")["running_balance_inr"] == 75_600

    # Issue Voice Undo
    undo_decisions = service.evaluate_utterance("கடைசி ஆர்டர் கேன்சல்")
    assert len(undo_decisions) == 1
    assert undo_decisions[0].status == LedgerEventStatus.VOIDED_BY_UNDO
    assert undo_decisions[0].projected_balance_inr == 42_000
    assert repo.get_buyer_row("BUY-102")["running_balance_inr"] == 42_000


def test_confidence_gate_blocks_unknown_buyer(tmp_path: Path) -> None:
    db_file = tmp_path / "test_gate.db"
    settings = AppSettings(db_path=str(db_file))
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    service = PreDispatchCreditFirewallService(settings, matcher, repo)

    decisions = service.evaluate_utterance("புது கடைக்கு 30 பாக்ஸ் வஞ்சரம் போடு")
    assert len(decisions) == 1
    assert decisions[0].status == LedgerEventStatus.PENDING_CLARIFICATION

import io
import wave
from kadal_kural.infrastructure.gnani_client import GnaniArthaSpeechClient


@pytest.mark.asyncio
async def test_live_gnani_timbre_to_prisma_roundtrip(tmp_path: Path) -> None:
    """
    LIVE E2E PRODUCTION NETWORK TEST (Zero Mocks):
    1. Calls live wss://api.vachana.ai/api/v1/tts (Timbre v2.5) to synthesize a Tamil trade utterance.
    2. Converts the returned WAV audio to 8,000 Hz 16-bit mono telephony PCM.
    3. Streams exact 1,024-byte frames at 64ms intervals to wss://api.vachana.ai/stt/v3/stream (Prisma v2.5).
    4. Runs the returned live Prisma transcript through the Credit Firewall into SQLite WAL.
    """
    import audioop  # removed in Python 3.13; imported here so collection works on newer interpreters

    settings = AppSettings(db_path=str(tmp_path / "live_e2e.db"))
    if not settings.gnani_api_key or settings.gnani_api_key == "your_gnani_api_key_here":
        pytest.skip("Set KADAL_GNANI_API_KEY in .env to run live Gnani WebSocket E2E test")

    client = GnaniArthaSpeechClient(settings)

    # 1. Synthesize real Tamil speech audio via live Gnani Timbre v2.5 WebSocket
    spoken_trade_tamil = "குமரன் ஸ்டோர்ஸ்க்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு"
    tts_telemetry = await client.synthesize_timbre_v25(spoken_trade_tamil, sample_rate=16000)

    assert len(tts_telemetry.audio_wav_bytes) > 1024, "Timbre v2.5 must return real WAV bytes"
    assert tts_telemetry.ttfb_ms > 0.0, "Measured TTFB latency must be positive"
    assert tts_telemetry.was_interrupted is False

    # 2. Strictly parse the WAV (no headerless fallback) and downsample 16kHz -> 8kHz telephony PCM
    with wave.open(io.BytesIO(tts_telemetry.audio_wav_bytes), "rb") as wf:
        assert (wf.getnchannels(), wf.getsampwidth(), wf.getframerate()) == (1, 2, 16000)
        pcm_16k = wf.readframes(wf.getnframes())
        assert len(pcm_16k) == len(tts_telemetry.audio_wav_bytes) - 44, "WAV header sizes must be exact"
        src_rate = wf.getframerate()

    pcm_8k, _ = audioop.ratecv(pcm_16k, 2, 1, src_rate, 8000, None)

    # 3. Stream 8kHz PCM in 1,024-byte frames to live Gnani Prisma v2.5 WebSocket
    live_segments: list[str] = []
    live_latencies: list[float] = []

    async def _on_live_segment(text: str, lat_ms: float) -> None:
        if text.strip():
            live_segments.append(text.strip())
            live_latencies.append(lat_ms)

    await client.stream_pcm_to_prisma_v25(
        pcm_8k,
        _on_live_segment,
        sample_rate=8000,
        lang_code="ta-IN",
        enable_boosting=True,
    )

    merged_live_transcript = " ".join(live_segments)
    assert len(merged_live_transcript) > 0, "Prisma v2.5 must return a live Tamil transcript"

    # 4. Verify live transcript evaluates through the Credit Firewall
    matcher = BilingualCatalogMatcher(settings.catalog_path)
    repo = AppendOnlyLedgerRepository(settings.db_path, list(matcher.buyers.values()))
    firewall = PreDispatchCreditFirewallService(settings, matcher, repo)

    decisions = firewall.evaluate_utterance(merged_live_transcript)
    assert len(decisions) >= 1
