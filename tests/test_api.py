"""
Unit tests for the FastAPI API endpoints.
"""

from unittest.mock import patch


class TestRequestValidation:
    """Tests for request validation."""

    def test_quote_valid_ticker(self, test_client, mock_data_fetcher):
        """Test valid ticker is accepted."""
        response = test_client.post("/quote", json={"ticker": "AAPL"})
        assert response.status_code == 200
        assert response.json()["ticker"] == "AAPL"

    def test_quote_ticker_lowercase_converted(self, test_client, mock_data_fetcher):
        """Test lowercase ticker is converted to uppercase."""
        response = test_client.post("/quote", json={"ticker": "aapl"})
        assert response.status_code == 200

    def test_quote_invalid_ticker_format(self, test_client):
        """Test invalid ticker format is rejected."""
        response = test_client.post("/quote", json={"ticker": "AAPL@#$"})
        assert response.status_code == 422  # Validation error

    def test_quote_ticker_too_long(self, test_client):
        """Test ticker exceeding max length is rejected."""
        response = test_client.post("/quote", json={"ticker": "ABCDEFGHIJK"})
        assert response.status_code == 422

    def test_quote_empty_ticker(self, test_client):
        """Test empty ticker is rejected."""
        response = test_client.post("/quote", json={"ticker": ""})
        assert response.status_code == 422

    def test_history_valid_period(self, test_client, mock_data_fetcher):
        """Test valid period values are accepted."""
        for period in ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]:
            response = test_client.post(
                "/history",
                json={"ticker": "AAPL", "period": period}
            )
            # May return 404 if no data, but not 422 (validation error)
            assert response.status_code in [200, 404]

    def test_history_invalid_period(self, test_client):
        """Test invalid period is rejected."""
        response = test_client.post(
            "/history",
            json={"ticker": "AAPL", "period": "invalid"}
        )
        assert response.status_code == 422

    def test_history_valid_date_format(self, test_client, mock_data_fetcher):
        """Test valid date format is accepted."""
        response = test_client.post(
            "/history",
            json={
                "ticker": "AAPL",
                "period": "1mo",
                "start": "2024-01-01",
                "end": "2024-06-01"
            }
        )
        assert response.status_code in [200, 404]

    def test_history_invalid_date_format(self, test_client):
        """Test invalid date format is rejected."""
        response = test_client.post(
            "/history",
            json={
                "ticker": "AAPL",
                "period": "1mo",
                "start": "01-01-2024"  # Wrong format
            }
        )
        assert response.status_code == 422

    def test_batch_valid_tickers(self, test_client, mock_data_fetcher):
        """Test valid ticker list is accepted."""
        response = test_client.post(
            "/batch",
            json={"tickers": ["AAPL", "MSFT", "GOOGL"]}
        )
        assert response.status_code == 200

    def test_batch_empty_list(self, test_client):
        """Test empty ticker list is rejected."""
        response = test_client.post("/batch", json={"tickers": []})
        assert response.status_code == 422

    def test_batch_too_many_tickers(self, test_client):
        """Test exceeding max tickers is rejected."""
        tickers = [f"TICK{i}" for i in range(51)]
        response = test_client.post("/batch", json={"tickers": tickers})
        assert response.status_code == 422

    def test_batch_invalid_ticker_in_list(self, test_client):
        """Test invalid ticker in list is rejected."""
        response = test_client.post(
            "/batch",
            json={"tickers": ["AAPL", "INVALID@#$", "MSFT"]}
        )
        assert response.status_code == 422


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_root_endpoint(self, test_client):
        """Test root endpoint returns API info."""
        response = test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "docs" in data

    def test_health_endpoint(self, test_client):
        """Test shallow health check."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_health_endpoint_no_external_calls(self, test_client):
        """Test health check doesn't make external calls."""
        with patch("src.data_sources.yahoo_yfinance.yf") as mock_yf:
            response = test_client.get("/health")
            assert response.status_code == 200
            # yfinance should NOT be called for shallow health check
            mock_yf.Ticker.assert_not_called()


class TestRequestTracing:
    """Tests for request ID tracing."""

    def test_request_id_in_response(self, test_client):
        """Test that response contains X-Request-ID header."""
        response = test_client.get("/health")
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0

    def test_request_id_propagated(self, test_client):
        """Test that provided request ID is propagated."""
        request_id = "custom-request-123"
        response = test_client.get(
            "/health",
            headers={"X-Request-ID": request_id}
        )
        assert response.headers["X-Request-ID"] == request_id


class TestAuthentication:
    """Tests for API key authentication."""

    def test_no_auth_when_key_not_configured(self, test_client, mock_data_fetcher):
        """Test requests work without API key when not configured."""
        response = test_client.post("/quote", json={"ticker": "AAPL"})
        assert response.status_code == 200

    def test_auth_required_when_key_configured(self, authenticated_client):
        """Test requests require API key when configured."""
        # Remove the auth header
        client = authenticated_client
        client.headers.pop("X-API-Key", None)

        response = client.post("/quote", json={"ticker": "AAPL"})
        assert response.status_code == 401

    def test_auth_with_valid_key(self, authenticated_client, mock_data_fetcher):
        """Test requests work with valid API key."""
        response = authenticated_client.post("/quote", json={"ticker": "AAPL"})
        assert response.status_code == 200

    def test_auth_with_invalid_key(self, authenticated_client):
        """Test requests fail with invalid API key."""
        authenticated_client.headers["X-API-Key"] = "wrong-key"
        response = authenticated_client.post("/quote", json={"ticker": "AAPL"})
        assert response.status_code == 401

    def test_health_no_auth_required(self, authenticated_client):
        """Test health endpoints don't require auth."""
        authenticated_client.headers.pop("X-API-Key", None)
        response = authenticated_client.get("/health")
        assert response.status_code == 200


class TestQuoteEndpoint:
    """Tests for the /quote endpoint."""

    def test_quote_success(self, test_client, mock_data_fetcher, sample_quote):
        """Test successful quote retrieval."""
        response = test_client.post("/quote", json={"ticker": "AAPL"})
        assert response.status_code == 200

        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["price"] == sample_quote.price
        assert data["currency"] == "USD"
        assert "timestamp" in data
        assert "source" in data

    def test_quote_not_found(self, test_client):
        """Test quote not found error."""
        with patch("src.app.api.data_fetcher") as mock:
            mock.get_quote.side_effect = Exception("Ticker not found")

            response = test_client.post("/quote", json={"ticker": "INVALID"})
            assert response.status_code == 404
            assert "Could not fetch quote" in response.json()["detail"]


class TestBatchEndpoint:
    """Tests for the /batch endpoint."""

    def test_batch_success(self, test_client, mock_data_fetcher):
        """Test successful batch quote retrieval."""
        response = test_client.post(
            "/batch",
            json={"tickers": ["AAPL", "MSFT"]}
        )
        assert response.status_code == 200

        data = response.json()
        assert "quotes" in data
        assert "success_count" in data
        assert "failed_tickers" in data

    def test_batch_partial_failure(self, test_client, sample_quote):
        """Test batch with some failures."""
        from src.core.models import ScrapeMetadata

        metadata = ScrapeMetadata(
            request_id="test",
            ticker="AAPL",
            source="yfinance",
            latency_ms=100.0,
            success=True,
            gemini_used=False,
        )

        with patch("src.app.api.data_fetcher") as mock:
            # Only return one quote
            mock.get_multiple_quotes.return_value = [(sample_quote, metadata)]

            response = test_client.post(
                "/batch",
                json={"tickers": ["AAPL", "INVALID"]}
            )
            assert response.status_code == 200

            data = response.json()
            assert data["success_count"] == 1
            assert "INVALID" in data["failed_tickers"]
