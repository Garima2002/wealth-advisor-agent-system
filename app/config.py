"""Application configuration using Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # General App Config
    APP_NAME: str = "Wealth Advisor Multi-Agent System"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # CRM Service Config
    CRM_TIMEOUT_SECONDS: float = 2.0
    CRM_MAX_RETRIES: int = 3
    CRM_RETRY_BACKOFF_FACTOR: float = 0.2

    # Financial & Anomaly Detection Thresholds
    ANOMALY_LARGE_TX_THRESHOLD: float = Field(
        default=5000.0,
        description="Transactions exceeding this value are flagged for review."
    )
    ANOMALY_CATEGORY_MULTIPLIER: float = Field(
        default=3.0,
        description="Transactions exceeding N times category mean are flagged."
    )
    ANOMALY_CATEGORY_MIN_SAMPLES: int = Field(
        default=3,
        description="Minimum transactions required in category to evaluate outlier multiplier."
    )
    ANOMALY_SPENDING_SPIKE_RATIO: float = Field(
        default=1.5,
        description="Spending period spike threshold vs baseline (1.5 = +50%)."
    )
    ANOMALY_DUPLICATE_WINDOW_HOURS: int = Field(
        default=48,
        description="Window in hours to evaluate duplicate transaction candidates."
    )
    PORTFOLIO_CONCENTRATION_THRESHOLD: float = Field(
        default=0.60,
        description="Asset class share > 60% flags portfolio concentration risk."
    )

    # Long-term Memory / Database Config
    SQLITE_DB_PATH: str = "wealth_advisor.db"
    RETENTION_DAYS: int = 90
    MAX_HISTORICAL_RECORDS_PER_CLIENT: int = 50


settings = Settings()
