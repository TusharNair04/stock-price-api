"""
Unified data fetcher that combines yfinance and HTML scraping.
Implements fallback logic and Gemini-assisted selector repair.
"""

import time
import uuid
from datetime import date, datetime
from typing import List, Optional, Tuple

from loguru import logger

from src.core.config import settings
from src.core.models import Quote, HistoricalBar, ScrapeMetadata
from src.data_sources.yahoo_yfinance import (
    YFinanceDataSource,
    YFinanceError,
    get_latest_quote as yf_get_quote,
    get_history as yf_get_history,
)
from src.data_sources.yahoo_html import (
    YahooHTMLScraper,
    HTMLScraperError,
    get_quote_html,
    get_html_snippet,
)


class DataFetcher:
    """
    Unified data fetcher with fallback logic.
    Tries yfinance first, falls back to HTML scraping if enabled.
    Uses Gemini for selector repair when HTML scraping fails.
    """
    
    def __init__(self):
        self.yfinance_source = YFinanceDataSource()
        self.html_scraper = YahooHTMLScraper()
        self._gemini_assistant = None
    
    @property
    def gemini_assistant(self):
        """Lazy load Gemini assistant."""
        if self._gemini_assistant is None and settings.use_gemini_assistant:
            try:
                from src.llm.scraping_assistant import scraping_assistant
                if scraping_assistant.is_available():
                    self._gemini_assistant = scraping_assistant
            except Exception as e:
                logger.warning(f"Gemini assistant not available: {e}")
        return self._gemini_assistant

    def get_quote(self, ticker: str) -> Tuple[Quote, ScrapeMetadata]:
        """
        Get latest quote for a ticker with automatic fallback.
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            Tuple of (Quote, ScrapeMetadata)
        
        Raises:
            Exception: If all methods fail
        """
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        gemini_used = False
        
        # Try yfinance first
        if settings.use_yfinance:
            try:
                quote = self.yfinance_source.get_latest_quote(ticker)
                latency = (time.time() - start_time) * 1000
                
                metadata = ScrapeMetadata(
                    request_id=request_id,
                    ticker=ticker,
                    source="yfinance",
                    latency_ms=latency,
                    success=True,
                    gemini_used=False,
                )
                
                return quote, metadata
                
            except YFinanceError as e:
                logger.warning(f"yfinance failed for {ticker}: {e}")
        
        # Try HTML scraping as fallback
        if settings.use_html_fallback:
            try:
                quote = self.html_scraper.get_quote(ticker)
                latency = (time.time() - start_time) * 1000
                
                metadata = ScrapeMetadata(
                    request_id=request_id,
                    ticker=ticker,
                    source="yahoo_html",
                    latency_ms=latency,
                    success=True,
                    gemini_used=False,
                )
                
                return quote, metadata
                
            except HTMLScraperError as e:
                logger.warning(f"HTML scraping failed for {ticker}: {e}")
                
                # Try Gemini-assisted selector repair
                if self.gemini_assistant:
                    try:
                        quote, gemini_used = self._gemini_assisted_scrape(ticker)
                        latency = (time.time() - start_time) * 1000
                        
                        metadata = ScrapeMetadata(
                            request_id=request_id,
                            ticker=ticker,
                            source="yahoo_html",
                            latency_ms=latency,
                            success=True,
                            gemini_used=True,
                        )
                        
                        return quote, metadata
                        
                    except Exception as gemini_error:
                        logger.error(f"Gemini-assisted scraping failed: {gemini_error}")
        
        # All methods failed
        latency = (time.time() - start_time) * 1000
        error_msg = f"All data sources failed for {ticker}"
        
        metadata = ScrapeMetadata(
            request_id=request_id,
            ticker=ticker,
            source="none",
            latency_ms=latency,
            success=False,
            error_message=error_msg,
            gemini_used=gemini_used,
        )
        
        raise Exception(error_msg)

    def _gemini_assisted_scrape(self, ticker: str) -> Tuple[Quote, bool]:
        """
        Attempt to scrape with Gemini-suggested selectors.
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            Tuple of (Quote, gemini_used flag)
        """
        logger.info(f"Attempting Gemini-assisted scraping for {ticker}")
        
        # Get HTML snippet for Gemini analysis
        html_snippet = self.html_scraper.get_html_snippet(ticker)
        
        # Ask Gemini to suggest selectors
        selectors = self.gemini_assistant.suggest_selectors(
            html_snippet,
            "stock price (current market price) and currency"
        )
        
        # Update scraper with new selector
        if selectors.get("price_selector"):
            self.html_scraper.update_selectors(selectors["price_selector"])
        
        # Try scraping again
        quote = self.html_scraper.get_quote(ticker)
        
        return quote, True

    def get_history(
        self,
        ticker: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
        period: str = "1mo"
    ) -> List[HistoricalBar]:
        """
        Get historical data for a ticker.
        Currently only uses yfinance as HTML scraping for history is complex.
        
        Args:
            ticker: Stock ticker symbol
            start: Start date
            end: End date  
            period: Period string if dates not specified
        
        Returns:
            List of HistoricalBar objects
        """
        return self.yfinance_source.get_history(ticker, start, end, period)

    def get_multiple_quotes(self, tickers: List[str]) -> List[Tuple[Quote, ScrapeMetadata]]:
        """
        Get quotes for multiple tickers.
        
        Args:
            tickers: List of ticker symbols
        
        Returns:
            List of (Quote, ScrapeMetadata) tuples for successful fetches
        """
        results = []
        
        for ticker in tickers:
            try:
                result = self.get_quote(ticker)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to get quote for {ticker}: {e}")
        
        return results


# Module-level instance
data_fetcher = DataFetcher()


def get_quote(ticker: str) -> Tuple[Quote, ScrapeMetadata]:
    """Convenience function to get a quote."""
    return data_fetcher.get_quote(ticker)


def get_history(
    ticker: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    period: str = "1mo"
) -> List[HistoricalBar]:
    """Convenience function to get history."""
    return data_fetcher.get_history(ticker, start, end, period)
