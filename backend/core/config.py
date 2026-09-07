"""AEGIS-Marine: Central Application Settings & Environment Configuration."""

from __future__ import annotations

import json
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "AEGIS-Marine API Gateway"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # Database & Storage
    DATABASE_URL: str = Field(
        default=os.getenv(
            "DATABASE_URL",
            "postgresql://aegis:aegis_secure_password@localhost:5432/aegis_marine",
        )
    )
    REDIS_URL: str = Field(default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    MINIO_ENDPOINT: str = Field(default=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"))
    MINIO_BUCKET: str = Field(default=os.getenv("MINIO_BUCKET", "aegis-storage"))

    # Security & JWT
    JWT_SECRET_KEY: str = Field(
        default=os.getenv(
            "JWT_SECRET_KEY",
            "aegis_development_super_secret_jwt_key_32bytes_minimum_length_required_12345",
        )
    )
    JWT_ALGORITHM: str = Field(default=os.getenv("JWT_ALGORITHM", "HS256"))
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    )

    # OIDC & Identity Provider
    OIDC_ISSUER: str | None = Field(default=os.getenv("OIDC_ISSUER", None))
    OIDC_AUDIENCE: str | None = Field(default=os.getenv("OIDC_AUDIENCE", None))

    # CORS Allowed Origins
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    @classmethod
    def load(cls) -> Settings:
        """Loads settings with environment overrides for list fields."""
        settings = cls()
        raw_cors = os.getenv("CORS_ORIGINS")
        if raw_cors:
            try:
                settings.CORS_ORIGINS = json.loads(raw_cors)
            except Exception:
                settings.CORS_ORIGINS = [
                    origin.strip() for origin in raw_cors.split(",") if origin.strip()
                ]
        return settings


settings = Settings.load()
