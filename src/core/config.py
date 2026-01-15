"""
Configuration module for the Yahoo Finance Stock Scraper.
Loads environment variables and provides settings for the application.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Load .env file from project root
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


def _get_default_data_dir() -> Path:
    """Get default data directory, using /tmp for Lambda environments."""
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return Path("/tmp/data")
    return Path("data")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")

    # Database
    db_url: str = Field(default="sqlite:///./data/data.db", alias="DB_URL")

    # Rate limiting
    rate_limit_requests_per_second: float = Field(
        default=1.0, alias="RATE_LIMIT_REQUESTS_PER_SECOND"
    )

    # Feature flags
    use_yfinance: bool = Field(default=True, alias="USE_YFINANCE")
    use_html_fallback: bool = Field(default=True, alias="USE_HTML_FALLBACK")
    use_gemini_assistant: bool = Field(default=True, alias="USE_GEMINI_ASSISTANT")

    # Data storage paths - use /tmp in Lambda
    data_dir: Path = Field(default_factory=_get_default_data_dir)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
settings = Settings()
