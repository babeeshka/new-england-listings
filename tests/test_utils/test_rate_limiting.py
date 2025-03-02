# tests/test_utils/test_rate_limiting.py
import pytest
from unittest.mock import patch, MagicMock
import time
import asyncio
import os
import tempfile
import json

from new_england_listings.utils.rate_limiting import (
    RateLimitExceeded,
    DomainRateLimiter,
    RateLimiter,
    rate_limiter
)


class TestDomainRateLimiter:
    """Tests for the DomainRateLimiter class which limits requests for a specific domain."""

    def test_init(self):
        """Test initialization with default values."""
        limiter = DomainRateLimiter()
        assert limiter.rpm == 30  # Default RPM
        assert isinstance(limiter.request_times, list)
        assert len(limiter.request_times) == 0

    def test_init_custom_rpm(self):
        """Test initialization with custom requests per minute."""
        limiter = DomainRateLimiter(requests_per_minute=10)
        assert limiter.rpm == 10

    def test_can_request_initial(self):
        """Test that initial requests are allowed."""
        limiter = DomainRateLimiter(requests_per_minute=5)
        assert limiter.can_request() is True

    def test_can_request_under_limit(self):
        """Test that requests under the limit are allowed."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record some requests
        for _ in range(3):
            limiter.record_request()

        # Should still be able to make requests
        assert limiter.can_request() is True

    def test_can_request_at_limit(self):
        """Test that requests at the limit are not allowed."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record up to the limit
        for _ in range(5):
            limiter.record_request()

        # Should not be able to make more requests
        assert limiter.can_request() is False

    def test_clean_old_requests(self):
        """Test that old requests are cleaned out."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Add some artificially old requests
        old_time = time.time() - 61  # Just over a minute old
        limiter.request_times = [old_time, old_time, old_time]

        # Add some new requests
        limiter.record_request()
        limiter.record_request()

        # Clean old requests and check we can still make requests
        limiter._clean_old_requests()
        assert len(limiter.request_times) == 2
        assert limiter.can_request() is True

    @patch('time.sleep')
    def test_wait_if_needed_no_wait(self, mock_sleep):
        """Test that wait_if_needed doesn't wait if under limit."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record some requests but stay under limit
        for _ in range(3):
            limiter.record_request()

        # Wait if needed
        limiter.wait_if_needed()

        # Verify sleep was not called
        mock_sleep.assert_not_called()

    @patch('time.sleep')
    def test_wait_if_needed_with_wait(self, mock_sleep):
        """Test that wait_if_needed waits if at limit."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record some requests to hit the limit
        for _ in range(5):
            limiter.record_request()

        # Wait if needed
        limiter.wait_if_needed()

        # Verify sleep was called
        mock_sleep.assert_called_once()

    @patch('asyncio.sleep')
    async def test_async_wait_if_needed_no_wait(self, mock_sleep):
        """Test that async_wait_if_needed doesn't wait if under limit."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record some requests but stay under limit
        for _ in range(3):
            limiter.record_request()

        # Wait if needed
        await limiter.async_wait_if_needed()

        # Verify sleep was not called
        mock_sleep.assert_not_called()

    @patch('asyncio.sleep')
    async def test_async_wait_if_needed_with_wait(self, mock_sleep):
        """Test that async_wait_if_needed waits if at limit."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record some requests to hit the limit
        for _ in range(5):
            limiter.record_request()

        # Wait if needed
        await limiter.async_wait_if_needed()

        # Verify sleep was called
        mock_sleep.assert_called_once()

    def test_record_request(self):
        """Test recording requests."""
        limiter = DomainRateLimiter()

        # Record a request
        limiter.record_request()

        # Verify request was recorded
        assert len(limiter.request_times) == 1
        assert limiter.request_times[0] <= time.time()


class TestRateLimiter:
    """Tests for the RateLimiter class which manages rate limits for multiple domains."""

    def test_init_defaults(self):
        """Test initialization with default values."""
        limiter = RateLimiter()
        assert limiter.default_rpm == 30
        assert isinstance(limiter.domain_limits, dict)
        assert isinstance(limiter.limiters, dict)
        assert limiter.persistence_path is None

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        limiter = RateLimiter(
            default_rpm=10, persistence_path="/tmp/test_rate_limits.json")
        assert limiter.default_rpm == 10
        assert limiter.persistence_path == "/tmp/test_rate_limits.json"

    def test_get_domain(self):
        """Test extracting domain from URL."""
        limiter = RateLimiter()

        # Test various URLs
        assert limiter._get_domain(
            "https://www.example.com/path") == "www.example.com"
        assert limiter._get_domain(
            "http://subdomain.example.com/path?query=value") == "subdomain.example.com"
        assert limiter._get_domain(
            "https://realtor.com/property") == "realtor.com"

    def test_get_limiter_new_domain(self):
        """Test getting a limiter for a new domain."""
        limiter = RateLimiter(default_rpm=20)

        # Get limiter for a new domain
        domain_limiter = limiter._get_limiter("example.com")

        # Verify new limiter was created with default RPM
        assert domain_limiter.rpm == 20
        assert "example.com" in limiter.limiters

        # Verify stats were initialized
        assert "example.com" in limiter.stats["domains"]
        assert limiter.stats["domains"]["example.com"]["requests"] == 0
        assert limiter.stats["domains"]["example.com"]["rate_limited"] == 0

    def test_get_limiter_known_domain(self):
        """Test getting a limiter for a known domain."""
        limiter = RateLimiter()

        # First get creates the limiter
        first_limiter = limiter._get_limiter("realtor.com")

        # Second get should return the same limiter
        second_limiter = limiter._get_limiter("realtor.com")

        # Verify same limiter was returned
        assert first_limiter is second_limiter

        # Verify the domain-specific RPM was used (from the domain_limits dict)
        assert first_limiter.rpm == 10  # realtor.com has a lower limit

    @patch('time.sleep')
    def test_wait_if_needed(self, mock_sleep):
        """Test wait_if_needed method."""
        limiter = RateLimiter()

        # Create a domain limiter and mock its wait_if_needed method
        domain_limiter = MagicMock()
        limiter.limiters["example.com"] = domain_limiter

        # Call wait_if_needed
        limiter.wait_if_needed("https://example.com/path")

        # Verify domain limiter's wait_if_needed was called
        domain_limiter.wait_if_needed.assert_called_once()

        # Verify stats were updated
        assert limiter.stats["total_requests"] == 1
        assert limiter.stats["domains"]["example.com"]["requests"] == 1

    @patch('time.sleep')
    def test_wait_if_needed_rate_limited(self, mock_sleep):
        """Test wait_if_needed when rate limited."""
        limiter = RateLimiter()

        # Create a domain limiter that is at its limit
        domain_limiter = MagicMock()
        domain_limiter.can_request.return_value = False
        limiter.limiters["example.com"] = domain_limiter

        # Call wait_if_needed
        limiter.wait_if_needed("https://example.com/path")

        # Verify rate limited stats were updated
        assert limiter.stats["rate_limited_requests"] == 1
        assert limiter.stats["domains"]["example.com"]["rate_limited"] == 1

    @patch('asyncio.sleep')
    async def test_async_wait_if_needed(self, mock_sleep):
        """Test async_wait_if_needed method."""
        limiter = RateLimiter()

        # Create a domain limiter and mock its async_wait_if_needed method
        domain_limiter = MagicMock()
        domain_limiter.async_wait_if_needed = AsyncMock()
        limiter.limiters["example.com"] = domain_limiter

        # Call async_wait_if_needed
        await limiter.async_wait_if_needed("https://example.com/path")

        # Verify domain limiter's async_wait_if_needed was called
        domain_limiter.async_wait_if_needed.assert_called_once()

        # Verify stats were updated
        assert limiter.stats["total_requests"] == 1
        assert limiter.stats["domains"]["example.com"]["requests"] == 1

    def test_record_request(self):
        """Test record_request method."""
        limiter = RateLimiter()

        # Create a domain limiter and mock its record_request method
        domain_limiter = MagicMock()
        limiter.limiters["example.com"] = domain_limiter

        # Call record_request
        limiter.record_request("https://example.com/path")

        # Verify domain limiter's record_request was called
        domain_limiter.record_request.assert_called_once()

    def test_get_stats_global(self):
        """Test getting global stats."""
        limiter = RateLimiter()

        # Setup some test data
        limiter.stats["total_requests"] = 10
        limiter.stats["rate_limited_requests"] = 2
        limiter.stats["domains"]["example.com"] = {
            "requests": 6,
            "rate_limited": 1,
            "rpm_limit": 30
        }
        limiter.stats["domains"]["realtor.com"] = {
            "requests": 4,
            "rate_limited": 1,
            "rpm_limit": 10
        }

        # Mock limiters with request times
        example_limiter = MagicMock()
        example_limiter.request_times = [time.time() - 30, time.time() - 10]
        limiter.limiters["example.com"] = example_limiter

        realtor_limiter = MagicMock()
        realtor_limiter.request_times = [time.time() - 5]
        limiter.limiters["realtor.com"] = realtor_limiter

        # Get global stats
        stats = limiter.get_stats()

        # Verify stats content
        assert stats["total_requests"] == 10
        assert stats["rate_limited_requests"] == 2
        assert "example.com" in stats["domains"]
        assert stats["domains"]["example.com"]["requests"] == 6
        assert stats["domains"]["example.com"]["rate_limited"] == 1
        assert stats["domains"]["example.com"]["rpm_limit"] == 30
        assert stats["domains"]["example.com"]["requests_last_minute"] == 2

        assert "realtor.com" in stats["domains"]
        assert stats["domains"]["realtor.com"]["requests"] == 4
        assert stats["domains"]["realtor.com"]["rate_limited"] == 1
        assert stats["domains"]["realtor.com"]["rpm_limit"] == 10
        assert stats["domains"]["realtor.com"]["requests_last_minute"] == 1

    def test_get_stats_domain(self):
        """Test getting stats for a specific domain."""
        limiter = RateLimiter()

        # Setup some test data
        limiter.stats["domains"]["example.com"] = {
            "requests": 6,
            "rate_limited": 1,
            "rpm_limit": 30
        }

        # Mock limiter with request times
        example_limiter = MagicMock()
        example_limiter.request_times = [time.time() - 30, time.time() - 10]
        limiter.limiters["example.com"] = example_limiter

        # Get domain stats
        stats = limiter.get_stats("https://example.com/path")

        # Verify stats content
        assert stats["domain"] == "example.com"
        assert stats["requests_last_minute"] == 2
        assert stats["rpm_limit"] == 30
        assert stats["total_requests"] == 6
        assert stats["rate_limited_requests"] == 1


class TestGlobalRateLimiter:
    """Tests for the global rate_limiter instance."""

    def test_global_instance(self):
        """Test that the global instance exists and is properly initialized."""
        assert rate_limiter is not None
        assert isinstance(rate_limiter, RateLimiter)

        # Verify domain limits are set
        assert "realtor.com" in rate_limiter.domain_limits
        assert "zillow.com" in rate_limiter.domain_limits
        assert "landandfarm.com" in rate_limiter.domain_limits

    def test_global_instance_methods(self):
        """Test that the global instance methods work."""
        # Just basic smoke tests to make sure methods exist and don't raise errors

        # Get a domain that doesn't exist yet
        domain = "test-global-instance-domain.com"
        url = f"https://{domain}/path"

        # These should not raise errors
        rate_limiter._get_domain(url)
        limiter = rate_limiter._get_limiter(domain)
        rate_limiter.record_request(url)
        stats = rate_limiter.get_stats(url)

        # Verify methods worked
        assert domain in rate_limiter.limiters
        assert limiter.rpm == rate_limiter.default_rpm
        assert domain in rate_limiter.stats["domains"]
        assert stats["domain"] == domain
        assert stats["total_requests"] >= 1  # At least our record_request call


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)

class TestRateLimitExceeded:
    def test_exception(self):
        """Test RateLimitExceeded exception."""
        # Create exception
        exception = RateLimitExceeded("Rate limit exceeded for example.com")

        # Should be an Exception
        assert isinstance(exception, Exception)

        # Should have the correct message
        assert str(exception) == "Rate limit exceeded for example.com"

# Integration Tests

@pytest.mark.integration
@pytest.mark.parametrize("url, expected_domain", [
    ("https://www.realtor.com/example", "www.realtor.com"),
    ("https://zillow.com/example", "zillow.com"),
    ("https://landandfarm.com/example", "landandfarm.com")
])
def test_rate_limiter_domain_specific_limits(url, expected_domain):
    """Test that rate limiter applies domain-specific limits."""
    # Create a new limiter to avoid affecting the singleton
    limiter = RateLimiter(default_rpm=30)

    # Get the domain limiter
    domain_limiter = limiter._get_limiter(limiter._get_domain(url))

    # Check the RPM limit
    if "realtor.com" in expected_domain:
        assert domain_limiter.rpm == 10
    elif "zillow.com" in expected_domain:
        assert domain_limiter.rpm == 8
    elif "landandfarm.com" in expected_domain:
        assert domain_limiter.rpm == 25
    else:
        assert domain_limiter.rpm == 30  # Default


@pytest.mark.integration
def test_rate_limiter_wait_and_record():
    """Integration test for waiting and recording requests."""
    # Create a new limiter to avoid affecting the singleton
    limiter = RateLimiter(default_rpm=5)  # Low limit for testing
    url = "https://example.com/test"

    # Record 4 requests (under the limit)
    for _ in range(4):
        limiter.record_request(url)

    # Should not need to wait
    start_time = time.time()
    limiter.wait_if_needed(url)
    elapsed = time.time() - start_time
    assert elapsed < 0.1

    # Record one more request (at the limit)
    limiter.record_request(url)

    # The next request should need to wait
    assert not limiter._get_limiter(limiter._get_domain(url)).can_request()

    # Check stats
    stats = limiter.get_stats(url)
    assert stats["requests_last_minute"] == 5
    assert stats["total_requests"] == 5


class TestDomainRateLimiter:
    @pytest.fixture
    def limiter(self):
        """Create a fresh DomainRateLimiter for each test."""
        return DomainRateLimiter(requests_per_minute=5)

    def test_init(self, limiter):
        """Test initialization with custom RPM."""
        assert limiter.rpm == 5
        assert limiter.request_times == []

    def test_can_request_under_limit(self, limiter):
        """Test can_request when under the limit."""
        # No requests yet
        assert limiter.can_request() is True

        # Add some requests, but still under limit
        limiter.request_times = [time.time() - 10, time.time() - 5]
        assert limiter.can_request() is True

    def test_can_request_at_limit(self, limiter):
        """Test can_request when at the limit."""
        # Set RPM to 3 for easier testing
        limiter.rpm = 3

        # Add exactly 3 requests
        limiter.request_times = [
            time.time() - 10, time.time() - 5, time.time() - 2]
        assert limiter.can_request() is False

    def test_clean_old_requests(self, limiter):
        """Test cleaning of old requests."""
        # Add mix of old and new requests
        now = time.time()
        limiter.request_times = [
            now - 120,  # 2 minutes ago (should be removed)
            now - 80,   # 1 minute 20 seconds ago (should be removed)
            now - 40,   # 40 seconds ago (should be kept)
            now - 10    # 10 seconds ago (should be kept)
        ]

        limiter._clean_old_requests()

        # Only recent requests should remain
        assert len(limiter.request_times) == 2

    def test_wait_if_needed_under_limit(self, limiter):
        """Test wait_if_needed when under the limit."""
        # No need to wait
        with patch('time.sleep') as mock_sleep:
            limiter.wait_if_needed()
            mock_sleep.assert_not_called()

    def test_wait_if_needed_at_limit(self, limiter):
        """Test wait_if_needed when at the limit."""
        # Set RPM to 2 for easier testing
        limiter.rpm = 2

        # Add exactly 2 requests, oldest first
        oldest_time = time.time() - 30
        limiter.request_times = [oldest_time, time.time() - 10]

        # Should wait until oldest request is more than a minute old
        with patch('time.sleep') as mock_sleep:
            limiter.wait_if_needed()
            # Expected sleep time is roughly 30 seconds (to make oldest request 60s old)
            mock_sleep.assert_called_once()
            assert 25 <= mock_sleep.call_args[0][0] <= 35

    @pytest.mark.asyncio
    async def test_async_wait_if_needed(self, limiter):
        """Test async_wait_if_needed."""
        # Set RPM to 2 for easier testing
        limiter.rpm = 2

        # Add exactly 2 requests, oldest first
        oldest_time = time.time() - 30
        limiter.request_times = [oldest_time, time.time() - 10]

        # Should wait until oldest request is more than a minute old
        with patch('asyncio.sleep') as mock_sleep:
            await limiter.async_wait_if_needed()
            # Expected sleep time is roughly 30 seconds (to make oldest request 60s old)
            mock_sleep.assert_called_once()
            assert 25 <= mock_sleep.call_args[0][0] <= 35

    def test_record_request(self, limiter):
        """Test recording a request."""
        initial_count = len(limiter.request_times)

        limiter.record_request()

        # One more request should be added
        assert len(limiter.request_times) == initial_count + 1

        # The new request time should be recent
        newest_time = max(limiter.request_times)
        assert time.time() - newest_time < 1  # Less than 1 second ago


class TestRateLimiter:
    @pytest.fixture
    def limiter(self):
        """Create a fresh RateLimiter for each test."""
        return RateLimiter(default_rpm=10, persistence_path=None)

    def test_init(self, limiter):
        """Test initialization with custom settings."""
        assert limiter.default_rpm == 10
        assert "realtor.com" in limiter.domain_limits
        assert limiter.limiters == {}

    def test_get_domain(self, limiter):
        """Test extracting domain from URL."""
        assert limiter._get_domain(
            "https://www.realtor.com/example") == "www.realtor.com"
        assert limiter._get_domain("http://zillow.com/homes") == "zillow.com"
        assert limiter._get_domain(
            "https://sub.domain.example.com/path?query=1") == "sub.domain.example.com"

    def test_get_limiter_new_domain(self, limiter):
        """Test getting limiter for a new domain."""
        domain = "example.com"
        assert domain not in limiter.limiters

        limiter_obj = limiter._get_limiter(domain)

        # Should create a new limiter with default RPM
        assert domain in limiter.limiters
        assert limiter.limiters[domain] == limiter_obj
        assert limiter_obj.rpm == limiter.default_rpm

        # Stats should be initialized
        assert domain in limiter.stats["domains"]
        assert limiter.stats["domains"][domain]["requests"] == 0

    def test_get_limiter_existing_domain(self, limiter):
        """Test getting limiter for an existing domain."""
        domain = "realtor.com"

        # Create the limiter first
        first_limiter = limiter._get_limiter(domain)

        # Get it again
        second_limiter = limiter._get_limiter(domain)

        # Should return the same object
        assert first_limiter is second_limiter

        # Should use domain-specific RPM
        assert first_limiter.rpm == limiter.domain_limits[domain]

    def test_wait_if_needed(self, limiter):
        """Test wait_if_needed functionality."""
        url = "https://www.realtor.com/example"
        domain = "www.realtor.com"

        # Create a mock domain limiter
        mock_domain_limiter = MagicMock()
        limiter.limiters[domain] = mock_domain_limiter

        # Mock can_request to simulate being at the limit
        mock_domain_limiter.can_request.return_value = False

        # Call wait_if_needed
        limiter.wait_if_needed(url)

        # Verify correct calls
        mock_domain_limiter.wait_if_needed.assert_called_once()

        # Stats should be updated
        assert limiter.stats["total_requests"] == 1
        assert limiter.stats["rate_limited_requests"] == 1
        assert limiter.stats["domains"][domain]["requests"] == 1
        assert limiter.stats["domains"][domain]["rate_limited"] == 1

    @pytest.mark.asyncio
    async def test_async_wait_if_needed(self, limiter):
        """Test async_wait_if_needed functionality."""
        url = "https://www.realtor.com/example"
        domain = "www.realtor.com"

        # Create a mock domain limiter
        mock_domain_limiter = MagicMock()
        mock_domain_limiter.async_wait_if_needed = MagicMock()
        limiter.limiters[domain] = mock_domain_limiter

        # Mock can_request to simulate being at the limit
        mock_domain_limiter.can_request.return_value = False

        # Call async_wait_if_needed
        await limiter.async_wait_if_needed(url)

        # Verify correct calls
        mock_domain_limiter.async_wait_if_needed.assert_called_once()

        # Stats should be updated
        assert limiter.stats["total_requests"] == 1
        assert limiter.stats["rate_limited_requests"] == 1

    def test_record_request(self, limiter):
        """Test record_request functionality."""
        url = "https://www.example.com/test"
        domain = "www.example.com"

        # Create a mock domain limiter
        mock_domain_limiter = MagicMock()
        limiter.limiters[domain] = mock_domain_limiter

        # Call record_request
        limiter.record_request(url)

        # Verify the domain limiter's record_request was called
        mock_domain_limiter.record_request.assert_called_once()

    def test_get_stats_for_url(self, limiter):
        """Test getting stats for a specific URL."""
        url = "https://www.realtor.com/example"
        domain = "www.realtor.com"

        # Set up some stats
        limiter.stats["domains"][domain] = {
            "requests": 5,
            "rate_limited": 2,
            "rpm_limit": 10
        }

        # Create a domain limiter with some request times
        domain_limiter = DomainRateLimiter(10)
        domain_limiter.request_times = [time.time() - 30, time.time() - 10]
        limiter.limiters[domain] = domain_limiter

        # Get stats for URL
        stats = limiter.get_stats(url)

        # Verify stats content
        assert stats["domain"] == domain
        assert stats["requests_last_minute"] == 2
        assert stats["rpm_limit"] == 10
        assert stats["total_requests"] == 5
        assert stats["rate_limited_requests"] == 2

    def test_get_stats_global(self, limiter):
        """Test getting global stats."""
        # Set up some stats
        limiter.stats["total_requests"] = 10
        limiter.stats["rate_limited_requests"] = 3
        limiter.stats["domains"] = {
            "domain1.com": {"requests": 5, "rate_limited": 1, "rpm_limit": 10},
            "domain2.com": {"requests": 5, "rate_limited": 2, "rpm_limit": 5}
        }

        # Create domain limiters
        domain1_limiter = DomainRateLimiter(10)
        domain1_limiter.request_times = [time.time() - 30, time.time() - 10]
        domain2_limiter = DomainRateLimiter(5)
        domain2_limiter.request_times = [time.time() - 20]

        limiter.limiters = {
            "domain1.com": domain1_limiter,
            "domain2.com": domain2_limiter
        }

        # Get global stats
        stats = limiter.get_stats()

        # Verify stats content
        assert stats["total_requests"] == 10
        assert stats["rate_limited_requests"] == 3
        assert len(stats["domains"]) == 2
        assert stats["domains"]["domain1.com"]["requests"] == 5
        assert stats["domains"]["domain1.com"]["rate_limited"] == 1
        assert stats["domains"]["domain1.com"]["requests_last_minute"] == 2
        assert stats["domains"]["domain2.com"]["requests_last_minute"] == 1


@patch("builtins.open")
@patch("os.path.exists")
class TestRateLimiterPersistence:
    def test_load_state_when_exists(self, mock_exists, mock_open):
        """Test loading state from disk when file exists."""
        # Mock file existence
        mock_exists.return_value = True

        # Mock file content
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = """
        {
            "stats": {
                "total_requests": 100,
                "rate_limited_requests": 20,
                "domains": {
                    "example.com": {
                        "requests": 50,
                        "rate_limited": 10,
                        "rpm_limit": 30
                    }
                }
            }
        }
        """
        mock_open.return_value = mock_file

        # Create limiter with persistence
        limiter = RateLimiter(persistence_path="test_path.json")

        # Verify state was loaded
        mock_exists.assert_called_once_with("test_path.json")
        mock_open.assert_called_once_with("test_path.json", "r")
        assert limiter.stats["total_requests"] == 100
        assert limiter.stats["rate_limited_requests"] == 20
        assert "example.com" in limiter.stats["domains"]

    def test_load_state_file_not_exists(self, mock_exists, mock_open):
        """Test behavior when persistence file doesn't exist."""
        # Mock file non-existence
        mock_exists.return_value = False

        # Create limiter with persistence
        limiter = RateLimiter(persistence_path="test_path.json")

        # Verify file was checked but not opened
        mock_exists.assert_called_once_with("test_path.json")
        mock_open.assert_not_called()

        # Stats should be default
        assert limiter.stats["total_requests"] == 0
        assert limiter.stats["rate_limited_requests"] == 0

    def test_save_state(self, mock_exists, mock_open):
        """Test saving state to disk."""
        # Create a limiter with persistence
        limiter = RateLimiter(persistence_path="test_path.json")

        # Set up some stats
        limiter.stats["total_requests"] = 5
        limiter.stats["domains"]["example.com"] = {
            "requests": 5,
            "rate_limited": 0,
            "rpm_limit": 10
        }

        # Mock file for writing
        mock_file = MagicMock()
        mock_open.return_value = mock_file

        # Call _save_state
        limiter._save_state()

        # Verify file was opened and written to
        mock_open.assert_called_once_with("test_path.json", "w")
        mock_file.__enter__.return_value.write.assert_called_once()

    def test_save_state_no_persistence(self, mock_exists, mock_open):
        """Test behavior when no persistence path is set."""
        # Create limiter without persistence
        limiter = RateLimiter(persistence_path=None)

        # Call _save_state
        limiter._save_state()

        # Verify no file operations
        mock_exists.assert_not_called()
        mock_open.assert_not_called()

    def test_error_handling_load(self, mock_exists, mock_open):
        """Test error handling during state loading."""
        # Mock file existence
        mock_exists.return_value = True

        # Mock open to raise exception
        mock_open.side_effect = Exception("Test error")

        # Create limiter with persistence (should handle exception)
        limiter = RateLimiter(persistence_path="test_path.json")

        # Verify state wasn't loaded (default values)
        assert limiter.stats["total_requests"] == 0

    def test_error_handling_save(self, mock_exists, mock_open):
        """Test error handling during state saving."""
        # Create a limiter with persistence
        limiter = RateLimiter(persistence_path="test_path.json")

        # Mock open to raise exception
        mock_open.side_effect = Exception("Test error")

        # Call _save_state (should handle exception)
        limiter._save_state()

        # Verify attempt was made
        mock_open.assert_called_once_with("test_path.json", "w")


class TestRateLimiterSingleton:
    def test_singleton_instance(self):
        """Test that rate_limiter is a singleton instance."""
        # Import the singleton
        from new_england_listings.utils.rate_limiting import rate_limiter as instance1

        # Import again
        from new_england_listings.utils.rate_limiting import rate_limiter as instance2

        # Should be the same object
        assert instance1 is instance2

    def test_singleton_default_config(self):
        """Test default configuration of the singleton."""
        # Should have domain limits for common sites
        assert "realtor.com" in rate_limiter.domain_limits
        assert "zillow.com" in rate_limiter.domain_limits

        # Check persistence path from environment
        expected_path = os.environ.get('RATE_LIMITER_STATE_PATH')
        assert rate_limiter.persistence_path == expected_path

# Running this with pytest requires event loop for async tests
@pytest.fixture
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
