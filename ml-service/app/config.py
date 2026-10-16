"""Configuration settings for ml-service."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings read from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ml-service"
    app_version: str = "1.0.0"
    model_mode: Literal["mock", "real"] = "mock"
    model_uri: str = ""
    model_cache_dir: str = "/tmp/model-cache"
    mlflow_tracking_uri: str = "http://mlflow:5000"
    log_level: str = "INFO"
    require_auth: bool = False


settings = Settings()
