"""
Unit tests for Pydantic models.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.core.models import HistoricalBar, Quote, ScrapeMetadata


class TestQuoteModel:
    """Tests for the Quote model."""

    def test_valid_quote(self):
        """Test creating a valid Quote."""
        quote = Quote(
            ticker="AAPL",
            price=150.50,
            currency="USD",
            timestamp=datetime.utcnow(),
            source="yfinance",
        )
        assert quote.ticker == "AAPL"
        assert quote.price == 150.50
        assert quote.currency == "USD"
        assert quote.source == "yfinance"

    def test_quote_with_optional_fields(self):
        """Test Quote with all optional fields."""
        quote = Quote(
            ticker="MSFT",
            price=400.00,
            currency="USD",
            timestamp=datetime.utcnow(),
            source="yahoo_html",
            change=5.00,
            change_percent=1.25,
            volume=10000000,
            market_cap=3000000000000,
        )
        assert quote.change == 5.00
        assert quote.change_percent == 1.25
        assert quote.volume == 10000000
        assert quote.market_cap == 3000000000000

    def test_quote_negative_price_fails(self):
        """Test that negative price is rejected."""
        with pytest.raises(ValidationError):
            Quote(
                ticker="AAPL",
                price=-10.00,
                currency="USD",
                timestamp=datetime.utcnow(),
                source="yfinance",
            )

    def test_quote_invalid_source_fails(self):
        """Test that invalid source is rejected."""
        with pytest.raises(ValidationError):
            Quote(
                ticker="AAPL",
                price=150.00,
                currency="USD",
                timestamp=datetime.utcnow(),
                source="invalid_source",
            )

    def test_quote_default_timestamp(self):
        """Test that timestamp defaults to now."""
        quote = Quote(
            ticker="AAPL",
            price=150.00,
            currency="USD",
            source="yfinance",
        )
        assert quote.timestamp is not None
        assert isinstance(quote.timestamp, datetime)


class TestHistoricalBarModel:
    """Tests for the HistoricalBar model."""

    def test_valid_bar(self):
        """Test creating a valid HistoricalBar."""
        bar = HistoricalBar(
            ticker="AAPL",
            date=datetime(2024, 1, 15),
            open=148.00,
            high=151.00,
            low=147.50,
            close=150.50,
            adj_close=150.50,
            volume=50000000,
        )
        assert bar.ticker == "AAPL"
        assert bar.open == 148.00
        assert bar.high == 151.00
        assert bar.low == 147.50
        assert bar.close == 150.50
        assert bar.volume == 50000000

    def test_bar_negative_values_fail(self):
        """Test that negative OHLC values are rejected."""
        with pytest.raises(ValidationError):
            HistoricalBar(
                ticker="AAPL",
                date=datetime(2024, 1, 15),
                open=-1.00,
                high=151.00,
                low=147.50,
                close=150.50,
                adj_close=150.50,
                volume=50000000,
            )

    def test_bar_negative_volume_fails(self):
        """Test that negative volume is rejected."""
        with pytest.raises(ValidationError):
            HistoricalBar(
                ticker="AAPL",
                date=datetime(2024, 1, 15),
                open=148.00,
                high=151.00,
                low=147.50,
                close=150.50,
                adj_close=150.50,
                volume=-1000,
            )


class TestScrapeMetadataModel:
    """Tests for the ScrapeMetadata model."""

    def test_valid_metadata(self):
        """Test creating valid ScrapeMetadata."""
        metadata = ScrapeMetadata(
            request_id="abc123",
            ticker="AAPL",
            source="yfinance",
            latency_ms=150.5,
            success=True,
        )
        assert metadata.request_id == "abc123"
        assert metadata.success is True
        assert metadata.gemini_used is False  # default

    def test_metadata_with_error(self):
        """Test ScrapeMetadata with error message."""
        metadata = ScrapeMetadata(
            request_id="abc123",
            ticker="INVALID",
            source="none",
            latency_ms=50.0,
            success=False,
            error_message="Ticker not found",
        )
        assert metadata.success is False
        assert metadata.error_message == "Ticker not found"

    def test_metadata_negative_latency_fails(self):
        """Test that negative latency is rejected."""
        with pytest.raises(ValidationError):
            ScrapeMetadata(
                request_id="abc123",
                ticker="AAPL",
                source="yfinance",
                latency_ms=-10.0,
                success=True,
            )
