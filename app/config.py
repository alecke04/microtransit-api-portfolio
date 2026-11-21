"""Explicit, fail-closed settings for the standalone portfolio edition."""

import json
import re
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: SecretStr = SecretStr("")
    READ_API_KEY: SecretStr = SecretStr("")
    VALID_API_KEYS_JSON: SecretStr = SecretStr("{}")
    CORS_ORIGINS: str = "http://localhost:3000"
    TESTING: bool = False
    HTTP_REQUESTS_PER_MINUTE: int = Field(default=120, ge=1, le=10000)
    HTTP_MAX_BUCKETS: int = Field(default=2000, ge=1, le=10000)
    INGEST_MIN_INTERVAL_SECONDS: float = Field(default=2, ge=0, le=60)
    WS_MAX_CONNECTIONS: int = Field(default=128, ge=1, le=1000)
    WS_MAX_PER_IP: int = Field(default=8, ge=1, le=100)
    WS_AUTH_TIMEOUT_SECONDS: float = Field(default=5, gt=0, le=30)
    WS_SEND_TIMEOUT_SECONDS: float = Field(default=2, gt=0, le=10)

    def device_keys(self) -> dict[str, str]:
        value = json.loads(self.VALID_API_KEYS_JSON.get_secret_value())
        if not isinstance(value, dict):
            raise ValueError("Device credentials must be a JSON object")
        return value

    def origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    def validate_required(self) -> None:
        if not self.DATABASE_URL.get_secret_value().startswith(
            ("postgresql://", "postgres://", "postgresql+asyncpg://")
        ):
            raise ValueError("A PostgreSQL DATABASE_URL is required")
        keys = self.device_keys()
        if not keys or len(keys) > 100:
            raise ValueError("Configure between 1 and 100 device credentials")
        for device, key in keys.items():
            if not isinstance(device, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", device):
                raise ValueError("Invalid configured device identifier")
            if not isinstance(key, str) or not 32 <= len(key) <= 256 or key.startswith("replace-"):
                raise ValueError("Generate a separate random key for each device")
        reader = self.READ_API_KEY.get_secret_value()
        if not 32 <= len(reader) <= 256 or reader.startswith("replace-"):
            raise ValueError("Generate a random read credential")
        if len(set(keys.values())) != len(keys) or reader in keys.values():
            raise ValueError("Read and per-device credentials must be distinct")
        if "*" in self.origins():
            raise ValueError("Configure exact browser origins")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
