# tests/test_api/test_endpoints.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

from new_england_listings.api.app import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_process_listing():
    """Mock the process_listing function."""
    with patch('new_england_listings.api.app.process_listing') as mock:
        # Set up mock response
        async def mock_process(*args, **kwargs):
            return {
                "listing_name": "Test Property",
                "location": "Portland, ME",
                "price": "$500,000",
                "price_bucket": "$300K - $600K",
                "platform": "Test Platform",
                "url": kwargs.get("url", "https://example.com/test")
            }

        mock.side_effect = mock_process
        yield mock


class TestProcessListingEndpoint:
    """Tests for the /process-listing endpoint."""

    def test_process_listing_success(self, client, mock_process_listing):
        """Test successful processing of a listing."""
        test_url = "https://example.com/test-property"
        response = client.post(
            "/process-listing",
            json={"url": test_url, "use_notion": True}
        )

        # Verify response
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        assert "data" in result
        assert result["data"]["listing_name"] == "Test Property"
        assert result["data"]["url"] == test_url

        # Verify mock was called with correct parameters
        mock_process_listing.assert_called_once()
        args, kwargs = mock_process_listing.call_args
        assert kwargs["url"] == test_url
        assert kwargs["use_notion"] is True

    def test_process_listing_without_notion(self, client, mock_process_listing):
        """Test processing without Notion integration."""
        response = client.post(
            "/process-listing",
            json={"url": "https://example.com/test", "use_notion": False}
        )

        # Verify response
        assert response.status_code == 200

        # Verify mock was called with use_notion=False
        args, kwargs = mock_process_listing.call_args
        assert kwargs["use_notion"] is False

    def test_process_listing_invalid_url(self, client):
        """Test with invalid URL format."""
        response = client.post(
            "/process-listing",
            json={"url": "not-a-valid-url", "use_notion": True}
        )

        # Should return validation error
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_process_listing_missing_url(self, client):
        """Test with missing URL."""
        response = client.post(
            "/process-listing",
            json={"use_notion": True}
        )

        # Should return validation error
        assert response.status_code == 422
        assert "detail" in response.json()

    @patch('new_england_listings.api.app.process_listing')
    def test_process_listing_error(self, mock_process, client):
        """Test error handling during listing processing."""
        # Configure mock to raise exception
        mock_process.side_effect = Exception("Test error")

        response = client.post(
            "/process-listing",
            json={"url": "https://example.com/test", "use_notion": True}
        )

        # Should return 500 error
        assert response.status_code == 500
        assert "detail" in response.json()
        assert "Test error" in response.json()["detail"]


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_check(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")

        # Verify response
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestContentNegotiation:
    """Tests for content negotiation and headers."""

    def test_cors_headers(self, client):
        """Test CORS headers if implemented."""
        response = client.options(
            "/process-listing",
            headers={"Origin": "http://localhost:3000"}
        )

        # Check if CORS is implemented (if not, this test can be skipped)
        if "access-control-allow-origin" in response.headers:
            assert response.headers["access-control-allow-origin"]

    def test_accept_json(self, client, mock_process_listing):
        """Test explicit JSON content negotiation."""
        response = client.post(
            "/process-listing",
            json={"url": "https://example.com/test"},
            headers={"Accept": "application/json"}
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")


class TestAPIPerformance:
    """Performance tests for API endpoints."""

    def test_response_time(self, client, mock_process_listing):
        """Test that API responses are reasonably fast."""
        import time

        start_time = time.time()
        client.post(
            "/process-listing",
            json={"url": "https://example.com/test"}
        )
        end_time = time.time()

        # Response should be fast since we're using a mock
        assert end_time - start_time < 0.5  # Less than 500ms


# Use this conditional to enable running the tests directly
if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
