"""
Pydantic models for stock data.
Defines Quote, HistoricalBar, and ScrapeMetadata models.
"""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Quote(BaseModel):
    """Live stock quote data."""

    ticker: str = Field(..., description="Stock ticker symbol (e.g., AAPL)")
    price: float = Field(..., ge=0, description="Current stock price")
    currency: str = Field(default="USD", description="Currency code")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Quote timestamp"
    )
    source: Literal["yfinance", "yahoo_html"] = Field(
        ..., description="Data source used"
    )

    change: Optional[float] = Field(default=None, description="Price change")
    change_percent: Optional[float] = Field(
        default=None, description="Price change percentage"
    )
    volume: Optional[int] = Field(default=None, description="Trading volume")
    market_cap: Optional[float] = Field(default=None, description="Market capitalization")


class HistoricalBar(BaseModel):
    """OHLCV candlestick bar data."""

    ticker: str = Field(..., description="Stock ticker symbol")
    date: datetime = Field(..., description="Bar date")
    open: float = Field(..., ge=0, description="Opening price")
    high: float = Field(..., ge=0, description="Highest price")
    low: float = Field(..., ge=0, description="Lowest price")
    close: float = Field(..., ge=0, description="Closing price")
    adj_close: float = Field(..., ge=0, description="Adjusted closing price")
    volume: int = Field(..., ge=0, description="Trading volume")


class ScrapeMetadata(BaseModel):
    """Metadata for tracking scrape requests."""

    request_id: str = Field(..., description="Unique request identifier")
    ticker: str = Field(..., description="Ticker being scraped")
    source: str = Field(..., description="Data source")
    latency_ms: float = Field(..., ge=0, description="Request latency in milliseconds")
    success: bool = Field(..., description="Whether the request succeeded")
    error_message: Optional[str] = Field(
        default=None, description="Error message if failed"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Request timestamp"
    )
    gemini_used: bool = Field(
        default=False, description="Whether Gemini was used for selector repair"
    )
