"""
Centralized, immutable runtime configuration for Kadal Kural.
Follows 12-Factor App principles by loading settings from environment variables.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent

# Gnani Prisma v2.5 wire format: strict 1,024-byte frames of 16-bit mono PCM.
PCM_FRAME_BYTES: int = 1024
PCM_SAMPLE_WIDTH_BYTES: int = 2
SUPPORTED_PCM_SAMPLE_RATES: tuple[int, ...] = (8000, 16000)
LIVE_MIC_SAMPLE_RATE: int = 8000
WS_PING_INTERVAL_SEC: float = 20.0

# Unit confidence when the word after the quantity isn't a recognised unit and the matcher
# falls back to the SKU's default_unit (e.g. 'kg' heard as 'கார்'). Deliberately below the
# default confidence_threshold so an assumed unit routes the trade to confirmation.
DEFAULT_ASSUMED_UNIT_CONFIDENCE: float = 0.75


def frame_pace_seconds(sample_rate: int) -> float:
    """Real-time duration of one 1,024-byte PCM frame at ``sample_rate`` (64ms @ 8kHz, 32ms @ 16kHz)."""
    return (PCM_FRAME_BYTES / PCM_SAMPLE_WIDTH_BYTES) / sample_rate


class AppSettings(BaseSettings):
    """Validated application configuration for Kadal Kural B2B Credit Firewall."""

    model_config = SettingsConfigDict(
        env_prefix="KADAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Gnani AI Artha Endpoints & Credentials
    gnani_api_key: str = Field(default="", description="Gnani AI Console API Key ID")
    prisma_ws_url: str = Field(default="wss://api.vachana.ai/stt/v3/stream")
    timbre_ws_url: str = Field(default="wss://api.vachana.ai/api/v1/tts")
    timbre_default_voice: str = Field(default="Asmita")

    # Gnani WebSocket resilience
    gnani_open_timeout_sec: float = Field(default=10.0, gt=0.0)
    gnani_read_timeout_sec: float = Field(default=15.0, gt=0.0)
    gnani_max_attempts: int = Field(default=3, ge=1, le=10)
    gnani_backoff_base_sec: float = Field(default=0.5, ge=0.0)
    stt_trailing_silence_margin_ms: int = Field(default=500, ge=0, le=5000)
    stt_drain_grace_sec: float = Field(default=0.3, ge=0.0)

    # Acoustic & VAD Parameters (Tuned for 85dB Harbour/Mandi Telephony)
    vad_threshold: float = Field(default=0.78, ge=0.0, le=1.0)
    min_speech_ms: int = Field(default=200, ge=50, le=2000)
    min_silence_ms: int = Field(default=360, ge=100, le=2000)
    assembler_window_sec: float = Field(default=1.5, ge=0.3, le=5.0)

    # Credit Firewall & Persistence Parameters
    confidence_threshold: float = Field(default=0.82, ge=0.50, le=0.99)
    assumed_unit_confidence: float = Field(default=DEFAULT_ASSUMED_UNIT_CONFIDENCE, ge=0.0, le=1.0)
    db_path: str = Field(default="kadal_kural.db")
    catalog_path: str = Field(default=str(PACKAGE_ROOT / "data" / "catalog.json"))

    # Standard UPI Settlement Configuration
    merchant_upi_vpa: str = Field(default="kadalkural.harbour@okaxis")
    merchant_name: str = Field(default="Kadal Kural Wholesale Dispatch")
