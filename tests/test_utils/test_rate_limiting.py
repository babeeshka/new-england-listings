# tests/test_utils/test_rate_limiting.py
import pytest
import time
import asyncio
import os
import tempfile
import json
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from new_england_listings.utils.rate_limiting import (
    RateLimitExceeded,
    DomainRateLimiter,
    RateLimiter,
    rate_limiter
)


class TestRateLimitExceeded:
    """Tests for the RateLimitExceeded exception."""

    def test_exception_init(self):
        """Test initialization of the exception."""
        msg = "Rate limit exceeded for example.com"
        exc = RateLimitExceeded(msg)

        # Should be an Exception
        assert isinstance(exc, Exception)

        # Should have the correct message
        assert str(exc) == msg


class TestDomainRateLimiter:
    """Tests for the DomainRateLimiter class."""

    @pytest.fixture
    def limiter(self):
        """Create a fresh DomainRateLimiter for each test."""
        return DomainRateLimiter(requests_per_minute=5)

    def test_init(self, limiter):
        """Test initialization with custom RPM."""
        assert limiter.rpm == 5
        assert limiter.request_times == []

        # Test with default value
        default_limiter = DomainRateLimiter()
        assert default_limiter.rpm == 30  # Default RPM should be 30

    def test_can_request_initial(self, limiter):
        """Test that initial requests are allowed."""
        assert limiter.can_request() is True

    def test_can_request_under_limit(self, limiter):
        """Test can_request when under the limit."""
        # Add some requests, but still under limit
        limiter.request_times = [time.time() - 10, time.time() - 5]
        assert limiter.can_request() is True

    def test_can_request_at_limit(self, limiter):
        """Test can_request when at the limit."""
        # Add exactly 5 requests
        current_time = time.time()
        limiter.request_times = [
            current_time - 50, current_time - 40,
            current_time - 30, current_time - 20,
            current_time - 10
        ]
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
        # All remaining times should be from last minute
        assert all(t > now - 60 for t in limiter.request_times)

    @patch('time.sleep')
    def test_wait_if_needed_under_limit(self, mock_sleep, limiter):
        """Test wait_if_needed when under the limit."""
        # No need to wait
        limiter.wait_if_needed()
        mock_sleep.assert_not_called()

    @patch('time.sleep')
    def test_wait_if_needed_at_limit(self, mock_sleep, limiter):
        """Test wait_if_needed when at the limit."""
        # Set RPM to 2 for easier testing
        limiter.rpm = 2

        # Add exactly 2 requests, oldest first
        oldest_time = time.time() - 30
        limiter.request_times = [oldest_time, time.time() - 10]

        # Should wait until oldest request is more than a minute old
        limiter.wait_if_needed()

        # Expected sleep time is roughly 30 seconds (to make oldest request 60s old)
        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert 25 <= sleep_time <= 35

    @pytest.mark.asyncio
    @patch('asyncio.sleep')
    async def test_async_wait_if_needed_under_limit(self, mock_sleep, limiter):
        """Test async_wait_if_needed when under the limit."""
        # No need to wait
        await limiter.async_wait_if_needed()
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    @patch('asyncio.sleep')
    async def test_async_wait_if_needed_at_limit(self, mock_sleep, limiter):
        """Test async_wait_if_needed when at the limit."""
        # Set RPM to 2 for easier testing
        limiter.rpm = 2

        # Add exactly 2 requests, oldest first
        oldest_time = time.time() - 30
        limiter.request_times = [oldest_time, time.time() - 10]

        # Should wait until oldest request is more than a minute old
        await limiter.async_wait_if_needed()

        # Expected sleep time is roughly 30 seconds (to make oldest request 60s old)
        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert 25 <= sleep_time <= 35

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
    """Tests for the RateLimiter class."""

    @pytest.fixture
    def limiter(self):
        """Create a fresh RateLimiter for each test."""
        return RateLimiter(default_rpm=10, persistence_path=None)

    def test_init(self, limiter):
        """Test initialization with custom settings."""
        assert limiter.default_rpm == 10
        assert isinstance(limiter.domain_limits, dict)
        assert "realtor.com" in limiter.domain_limits
        assert limiter.limiters == {}
        assert limiter.persistence_path is None

        # Check default stats initialization
        assert limiter.stats["total_requests"] == 0
        assert limiter.stats["rate_limited_requests"] == 0
        assert limiter.stats["domains"] == {}

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
        assert limiter.stats["domains"][domain]["rate_limited"] == 0
        assert limiter.stats["domains"][domain]["rpm_limit"] == limiter.default_rpm

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

    def test_get_limiter_domain_specific_limits(self, limiter):
        """Test that domain-specific rate limits are applied correctly."""
        # Test realtor.com limit
        realtor_limiter = limiter._get_limiter("realtor.com")
        assert realtor_limiter.rpm == 10  # Strict limit for realtor.com

        # Test zillow.com limit
        zillow_limiter = limiter._get_limiter("zillow.com")
        assert zillow_limiter.rpm == 8  # Very restrictive for zillow.com

        # Test landandfarm.com limit
        landandfarm_limiter = limiter._get_limiter("landandfarm.com")
        assert landandfarm_limiter.rpm == 25  # Medium limit for landandfarm.com

        # Test unknown domain - should use default
        unknown_limiter = limiter._get_limiter("unknown.com")
        assert unknown_limiter.rpm == limiter.default_rpm

    @patch('time.sleep')
    def test_wait_if_needed(self, mock_sleep, limiter):
        """Test wait_if_needed functionality."""
        url = "https://www.realtor.com/example"
        domain = "www.realtor.com"

        # Create a mock domain limiter
        mock_domain_limiter = MagicMock()
        limiter.limiters[domain] = mock_domain_limiter

        # Mock can_request to simulate being under the limit
        mock_domain_limiter.can_request.return_value = True

        # Call wait_if_needed
        limiter.wait_if_needed(url)

        # Verify domain limiter's wait_if_needed was called
        mock_domain_limiter.wait_if_needed.assert_called_once()

        # Stats should be updated
        assert limiter.stats["total_requests"] == 1
        assert limiter.stats["domains"][domain]["requests"] == 1
        assert limiter.stats["rate_limited_requests"] == 0

    @patch('time.sleep')
    def test_wait_if_needed_rate_limited(self, mock_sleep, limiter):
        """Test wait_if_needed when rate limited."""
        url = "https://www.realtor.com/example"
        domain = "www.realtor.com"

        # Create a mock domain limiter
        mock_domain_limiter = MagicMock()
        mock_domain_limiter.can_request.return_value = False
        limiter.limiters[domain] = mock_domain_limiter

        # Call wait_if_needed
        limiter.wait_if_needed(url)

        # Verify domain limiter's wait_if_needed was called
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
        mock_domain_limiter.can_request.return_value = True
        mock_domain_limiter.async_wait_if_needed = AsyncMock()
        limiter.limiters[domain] = mock_domain_limiter

        # Call async_wait_if_needed
        await limiter.async_wait_if_needed(url)

        # Verify domain limiter's async_wait_if_needed was called
        mock_domain_limiter.async_wait_if_needed.assert_called_once()

        # Stats should be updated
        assert limiter.stats["total_requests"] == 1
        assert limiter.stats["domains"][domain]["requests"] == 1

    @pytest.mark.asyncio
    async def test_async_wait_if_needed_rate_limited(self, limiter):
        """Test async_wait_if_needed when rate limited."""
        url = "https://www.realtor.com/example"
        domain = "www.realtor.com"

        # Create a mock domain limiter
        mock_domain_limiter = MagicMock()
        mock_domain_limiter.can_request.return_value = False
        mock_domain_limiter.async_wait_if_needed = AsyncMock()
        limiter.limiters[domain] = mock_domain_limiter

        # Call async_wait_if_needed
        await limiter.async_wait_if_needed(url)

        # Verify domain limiter's async_wait_if_needed was called
        mock_domain_limiter.async_wait_if_needed.assert_called_once()

        # Stats should be updated
        assert limiter.stats["total_requests"] == 1
        assert limiter.stats["rate_limited_requests"] == 1
        assert limiter.stats["domains"][domain]["requests"] == 1
        assert limiter.stats["domains"][domain]["rate_limited"] == 1

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


class TestRateLimiterPersistence:
    """Tests for the persistence functionality of RateLimiter."""

    def test_save_state(self):
        """Test saving state to file."""
        # Create a temp file for testing
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            # Create limiter with persistence
            limiter = RateLimiter(persistence_path=temp_path)

            # Set up some stats
            limiter.stats["total_requests"] = 10
            limiter.stats["rate_limited_requests"] = 2
            limiter.stats["domains"]["example.com"] = {
                "requests": 10,
                "rate_limited": 2,
                "rpm_limit": 30
            }

            # Save state
            limiter._save_state()

            # Verify file was created and contains valid JSON
            assert os.path.exists(temp_path)
            with open(temp_path, 'r') as f:
                data = json.load(f)
                assert "stats" in data
                assert data["stats"]["total_requests"] == 10
                assert "example.com" in data["stats"]["domains"]

        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_load_state(self):
        """Test loading state from file."""
        # Create a temp file for testing
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            # Write test data
            test_data = {
                "stats": {
                    "total_requests": 25,
                    "rate_limited_requests": 5,
                    "domains": {
                        "test.com": {
                            "requests": 25,
                            "rate_limited": 5,
                            "rpm_limit": 20
                        }
                    }
                }
            }
            temp_file.write(json.dumps(test_data).encode())
            temp_path = temp_file.name

        try:
            # Create limiter with persistence - should load state
            limiter = RateLimiter(persistence_path=temp_path)

            # Verify state was loaded
            assert limiter.stats["total_requests"] == 25
            assert limiter.stats["rate_limited_requests"] == 5
            assert "test.com" in limiter.stats["domains"]
            assert limiter.stats["domains"]["test.com"]["requests"] == 25

        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_error_handling_load(self):
        """Test error handling during state loading."""
        # Create a temp file with invalid JSON
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"invalid json{")
            temp_path = temp_file.name

        try:
            # Create limiter - should handle error and use default values
            limiter = RateLimiter(persistence_path=temp_path)

            # Verify default values were used
            assert limiter.stats["total_requests"] == 0
            assert limiter.stats["rate_limited_requests"] == 0

        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_error_handling_save(self):
        """Test error handling during state saving."""
        # Create a directory instead of a file (can't write to directory)
        temp_dir = tempfile.mkdtemp()

        try:
            # Create limiter with persistence path pointing to directory
            limiter = RateLimiter(persistence_path=temp_dir)

            # Should not raise exception
            limiter._save_state()

        finally:
            # Clean up
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)


class TestGlobalRateLimiter:
    """Tests for the global rate_limiter instance."""

    def test_singleton_instance(self):
        """Test that rate_limiter is a singleton instance."""
        # Import the singleton
        from new_england_listings.utils.rate_limiting import rate_limiter as instance1

        # Import again
        from new_england_listings.utils.rate_limiting import rate_limiter as instance2

        # Should be the same object
        assert instance1 is instance2

    def test_singleton_properties(self):
        """Test properties of the singleton instance."""
        # Should have domain limits for common sites
        assert "realtor.com" in rate_limiter.domain_limits
        assert "zillow.com" in rate_limiter.domain_limits
        assert "landandfarm.com" in rate_limiter.domain_limits

        # Should have RPM limits according to site requirements
        # Realtor.com is strict
        assert rate_limiter.domain_limits["realtor.com"] <= 10
        # Zillow is also strict
        assert rate_limiter.domain_limits["zillow.com"] <= 10

    def test_singleton_methods(self):
        """Test that singleton methods work properly."""
        # Create a unique test domain
        import uuid
        test_domain = f"test-{uuid.uuid4()}.com"
        test_url = f"https://{test_domain}/page"

        # Test _get_domain
        extracted_domain = rate_limiter._get_domain(test_url)
        assert extracted_domain == test_domain

        # Test _get_limiter
        limiter = rate_limiter._get_limiter(test_domain)
        assert isinstance(limiter, DomainRateLimiter)
        assert test_domain in rate_limiter.limiters

        # Test get_stats
        stats = rate_limiter.get_stats(test_url)
        assert stats["domain"] == test_domain
        assert "rpm_limit" in stats
        assert "requests_last_minute" in stats


# Running this with pytest requires event loop for async tests
@pytest.fixture
def event_loop():
    """Create and yield a new event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Create a MockAsyncMock for Python 3.7 compatibility
class AsyncMock(MagicMock):
    """Mock for async functions."""

    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)
