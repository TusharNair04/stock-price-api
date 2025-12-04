"""
FastAPI REST API for the Yahoo Finance Stock Scraper.
Provides endpoints for quotes, history, and batch processing.
"""

from datetime import date, datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from loguru import logger

from src.core.models import Quote, HistoricalBar
from src.app.data_fetcher import data_fetcher


# ============================================================================
# API Response Models
# ============================================================================

class QuoteResponse(BaseModel):
    """API response for a single quote."""
    ticker: str
    price: float
    currency: str
    timestamp: datetime
    source: str
    change: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[int] = None
    market_cap: Optional[float] = None


class HistoryResponse(BaseModel):
    """API response for historical data."""
    ticker: str
    bars: List[HistoricalBar]
    count: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class BatchQuoteResponse(BaseModel):
    """API response for batch quotes."""
    quotes: List[QuoteResponse]
    success_count: int
    failed_tickers: List[str]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    yfinance: bool
    gemini: bool
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
    ticker: Optional[str] = None


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

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Yahoo Finance Stock Scraper API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Check API health and service availability."""
    from src.core.config import settings
    
    # Check yfinance
    yfinance_ok = False
    try:
        from src.data_sources.yahoo_yfinance import get_latest_quote
        quote = get_latest_quote("AAPL")
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
    
    return HealthResponse(
        status="healthy" if yfinance_ok else "degraded",
        yfinance=yfinance_ok,
        gemini=gemini_ok,
        timestamp=datetime.utcnow(),
    )


@app.get(
    "/quote/{ticker}",
    response_model=QuoteResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["Quotes"],
)
async def get_quote(ticker: str):
    """
    Get the latest quote for a stock ticker.
    
    - **ticker**: Stock symbol (e.g., AAPL, MSFT, GOOGL)
    """
    try:
        quote, metadata = data_fetcher.get_quote(ticker.upper())
        
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
        logger.error(f"Failed to get quote for {ticker}: {e}")
        raise HTTPException(status_code=404, detail=f"Could not fetch quote for {ticker}: {str(e)}")


@app.get(
    "/history/{ticker}",
    response_model=HistoryResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["History"],
)
async def get_history(
    ticker: str,
    period: str = Query(default="1mo", description="Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max"),
    start: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD)"),
):
    """
    Get historical OHLCV data for a stock ticker.
    
    - **ticker**: Stock symbol (e.g., AAPL)
    - **period**: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max)
    - **start**: Optional start date (YYYY-MM-DD)
    - **end**: Optional end date (YYYY-MM-DD)
    """
    try:
        # Parse dates if provided
        start_date = None
        end_date = None
        
        if start:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
        if end:
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
        
        bars = data_fetcher.get_history(
            ticker.upper(),
            start=start_date,
            end=end_date,
            period=period
        )
        
        if not bars:
            raise HTTPException(status_code=404, detail=f"No historical data found for {ticker}")
        
        return HistoryResponse(
            ticker=ticker.upper(),
            bars=bars,
            count=len(bars),
            start_date=bars[0].date if bars else None,
            end_date=bars[-1].date if bars else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get history for {ticker}: {e}")
        raise HTTPException(status_code=404, detail=f"Could not fetch history for {ticker}: {str(e)}")


@app.get(
    "/batch",
    response_model=BatchQuoteResponse,
    tags=["Quotes"],
)
async def get_batch_quotes(
    tickers: str = Query(..., description="Comma-separated list of tickers (e.g., AAPL,MSFT,GOOGL)")
):
    """
    Get quotes for multiple stock tickers in a single request.
    
    - **tickers**: Comma-separated list of stock symbols
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    
    if not ticker_list:
        raise HTTPException(status_code=400, detail="No valid tickers provided")
    
    if len(ticker_list) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 tickers per request")
    
    results = data_fetcher.get_multiple_quotes(ticker_list)
    
    quotes = []
    successful_tickers = set()
    
    for quote, metadata in results:
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
    
    failed_tickers = [t for t in ticker_list if t not in successful_tickers]
    
    return BatchQuoteResponse(
        quotes=quotes,
        success_count=len(quotes),
        failed_tickers=failed_tickers,
    )


@app.post("/quote/{ticker}/save", tags=["Storage"])
async def save_quote(ticker: str):
    """
    Fetch and save a quote to the data store.
    
    - **ticker**: Stock symbol to fetch and save
    """
    from src.core.storage import save_quote as store_quote
    
    try:
        quote, metadata = data_fetcher.get_quote(ticker.upper())
        filepath = store_quote(quote)
        
        return {
            "message": f"Quote saved for {ticker}",
            "ticker": quote.ticker,
            "price": quote.price,
            "filepath": str(filepath),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save quote: {str(e)}")


# ============================================================================
# Run with: uvicorn src.app.api:app --reload
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
