"""
Configuration module for the Yahoo Finance Stock Scraper.
Loads environment variables and provides settings for the application.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Load .env file from project root
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")

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

    # Data storage paths
    data_dir: Path = Field(default=Path("data"))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
