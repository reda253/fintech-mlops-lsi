"""Configuration settings for the transaction simulator."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class SimulatorSettings(BaseSettings):
    """Simulator settings configurable via environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gateway_url: str = "http://localhost:8080"
    auth_username: str = "simulator"
    auth_password: str = "simulator"
    data_path: str = "ml/data/raw/fraudTest.csv"
    tps: float = 10.0
    feedback_delay_seconds: float = 120.0
    dry_run: bool = True
    limit: int | None = None


settings = SimulatorSettings()
