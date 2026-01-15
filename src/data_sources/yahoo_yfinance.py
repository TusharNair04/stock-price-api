"""
Yahoo Finance data source using yfinance library.
Primary data source for stock quotes and historical data.
"""

import time
from datetime import date, datetime

import yfinance as yf
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import settings
from src.core.models import HistoricalBar, Quote


class YFinanceError(Exception):
    """Custom exception for yfinance-related errors."""
    pass


class YFinanceDataSource:
    """Yahoo Finance data source using yfinance library."""

    def __init__(self):
        self.rate_limit = settings.rate_limit_requests_per_second
        self._last_request_time: float | None = None

    def _rate_limit_wait(self) -> None:
        """Enforce rate limiting between requests."""
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            min_interval = 1.0 / self.rate_limit
            if elapsed < min_interval:
                sleep_time = min_interval - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True,
    )
    def get_latest_quote(self, ticker: str) -> Quote:
        """
        Get the latest quote for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')

        Returns:
            Quote object with current price data

        Raises:
            YFinanceError: If data cannot be retrieved
        """
        self._rate_limit_wait()

        try:
            ticker_obj = yf.Ticker(ticker)

            # Get recent history to get the latest price
            hist = ticker_obj.history(period="1d")

            if hist.empty:
                raise YFinanceError(f"No data available for ticker: {ticker}")

            last_row = hist.iloc[-1]

            # Get additional info
            try:
                fast_info = ticker_obj.fast_info
                currency = getattr(fast_info, 'currency', 'USD') or 'USD'
                market_cap = getattr(fast_info, 'market_cap', None)
            except Exception:
                currency = 'USD'
                market_cap = None

            # Calculate change if we have enough data
            change = None
            change_percent = None
            if len(hist) >= 1:
                try:
                    prev_close = float(last_row.get('Open', last_row['Close']))
                    current = float(last_row['Close'])
                    change = current - prev_close
                    change_percent = (change / prev_close) * 100 if prev_close > 0 else None
                except Exception:
                    pass

            quote = Quote(
                ticker=ticker.upper(),
                price=float(last_row['Close']),
                currency=currency,
                timestamp=datetime.utcnow(),
                source="yfinance",
                change=change,
                change_percent=change_percent,
                volume=int(last_row['Volume']) if 'Volume' in last_row else None,
                market_cap=market_cap,
            )

            logger.info(f"Retrieved quote for {ticker}: ${quote.price:.2f} {currency}")
            return quote

        except Exception as e:
            logger.error(f"Failed to get quote for {ticker}: {e}")
            raise YFinanceError(f"Failed to get quote for {ticker}: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True,
    )
    def get_history(
        self,
        ticker: str,
        start: date | None = None,
        end: date | None = None,
        period: str = "1mo",
    ) -> list[HistoricalBar]:
        """
        Get historical OHLCV data for a ticker.

        Args:
            ticker: Stock ticker symbol
            start: Start date (optional, use period if not specified)
            end: End date (optional, defaults to today)
            period: Period string if start/end not specified
                   (e.g., '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')

        Returns:
            List of HistoricalBar objects

        Raises:
            YFinanceError: If data cannot be retrieved
        """
        self._rate_limit_wait()

        try:
            ticker_obj = yf.Ticker(ticker)

            if start and end:
                hist = ticker_obj.history(start=start, end=end)
            elif start:
                hist = ticker_obj.history(start=start)
            else:
                hist = ticker_obj.history(period=period)

            if hist.empty:
                raise YFinanceError(f"No historical data for {ticker}")

            bars = []
            for idx, row in hist.iterrows():
                bar = HistoricalBar(
                    ticker=ticker.upper(),
                    date=idx.to_pydatetime(),
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    adj_close=float(row.get('Adj Close', row['Close'])),
                    volume=int(row['Volume']),
                )
                bars.append(bar)

            logger.info(f"Retrieved {len(bars)} bars for {ticker}")
            return bars

        except Exception as e:
            logger.error(f"Failed to get history for {ticker}: {e}")
            raise YFinanceError(f"Failed to get history for {ticker}: {e}") from e

    def get_multiple_quotes(self, tickers: list[str]) -> list[Quote]:
        """
        Get latest quotes for multiple tickers.

        Args:
            tickers: List of ticker symbols

        Returns:
            List of Quote objects (failed tickers are skipped)
        """
        quotes = []
        for ticker in tickers:
            try:
                quote = self.get_latest_quote(ticker)
                quotes.append(quote)
            except YFinanceError as e:
                logger.warning(f"Skipping {ticker}: {e}")
        return quotes


# Module-level instance for convenience
yfinance_source = YFinanceDataSource()


def get_latest_quote(ticker: str) -> Quote:
    """Convenience function to get latest quote."""
    return yfinance_source.get_latest_quote(ticker)


def get_history(
    ticker: str,
    start: date | None = None,
    end: date | None = None,
    period: str = "1mo",
) -> list[HistoricalBar]:
    """Convenience function to get historical data."""
    return yfinance_source.get_history(ticker, start, end, period)
