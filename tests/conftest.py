"""
Pytest fixtures for testing the Stock Price API.
"""

import os
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.core.models import HistoricalBar, Quote


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    # Ensure no API key requirement for tests
    os.environ.pop("API_KEY", None)

    from src.app.api import app
    return TestClient(app)


@pytest.fixture
def authenticated_client():
    """Create a test client with API key authentication."""
    os.environ["API_KEY"] = "test-api-key"

    from importlib import reload

    import src.app.api
    reload(src.app.api)

    from src.app.api import app
    client = TestClient(app)
    client.headers["X-API-Key"] = "test-api-key"

    yield client

    # Cleanup
    os.environ.pop("API_KEY", None)
    reload(src.app.api)


@pytest.fixture
def sample_quote():
    """Create a sample Quote for testing."""
    return Quote(
        ticker="AAPL",
        price=150.50,
        currency="USD",
        timestamp=datetime.utcnow(),
        source="yfinance",
        change=2.50,
        change_percent=1.69,
        volume=50000000,
        market_cap=2500000000000,
    )


@pytest.fixture
def sample_historical_bar():
    """Create a sample HistoricalBar for testing."""
    return HistoricalBar(
        ticker="AAPL",
        date=datetime(2024, 1, 15),
        open=148.00,
        high=151.00,
        low=147.50,
        close=150.50,
        adj_close=150.50,
        volume=50000000,
    )


@pytest.fixture
def mock_data_fetcher(sample_quote):
    """Mock the data fetcher for API tests."""
    from src.core.models import ScrapeMetadata

    metadata = ScrapeMetadata(
        request_id="test123",
        ticker="AAPL",
        source="yfinance",
        latency_ms=100.0,
        success=True,
        gemini_used=False,
    )

    with patch("src.app.api.data_fetcher") as mock:
        mock.get_quote.return_value = (sample_quote, metadata)
        mock.get_multiple_quotes.return_value = [(sample_quote, metadata)]
        mock.get_history.return_value = []
        yield mock


@pytest.fixture
def mock_yfinance():
    """Mock yfinance for unit tests."""
    with patch("src.data_sources.yahoo_yfinance.yf") as mock:
        yield mock
