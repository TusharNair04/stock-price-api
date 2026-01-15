"""
Integration tests for the data fetcher and data sources.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.app.data_fetcher import DataFetcher
from src.core.models import Quote
from src.data_sources.yahoo_yfinance import YFinanceDataSource, YFinanceError


class TestYFinanceDataSource:
    """Integration tests for yfinance data source."""

    def test_get_quote_with_mock(self, mock_yfinance):
        """Test quote retrieval with mocked yfinance."""
        # Setup mock
        mock_ticker = MagicMock()
        mock_yfinance.Ticker.return_value = mock_ticker

        mock_hist = pd.DataFrame({
            "Open": [148.0],
            "High": [151.0],
            "Low": [147.5],
            "Close": [150.5],
            "Volume": [50000000],
        }, index=pd.DatetimeIndex([datetime(2024, 1, 15)]))

        mock_ticker.history.return_value = mock_hist
        mock_ticker.fast_info = MagicMock()
        mock_ticker.fast_info.currency = "USD"
        mock_ticker.fast_info.market_cap = 2500000000000

        # Test
        source = YFinanceDataSource()
        quote = source.get_latest_quote("AAPL")

        assert quote.ticker == "AAPL"
        assert quote.price == 150.5
        assert quote.currency == "USD"
        assert quote.source == "yfinance"

    def test_get_quote_empty_data(self, mock_yfinance):
        """Test handling of empty data from yfinance."""
        mock_ticker = MagicMock()
        mock_yfinance.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = pd.DataFrame()

        source = YFinanceDataSource()

        with pytest.raises(YFinanceError) as exc_info:
            source.get_latest_quote("INVALID")

        assert "No data available" in str(exc_info.value)

    def test_get_history_with_mock(self, mock_yfinance):
        """Test history retrieval with mocked yfinance."""
        mock_ticker = MagicMock()
        mock_yfinance.Ticker.return_value = mock_ticker

        dates = pd.date_range(start="2024-01-01", periods=5, freq="D")
        mock_hist = pd.DataFrame({
            "Open": [148.0, 149.0, 150.0, 151.0, 152.0],
            "High": [151.0, 152.0, 153.0, 154.0, 155.0],
            "Low": [147.0, 148.0, 149.0, 150.0, 151.0],
            "Close": [150.0, 151.0, 152.0, 153.0, 154.0],
            "Adj Close": [150.0, 151.0, 152.0, 153.0, 154.0],
            "Volume": [1000000, 1100000, 1200000, 1300000, 1400000],
        }, index=dates)

        mock_ticker.history.return_value = mock_hist

        source = YFinanceDataSource()
        bars = source.get_history("AAPL", period="5d")

        assert len(bars) == 5
        assert bars[0].ticker == "AAPL"
        assert bars[0].close == 150.0
        assert bars[-1].close == 154.0


class TestDataFetcher:
    """Integration tests for the unified data fetcher."""

    def test_fetcher_uses_yfinance_first(self, mock_yfinance):
        """Test that fetcher tries yfinance first."""
        mock_ticker = MagicMock()
        mock_yfinance.Ticker.return_value = mock_ticker

        mock_hist = pd.DataFrame({
            "Open": [148.0],
            "High": [151.0],
            "Low": [147.5],
            "Close": [150.5],
            "Volume": [50000000],
        }, index=pd.DatetimeIndex([datetime(2024, 1, 15)]))

        mock_ticker.history.return_value = mock_hist
        mock_ticker.fast_info = MagicMock()
        mock_ticker.fast_info.currency = "USD"
        mock_ticker.fast_info.market_cap = None

        fetcher = DataFetcher()
        quote, metadata = fetcher.get_quote("AAPL")

        assert quote.source == "yfinance"
        assert metadata.success is True
        assert metadata.gemini_used is False

    def test_fetcher_fallback_to_html(self):
        """Test fallback to HTML scraping when yfinance fails."""
        from src.data_sources.yahoo_yfinance import YFinanceError

        fetcher = DataFetcher()

        # Mock the instance methods directly
        with patch.object(fetcher.yfinance_source, 'get_latest_quote') as mock_yf:
            mock_yf.side_effect = YFinanceError("yfinance failed")

            with patch.object(fetcher.html_scraper, 'get_quote') as mock_html:
                mock_quote = Quote(
                    ticker="AAPL",
                    price=150.0,
                    currency="USD",
                    timestamp=datetime.utcnow(),
                    source="yahoo_html",
                )
                mock_html.return_value = mock_quote

                quote, metadata = fetcher.get_quote("AAPL")

                assert quote.source == "yahoo_html"
                assert metadata.success is True

    def test_fetcher_all_sources_fail(self):
        """Test error when all data sources fail."""
        from src.data_sources.yahoo_html import HTMLScraperError
        from src.data_sources.yahoo_yfinance import YFinanceError

        fetcher = DataFetcher()

        with patch.object(fetcher.yfinance_source, 'get_latest_quote') as mock_yf:
            mock_yf.side_effect = YFinanceError("yfinance failed")

            with patch.object(fetcher.html_scraper, 'get_quote') as mock_html:
                mock_html.side_effect = HTMLScraperError("HTML failed")

                with pytest.raises(Exception) as exc_info:
                    fetcher.get_quote("AAPL")

                assert "All data sources failed" in str(exc_info.value)

    def test_fetcher_multiple_quotes(self, mock_yfinance):
        """Test fetching multiple quotes."""
        mock_ticker = MagicMock()
        mock_yfinance.Ticker.return_value = mock_ticker

        mock_hist = pd.DataFrame({
            "Open": [148.0],
            "High": [151.0],
            "Low": [147.5],
            "Close": [150.5],
            "Volume": [50000000],
        }, index=pd.DatetimeIndex([datetime(2024, 1, 15)]))

        mock_ticker.history.return_value = mock_hist
        mock_ticker.fast_info = MagicMock()
        mock_ticker.fast_info.currency = "USD"
        mock_ticker.fast_info.market_cap = None

        fetcher = DataFetcher()
        results = fetcher.get_multiple_quotes(["AAPL", "MSFT"])

        # Should get 2 results (mock returns same data for all)
        assert len(results) == 2


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_rate_limit_applied(self, mock_yfinance):
        """Test that rate limiting is applied between requests."""
        import time

        mock_ticker = MagicMock()
        mock_yfinance.Ticker.return_value = mock_ticker

        mock_hist = pd.DataFrame({
            "Open": [148.0],
            "High": [151.0],
            "Low": [147.5],
            "Close": [150.5],
            "Volume": [50000000],
        }, index=pd.DatetimeIndex([datetime(2024, 1, 15)]))

        mock_ticker.history.return_value = mock_hist
        mock_ticker.fast_info = MagicMock()
        mock_ticker.fast_info.currency = "USD"
        mock_ticker.fast_info.market_cap = None

        source = YFinanceDataSource()

        # Make two requests and measure time
        start = time.time()
        source.get_latest_quote("AAPL")
        source.get_latest_quote("MSFT")
        elapsed = time.time() - start

        # Should take at least rate_limit interval between requests
        # (default is 1 req/sec, so at least ~1 second)
        assert elapsed >= 0.5  # Allow some tolerance
