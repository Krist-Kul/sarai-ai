"""Configuration. Environment only -- no config file, no defaults hidden in code."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["deepseek", "anthropic"]
Device = Literal["auto", "cuda", "mps", "cpu"]

ALLOWED_UPLOAD_EXTENSIONS: frozenset[str] = frozenset(
    {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".mp4"}
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- storage ---
    data_dir: Path = Path("./data")
    min_free_disk_bytes: int = 5 * 1024**3
    upload_max_bytes: int = 500 * 1024**2

    # --- api ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # --- worker ---
    worker_poll_seconds: float = 2.0
    worker_heartbeat_seconds: float = 10.0
    worker_stale_claim_minutes: int = 30
    worker_max_attempts: int = 3
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    # --- asr ---
    asr_model: str = "typhoon-ai/typhoon-whisper-turbo"
    asr_device: Device = "auto"

    # --- diarization ---
    hf_token: str | None = None
    diarization_model: str = "pyannote/speaker-diarization-community-1"

    # --- llm ---
    llm_enabled: bool = True
    llm_provider: Provider = "deepseek"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-sonnet-5"
    llm_single_call_chars: int = 40_000
    llm_chunk_chars: int = 30_000
    llm_chunk_overlap_segments: int = 2
    llm_timeout_seconds: float = 300.0

    # Empty strings in a .env should read as "unset", not as a real key.
    @field_validator("hf_token", "deepseek_api_key", "anthropic_api_key", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def db_path(self) -> Path:
        return self.data_dir / "sarai.db"

    @property
    def uploads_dir(self) -> Path:
        """Original uploaded files, byte-identical to what the user sent."""
        return self.data_dir / "uploads"

    @property
    def work_dir(self) -> Path:
        """Derived artifacts: normalized 16 kHz wavs."""
        return self.data_dir / "work"

    @property
    def docs_dir(self) -> Path:
        return self.data_dir / "docs"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def diarization_enabled(self) -> bool:
        """No HF token means the gated pyannote model cannot be fetched."""
        return self.hf_token is not None

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.work_dir, self.docs_dir):
            d.mkdir(parents=True, exist_ok=True)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
