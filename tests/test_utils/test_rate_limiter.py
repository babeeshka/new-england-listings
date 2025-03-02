# tests/test_utils/test_rate_limiter.py
import pytest
import time
from unittest.mock import patch, MagicMock
from new_england_listings.utils.rate_limiting import RateLimiter, DomainRateLimiter, RateLimitExceeded


class TestDomainRateLimiter:
    def test_can_request_under_limit(self):
        """Test that requests under the rate limit are allowed."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record 4 requests (under the limit of 5)
        for _ in range(4):
            limiter.record_request()

        assert limiter.can_request() is True

    def test_can_request_at_limit(self):
        """Test that requests at the rate limit are not allowed."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record 5 requests (at the limit)
        for _ in range(5):
            limiter.record_request()

        assert limiter.can_request() is False

    def test_clean_old_requests(self):
        """Test that old requests are cleaned up."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Add old requests (more than a minute ago)
        now = time.time()
        limiter.request_times = [now - 61, now - 62, now - 63]

        # Add recent requests
        limiter.request_times.extend([now - 10, now - 20])

        # Clean old requests
        limiter._clean_old_requests()

        # Should only have 2 recent requests left
        assert len(limiter.request_times) == 2

    def test_wait_if_needed(self):
        """Test that wait_if_needed waits when rate limited."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record 5 requests (at the limit)
        for _ in range(5):
            limiter.record_request()

        # Mock time.sleep to avoid actual waiting
        with patch('time.sleep') as mock_sleep:
            limiter.wait_if_needed()
            mock_sleep.assert_called_once()

    def test_wait_if_needed_no_wait(self):
        """Test that wait_if_needed doesn't wait when under limit."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record 4 requests (under the limit)
        for _ in range(4):
            limiter.record_request()

        # Mock time.sleep to verify it's not called
        with patch('time.sleep') as mock_sleep:
            limiter.wait_if_needed()
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_wait_if_needed(self):
        """Test that async_wait_if_needed waits when rate limited."""
        limiter = DomainRateLimiter(requests_per_minute=5)

        # Record 5 requests (at the limit)
        for _ in range(5):
            limiter.record_request()

        # Mock asyncio.sleep to avoid actual waiting
        with patch('asyncio.sleep') as mock_sleep:
            await limiter.async_wait_if_needed()
            mock_sleep.assert_called_once()


class TestRateLimiter:
    def test_get_domain(self):
        """Test extracting domain from URL."""
        limiter = RateLimiter()

        assert limiter._get_domain(
            "https://www.realtor.com/listing/123") == "www.realtor.com"
        assert limiter._get_domain(
            "http://mainefarmlandtrust.org/farm-456") == "mainefarmlandtrust.org"
        assert limiter._get_domain(
            "https://landsearch.com/property/789?param=value") == "landsearch.com"

    def test_get_limiter_new_domain(self):
        """Test getting a new limiter for a domain."""
        limiter = RateLimiter()
        domain = "example.com"

        # Domain shouldn't exist yet
        assert domain not in limiter.limiters

        # Get limiter for domain
        domain_limiter = limiter._get_limiter(domain)

        # Domain limiter should be created and stored
        assert domain in limiter.limiters
        assert domain_limiter is limiter.limiters[domain]
        assert isinstance(domain_limiter, DomainRateLimiter)

        # Stats should be initialized
        assert domain in limiter.stats["domains"]
        assert limiter.stats["domains"][domain]["requests"] == 0
        assert limiter.stats["domains"][domain]["rate_limited"] == 0

    def test_get_limiter_existing_domain(self):
        """Test getting an existing limiter for a domain."""
        limiter = RateLimiter()
        domain = "example.com"

        # Create domain limiter
        domain_limiter = limiter._get_limiter(domain)

        # Get limiter again - should be the same instance
        domain_limiter2 = limiter._get_limiter(domain)
        assert domain_limiter is domain_limiter2

    def test_get_limiter_domain_specific_rpm(self):
        """Test that domain-specific RPM limits are applied."""
        limiter = RateLimiter()

        # Get limiters for different domains
        realtor_limiter = limiter._get_limiter("www.realtor.com")
        mft_limiter = limiter._get_limiter("mainefarmlandtrust.org")
        other_limiter = limiter._get_limiter("example.com")

        # Verify domain-specific RPM limits
        assert realtor_limiter.rpm == 10  # Realtor.com has a stricter limit
        assert mft_limiter.rpm == 50      # MFT has a higher limit
        assert other_limiter.rpm == 30    # Default RPM

    def test_wait_if_needed(self):
        """Test wait_if_needed with domain rate limiting."""
        limiter = RateLimiter()

        # Mock _get_limiter to return a mock domain limiter
        mock_domain_limiter = MagicMock()
        mock_domain_limiter.can_request.return_value = False
        limiter._get_limiter = MagicMock(return_value=mock_domain_limiter)

        # Test wait_if_needed
        url = "https://www.example.com/listing/123"
        with patch('time.sleep'):
            limiter.wait_if_needed(url)

            # Verify domain limiter was used
            limiter._get_limiter.assert_called_once_with("www.example.com")
            mock_domain_limiter.wait_if_needed.assert_called_once()

            # Verify stats
            assert limiter.stats["total_requests"] == 1
            assert limiter.stats["rate_limited_requests"] == 1

    @pytest.mark.asyncio
    async def test_async_wait_if_needed(self):
        """Test async_wait_if_needed with domain rate limiting."""
        limiter = RateLimiter()

        # Mock _get_limiter to return a mock domain limiter
        mock_domain_limiter = MagicMock()
        mock_domain_limiter.can_request.return_value = False
        limiter._get_limiter = MagicMock(return_value=mock_domain_limiter)

        # Test async_wait_if_needed
        url = "https://www.example.com/listing/123"
        with patch('asyncio.sleep'):
            await limiter.async_wait_if_needed(url)

            # Verify domain limiter was used
            limiter._get_limiter.assert_called_once_with("www.example.com")
            mock_domain_limiter.async_wait_if_needed.assert_called_once()

            # Verify stats
            assert limiter.stats["total_requests"] == 1
            assert limiter.stats["rate_limited_requests"] == 1

    def test_record_request(self):
        """Test record_request with domain rate limiting."""
        limiter = RateLimiter()

        # Mock _get_limiter to return a mock domain limiter
        mock_domain_limiter = MagicMock()
        limiter._get_limiter = MagicMock(return_value=mock_domain_limiter)

        # Test record_request
        url = "https://www.example.com/listing/123"
        limiter.record_request(url)

        # Verify domain limiter was used
        limiter._get_limiter.assert_called_once_with("www.example.com")
        mock_domain_limiter.record_request.assert_called_once()

    def test_get_stats_global(self):
        """Test getting global stats."""
        limiter = RateLimiter()

        # Set up some stats
        limiter.stats["total_requests"] = 100
        limiter.stats["rate_limited_requests"] = 20
        limiter.stats["domains"] = {
            "www.realtor.com": {
                "requests": 50,
                "rate_limited": 10,
                "rpm_limit": 10
            },
            "mainefarmlandtrust.org": {
                "requests": 50,
                "rate_limited": 10,
                "rpm_limit": 50
            }
        }

        # Get global stats
        stats = limiter.get_stats()

        # Verify stats
        assert stats["total_requests"] == 100
        assert stats["rate_limited_requests"] == 20
        assert "domains" in stats
        assert "www.realtor.com" in stats["domains"]
        assert "mainefarmlandtrust.org" in stats["domains"]

    def test_get_stats_domain_specific(self):
        """Test getting domain-specific stats."""
        limiter = RateLimiter()

        # Set up domain limiter
        domain = "www.realtor.com"
        domain_limiter = limiter._get_limiter(domain)
        domain_limiter.request_times = [time.time() - 10, time.time() - 20]

        # Set up stats
        limiter.stats["domains"][domain]["requests"] = 50
        limiter.stats["domains"][domain]["rate_limited"] = 10

        # Get domain-specific stats
        url = f"https://{domain}/listing/123"
        stats = limiter.get_stats(url)

        # Verify stats
        assert stats["domain"] == domain
        assert stats["requests_last_minute"] == 2
        assert stats["rpm_limit"] == 10
        assert stats["total_requests"] == 50
        assert stats["rate_limited_requests"] == 10
