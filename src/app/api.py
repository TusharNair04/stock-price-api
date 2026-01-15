"""
FastAPI REST API for the Yahoo Finance Stock Scraper.
Provides endpoints for quotes, history, and batch processing.
"""

import os
import re
import uuid
from datetime import datetime
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from src.app.data_fetcher import data_fetcher
from src.core.models import HistoricalBar

# ============================================================================
# Configuration
# ============================================================================

API_KEY = os.environ.get("API_KEY")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "").split(",") if os.environ.get("CORS_ORIGINS") else ["*"]


# ============================================================================
# Enums for Validation
# ============================================================================

class PeriodEnum(str, Enum):
    """Valid period values for historical data."""
    ONE_DAY = "1d"
    FIVE_DAYS = "5d"
    ONE_MONTH = "1mo"
    THREE_MONTHS = "3mo"
    SIX_MONTHS = "6mo"
    ONE_YEAR = "1y"
    TWO_YEARS = "2y"
    FIVE_YEARS = "5y"
    TEN_YEARS = "10y"
    YTD = "ytd"
    MAX = "max"


# ============================================================================
# Request Models (Payloads) with Validation
# ============================================================================

TICKER_PATTERN = re.compile(r"^[A-Za-z0-9.\-]{1,10}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class QuoteRequest(BaseModel):
    """Request payload for getting a quote."""
    ticker: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Stock symbol (e.g., AAPL, MSFT, GOOGL)"
    )

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        if not TICKER_PATTERN.match(v):
            raise ValueError("Ticker must be 1-10 alphanumeric characters, dots, or hyphens")
        return v.upper()

    class Config:
        json_schema_extra = {
            "example": {"ticker": "AAPL"}
        }


class HistoryRequest(BaseModel):
    """Request payload for getting historical data."""
    ticker: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Stock symbol (e.g., AAPL)"
    )
    period: PeriodEnum = Field(
        default=PeriodEnum.ONE_MONTH,
        description="Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max"
    )
    start: str | None = Field(
        default=None,
        description="Start date (YYYY-MM-DD)"
    )
    end: str | None = Field(
        default=None,
        description="End date (YYYY-MM-DD)"
    )

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        if not TICKER_PATTERN.match(v):
            raise ValueError("Ticker must be 1-10 alphanumeric characters, dots, or hyphens")
        return v.upper()

    @field_validator("start", "end")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        if v is not None and not DATE_PATTERN.match(v):
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "AAPL",
                "period": "1mo",
                "start": None,
                "end": None
            }
        }


class BatchRequest(BaseModel):
    """Request payload for batch quotes."""
    tickers: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of stock symbols (max 50)"
    )

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, v: list[str]) -> list[str]:
        validated = []
        for ticker in v:
            ticker = ticker.strip()
            if not TICKER_PATTERN.match(ticker):
                raise ValueError(f"Invalid ticker format: {ticker}")
            validated.append(ticker.upper())
        return validated

    class Config:
        json_schema_extra = {
            "example": {"tickers": ["AAPL", "MSFT", "GOOGL"]}
        }


# ============================================================================
# Response Models
# ============================================================================

class QuoteResponse(BaseModel):
    """API response for a single quote."""
    ticker: str
    price: float
    currency: str
    timestamp: datetime
    source: str
    change: float | None = None
    change_percent: float | None = None
    volume: int | None = None
    market_cap: float | None = None


class HistoryResponse(BaseModel):
    """API response for historical data."""
    ticker: str
    bars: list[HistoricalBar]
    count: int
    start_date: datetime | None = None
    end_date: datetime | None = None


class BatchQuoteResponse(BaseModel):
    """API response for batch quotes."""
    quotes: list[QuoteResponse]
    success_count: int
    failed_tickers: list[str]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime


class DeepHealthResponse(BaseModel):
    """Deep health check response with dependency status."""
    status: str
    yfinance: bool
    gemini: bool
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
    request_id: str | None = None


# ============================================================================
# Security
# ============================================================================

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Depends(api_key_header)) -> str | None:
    """Verify API key if configured."""
    if not API_KEY:
        # No API key configured, allow all requests
        return None

    if not api_key or api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )
    return api_key


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Stock Price API with AI Scraping",
    description="REST API for fetching stock quotes and historical data with AI-powered selector maintenance",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ============================================================================
# Request ID Middleware
# ============================================================================

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to each request for tracing."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])

    # Add to request state
    request.state.request_id = request_id

    # Log request
    logger.info(f"[{request_id}] {request.method} {request.url.path}")

    # Process request
    response = await call_next(request)

    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id

    return response


# ============================================================================
# Health Check Endpoints
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Stock Price API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Shallow health check - fast, no external dependencies.
    Use /health/deep for full dependency check.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
    )


@app.get("/health/deep", response_model=DeepHealthResponse, tags=["Health"])
async def deep_health_check():
    """
    Deep health check - verifies all external dependencies.
    May be slow, use sparingly.
    """
    from src.core.config import settings

    # Check yfinance
    yfinance_ok = False
    try:
        from src.data_sources.yahoo_yfinance import get_latest_quote
        get_latest_quote("AAPL")
        yfinance_ok = True
    except Exception:
        pass

    # Check Gemini
    gemini_ok = False
    if settings.gemini_api_key:
        try:
            from src.llm.gemini_client import gemini_client
            gemini_ok = gemini_client.is_available()
        except Exception:
            pass

    status = "healthy" if yfinance_ok else "degraded"

    return DeepHealthResponse(
        status=status,
        yfinance=yfinance_ok,
        gemini=gemini_ok,
        timestamp=datetime.utcnow(),
    )


# ============================================================================
# Protected Endpoints
# ============================================================================

@app.post(
    "/quote",
    response_model=QuoteResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["Quotes"],
)
async def get_quote(
    request: QuoteRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Get the latest quote for a stock ticker.

    **Payload:**
    - **ticker**: Stock symbol (e.g., AAPL, MSFT, GOOGL)
    """
    try:
        quote, metadata = data_fetcher.get_quote(request.ticker)

        return QuoteResponse(
            ticker=quote.ticker,
            price=quote.price,
            currency=quote.currency,
            timestamp=quote.timestamp,
            source=quote.source,
            change=quote.change,
            change_percent=quote.change_percent,
            volume=quote.volume,
            market_cap=quote.market_cap,
        )
    except Exception as e:
        logger.error(f"Failed to get quote for {request.ticker}: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch quote for {request.ticker}: {str(e)}"
        ) from e


@app.post(
    "/history",
    response_model=HistoryResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["History"],
)
async def get_history(
    request: HistoryRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Get historical OHLCV data for a stock ticker.

    **Payload:**
    - **ticker**: Stock symbol (e.g., AAPL)
    - **period**: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
    - **start**: Optional start date (YYYY-MM-DD)
    - **end**: Optional end date (YYYY-MM-DD)
    """
    try:
        # Parse dates if provided
        start_date = None
        end_date = None

        if request.start:
            start_date = datetime.strptime(request.start, "%Y-%m-%d").date()
        if request.end:
            end_date = datetime.strptime(request.end, "%Y-%m-%d").date()

        bars = data_fetcher.get_history(
            request.ticker,
            start=start_date,
            end=end_date,
            period=request.period.value
        )

        if not bars:
            raise HTTPException(
                status_code=404,
                detail=f"No historical data found for {request.ticker}"
            )

        return HistoryResponse(
            ticker=request.ticker,
            bars=bars,
            count=len(bars),
            start_date=bars[0].date if bars else None,
            end_date=bars[-1].date if bars else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get history for {request.ticker}: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch history for {request.ticker}: {str(e)}"
        ) from e


@app.post(
    "/batch",
    response_model=BatchQuoteResponse,
    responses={401: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
    tags=["Quotes"],
)
async def get_batch_quotes(
    request: BatchRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Get quotes for multiple stock tickers in a single request.

    **Payload:**
    - **tickers**: List of stock symbols (max 50)
    """
    if not request.tickers:
        raise HTTPException(status_code=400, detail="No valid tickers provided")

    results = data_fetcher.get_multiple_quotes(request.tickers)

    quotes = []
    successful_tickers = set()

    for quote, _metadata in results:
        successful_tickers.add(quote.ticker)
        quotes.append(QuoteResponse(
            ticker=quote.ticker,
            price=quote.price,
            currency=quote.currency,
            timestamp=quote.timestamp,
            source=quote.source,
            change=quote.change,
            change_percent=quote.change_percent,
            volume=quote.volume,
            market_cap=quote.market_cap,
        ))

    failed_tickers = [t for t in request.tickers if t not in successful_tickers]

    return BatchQuoteResponse(
        quotes=quotes,
        success_count=len(quotes),
        failed_tickers=failed_tickers,
    )


@app.post(
    "/save",
    responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Storage"],
)
async def save_quote(
    request: QuoteRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Fetch and save a quote to the data store.

    **Payload:**
    - **ticker**: Stock symbol to fetch and save
    """
    from src.core.storage import save_quote as store_quote

    try:
        quote, metadata = data_fetcher.get_quote(request.ticker)
        filepath = store_quote(quote)

        return {
            "message": f"Quote saved for {request.ticker}",
            "ticker": quote.ticker,
            "price": quote.price,
            "filepath": str(filepath),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save quote: {str(e)}"
        ) from e


# ============================================================================
# Run with: uvicorn src.app.api:app --reload
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
