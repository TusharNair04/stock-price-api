"""
Storage module for persisting stock data.
Supports CSV and Parquet formats using pandas.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional
import pandas as pd
from loguru import logger

from .config import settings
from .models import Quote, HistoricalBar


def _ensure_data_dir() -> Path:
    """Ensure data directory exists and return path."""
    data_dir = settings.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def save_quote(quote: Quote, filename: Optional[str] = None) -> Path:
    """
    Save a quote to CSV file.
    Appends to existing file or creates new one.
    
    Args:
        quote: Quote object to save
        filename: Optional custom filename (default: quotes.csv)
    
    Returns:
        Path to the saved file
    """
    data_dir = _ensure_data_dir()
    filepath = data_dir / (filename or "quotes.csv")
    
    # Convert to DataFrame
    df = pd.DataFrame([quote.model_dump()])
    
    # Append or create
    if filepath.exists():
        df.to_csv(filepath, mode="a", header=False, index=False)
        logger.debug(f"Appended quote for {quote.ticker} to {filepath}")
    else:
        df.to_csv(filepath, index=False)
        logger.info(f"Created new quotes file at {filepath}")
    
    return filepath


def save_quotes(quotes: List[Quote], filename: Optional[str] = None) -> Path:
    """
    Save multiple quotes to CSV file.
    
    Args:
        quotes: List of Quote objects to save
        filename: Optional custom filename (default: quotes.csv)
    
    Returns:
        Path to the saved file
    """
    data_dir = _ensure_data_dir()
    filepath = data_dir / (filename or "quotes.csv")
    
    # Convert to DataFrame
    df = pd.DataFrame([q.model_dump() for q in quotes])
    
    # Append or create
    if filepath.exists():
        df.to_csv(filepath, mode="a", header=False, index=False)
    else:
        df.to_csv(filepath, index=False)
    
    logger.info(f"Saved {len(quotes)} quotes to {filepath}")
    return filepath


def load_quotes(filename: Optional[str] = None) -> List[Quote]:
    """
    Load quotes from CSV file.
    
    Args:
        filename: Optional custom filename (default: quotes.csv)
    
    Returns:
        List of Quote objects
    """
    data_dir = _ensure_data_dir()
    filepath = data_dir / (filename or "quotes.csv")
    
    if not filepath.exists():
        logger.warning(f"No quotes file found at {filepath}")
        return []
    
    df = pd.read_csv(filepath, parse_dates=["timestamp"])
    quotes = [Quote(**row) for row in df.to_dict("records")]
    logger.debug(f"Loaded {len(quotes)} quotes from {filepath}")
    return quotes


def save_history(
    bars: List[HistoricalBar],
    ticker: str,
    format: str = "csv"
) -> Path:
    """
    Save historical bars to file.
    
    Args:
        bars: List of HistoricalBar objects
        ticker: Ticker symbol (used in filename)
        format: 'csv' or 'parquet'
    
    Returns:
        Path to the saved file
    """
    data_dir = _ensure_data_dir()
    
    # Create history subdirectory
    history_dir = data_dir / "history"
    history_dir.mkdir(exist_ok=True)
    
    # Convert to DataFrame
    df = pd.DataFrame([bar.model_dump() for bar in bars])
    
    # Save based on format
    if format == "parquet":
        filepath = history_dir / f"{ticker.upper()}_history.parquet"
        df.to_parquet(filepath, index=False)
    else:
        filepath = history_dir / f"{ticker.upper()}_history.csv"
        df.to_csv(filepath, index=False)
    
    logger.info(f"Saved {len(bars)} bars for {ticker} to {filepath}")
    return filepath


def load_history(ticker: str, format: str = "csv") -> List[HistoricalBar]:
    """
    Load historical bars from file.
    
    Args:
        ticker: Ticker symbol
        format: 'csv' or 'parquet'
    
    Returns:
        List of HistoricalBar objects
    """
    data_dir = _ensure_data_dir()
    history_dir = data_dir / "history"
    
    if format == "parquet":
        filepath = history_dir / f"{ticker.upper()}_history.parquet"
        if not filepath.exists():
            return []
        df = pd.read_parquet(filepath)
    else:
        filepath = history_dir / f"{ticker.upper()}_history.csv"
        if not filepath.exists():
            return []
        df = pd.read_csv(filepath, parse_dates=["date"])
    
    bars = [HistoricalBar(**row) for row in df.to_dict("records")]
    logger.debug(f"Loaded {len(bars)} bars for {ticker} from {filepath}")
    return bars


def get_latest_quote_for_ticker(ticker: str) -> Optional[Quote]:
    """
    Get the most recent quote for a specific ticker.
    
    Args:
        ticker: Ticker symbol
    
    Returns:
        Most recent Quote or None if not found
    """
    quotes = load_quotes()
    ticker_quotes = [q for q in quotes if q.ticker.upper() == ticker.upper()]
    
    if not ticker_quotes:
        return None
    
    return max(ticker_quotes, key=lambda q: q.timestamp)
