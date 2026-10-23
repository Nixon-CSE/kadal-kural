"""
Centralized, immutable runtime configuration for Kadal Kural.
Follows 12-Factor App principles by loading settings from environment variables.
"""

from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent


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

    # Acoustic & VAD Parameters (Tuned for 85dB Harbour/Mandi Telephony)
    vad_threshold: float = Field(default=0.78, ge=0.0, le=1.0)
    min_speech_ms: int = Field(default=200, ge=50, le=2000)
    min_silence_ms: int = Field(default=360, ge=100, le=2000)
    assembler_window_sec: float = Field(default=1.5, ge=0.3, le=5.0)

    # Credit Firewall & Persistence Parameters
    confidence_threshold: float = Field(default=0.82, ge=0.50, le=0.99)
    db_path: str = Field(default="kadal_kural.db")
    catalog_path: str = Field(default=str(PACKAGE_ROOT / "data" / "catalog.json"))

    # Standard UPI Settlement Configuration
    merchant_upi_vpa: str = Field(default="kadalkural.harbour@okaxis")
    merchant_name: str = Field(default="Kadal Kural Wholesale Dispatch")
