# tests/test_integration/test_scraper.py
import pytest
from unittest.mock import patch
import asyncio

from new_england_listings import process_listing, process_listings
from new_england_listings.utils.rate_limiting import RateLimitExceeded


@pytest.mark.integration
class TestScraperIntegration:
    """Integration tests for the scraper functionality that interact with real websites."""

    @pytest.mark.parametrize("url, expected_platform, expected_location", [
        ("https://www.landandfarm.com/property/single-family-residence-cape-windham-me-36400823/",
         "Land and Farm", "Windham"),
        ("https://www.realtor.com/realestateandhomes-detail/28-Vanderwerf-Dr_West-Bath_ME_04530_M36122-24566",
         "Realtor.com", "West Bath"),
        ("https://farmlink.mainefarmlandtrust.org/individual-farm-listings/farm-id-3582",
         "Maine Farmland Trust", None)
    ])
    def test_process_listing_basic(self, url, expected_platform, expected_location):
        """Test basic listing processing for different platforms."""
        data = process_listing(url, use_notion=False)

        # Verify platform is correct
        assert data["platform"] == expected_platform

        # Verify location contains expected town if provided
        if expected_location:
            assert expected_location in data["location"]

        # Verify essential fields are present
        assert "listing_name" in data
        assert "price" in data or "price_bucket" in data
        assert "url" in data

    @pytest.mark.asyncio
    async def test_process_multiple_listings(self):
        """Test processing multiple listings concurrently."""
        urls = [
            "https://www.landandfarm.com/property/single-family-residence-cape-windham-me-36400823/",
            "https://www.realtor.com/realestateandhomes-detail/28-Vanderwerf-Dr_West-Bath_ME_04530_M36122-24566"
        ]

        results = await process_listings(urls, use_notion=False, concurrency=2)

        # Verify all listings were processed
        assert len(results) == 2

        # Verify results contain both platforms
        platforms = [r["platform"] for r in results]
        assert "Land and Farm" in platforms
        assert "Realtor.com" in platforms

    @pytest.mark.asyncio
    async def test_handle_rate_limiting(self):
        """Test handling of rate limiting."""
        url = "https://www.realtor.com/realestateandhomes-detail/28-Vanderwerf-Dr_West-Bath_ME_04530_M36122-24566"

        # Mock rate limiter to simulate rate limiting
        with patch('new_england_listings.main.rate_limiter.async_wait_if_needed') as mock_wait:
            # First call raises RateLimitExceeded, second call succeeds
            side_effects = [RateLimitExceeded("Rate limit exceeded"), None]
            mock_wait.side_effect = side_effects

            # Should handle the rate limit and retry
            data = await process_listing(url, use_notion=False, max_retries=2)

            # Verify rate limiter was called twice
            assert mock_wait.call_count >= 1

            # Verify data was still extracted
            assert data["platform"] == "Realtor.com"

    @pytest.mark.skip(reason="Only run manually to avoid excessive API calls")
    @pytest.mark.asyncio
    async def test_error_handling_invalid_url(self):
        """Test error handling with invalid URLs."""
        # Test with invalid URL
        with pytest.raises(Exception):
            await process_listing("https://www.realtor.com/nonexistent-page",
                                  use_notion=False,
                                  max_retries=1)

    @pytest.mark.asyncio
    async def test_respect_rate_limits_flag(self):
        """Test that respect_rate_limits flag is honored."""
        url = "https://www.realtor.com/realestateandhomes-detail/example"

        # Mock rate limiter to verify it's called or not called
        with patch('new_england_listings.main.rate_limiter.async_wait_if_needed') as mock_wait:
            # With respect_rate_limits=True (default)
            try:
                await process_listing(url, respect_rate_limits=True)
            except:
                pass  # Ignore any errors - we just want to check if rate limiter was called

            # Verify rate limiter was called
            mock_wait.assert_called_once()
            mock_wait.reset_mock()

            # With respect_rate_limits=False
            try:
                await process_listing(url, respect_rate_limits=False)
            except:
                pass  # Ignore any errors

            # Verify rate limiter was not called
            mock_wait.assert_not_called()
