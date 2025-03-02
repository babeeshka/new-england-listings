# tests/test_main.py
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import json
from bs4 import BeautifulSoup

from new_england_listings import main
from new_england_listings.extractors import BaseExtractor
from new_england_listings.utils.rate_limiting import RateLimitExceeded


class TestNeedsSelenium:
    def test_needs_selenium_realtor(self):
        """Test that Realtor.com URLs need Selenium."""
        assert main.needs_selenium(
            "https://www.realtor.com/property/123") is True

    def test_needs_selenium_zillow(self):
        """Test that Zillow URLs need Selenium."""
        assert main.needs_selenium(
            "https://www.zillow.com/homedetails/123") is True

    def test_needs_selenium_farmland(self):
        """Test that Farmland URLs need Selenium."""
        assert main.needs_selenium(
            "https://newenglandfarmlandfinder.org/property/123") is True

    def test_needs_selenium_other(self):
        """Test that other URLs don't need Selenium."""
        assert main.needs_selenium("https://example.com/property/123") is False


class MockExtractor(BaseExtractor):
    """Mock implementation of BaseExtractor for testing."""
    @property
    def platform_name(self):
        return "Mock Platform"

    def extract_listing_name(self):
        return "Mock Listing"

    def extract_location(self):
        return "Mock Location, ME"

    def extract_price(self):
        return "$500,000", "$300K - $600K"

    def extract_acreage_info(self):
        return "10.0 acres", "Medium (5-20 acres)"

    def extract(self, soup):
        self.soup = soup
        return {
            "listing_name": "Mock Listing",
            "location": "Mock Location, ME",
            "price": "$500,000",
            "price_bucket": "$300K - $600K",
            "acreage": "10.0 acres",
            "acreage_bucket": "Medium (5-20 acres)",
            "platform": "Mock Platform",
            "url": self.url
        }


@pytest.mark.asyncio
class TestProcessListing:
    @patch("new_england_listings.main.get_extractor_for_url")
    @patch("new_england_listings.main.get_page_content_async")
    @patch("new_england_listings.main.create_notion_entry")
    async def test_process_listing_success(self, mock_notion, mock_get_page, mock_get_extractor):
        """Test successful listing processing."""
        # Setup mocks
        mock_get_extractor.return_value = MockExtractor(
            "https://example.com/test")
        mock_get_page.return_value = BeautifulSoup(
            "<html><body>Test</body></html>", 'html.parser')
        mock_notion.return_value = {"id": "notion-123"}

        # Test
        result = await main.process_listing("https://example.com/test", use_notion=True)

        # Verify results
        assert result["listing_name"] == "Mock Listing"
        assert result["location"] == "Mock Location, ME"
        assert result["price"] == "$500,000"
        assert result["platform"] == "Mock Platform"

        # Verify mocks were called
        mock_get_extractor.assert_called_once_with("https://example.com/test")
        mock_get_page.assert_called_once()
        mock_notion.assert_called_once()

    @patch("new_england_listings.main.get_extractor_for_url")
    @patch("new_england_listings.main.get_page_content_async")
    @patch("new_england_listings.main.create_notion_entry")
    async def test_process_listing_without_notion(self, mock_notion, mock_get_page, mock_get_extractor):
        """Test processing without creating Notion entry."""
        # Setup mocks
        mock_get_extractor.return_value = MockExtractor(
            "https://example.com/test")
        mock_get_page.return_value = BeautifulSoup(
            "<html><body>Test</body></html>", 'html.parser')

        # Test
        result = await main.process_listing("https://example.com/test", use_notion=False)

        # Verify Notion was not called
        mock_notion.assert_not_called()

    @patch("new_england_listings.main.get_extractor_for_url")
    async def test_process_listing_no_extractor(self, mock_get_extractor):
        """Test handling when no extractor is available."""
        # Setup mock to return None
        mock_get_extractor.return_value = None

        # Test
        with pytest.raises(ValueError, match="No extractor available"):
            await main.process_listing("https://example.com/test")

    @patch("new_england_listings.main.get_extractor_for_url")
    @patch("new_england_listings.main.get_page_content_async")
    @patch("new_england_listings.main.rate_limiter.async_wait_if_needed")
    async def test_process_listing_rate_limit(self, mock_rate_limiter, mock_get_page, mock_get_extractor):
        """Test handling rate limiting."""
        # Setup mocks
        mock_get_extractor.return_value = MockExtractor(
            "https://example.com/test")
        mock_get_page.return_value = BeautifulSoup(
            "<html><body>Test</body></html>", 'html.parser')

        # Test
        await main.process_listing("https://example.com/test", respect_rate_limits=True)

        # Verify rate limiter was called
        mock_rate_limiter.assert_called_once_with("https://example.com/test")

    @patch("new_england_listings.main.get_extractor_for_url")
    @patch("new_england_listings.main.get_page_content_async")
    @patch("new_england_listings.main.rate_limiter.async_wait_if_needed")
    async def test_process_listing_no_rate_limit(self, mock_rate_limiter, mock_get_page, mock_get_extractor):
        """Test processing without rate limiting."""
        # Setup mocks
        mock_get_extractor.return_value = MockExtractor(
            "https://example.com/test")
        mock_get_page.return_value = BeautifulSoup(
            "<html><body>Test</body></html>", 'html.parser')

        # Test
        await main.process_listing("https://example.com/test", respect_rate_limits=False)

        # Verify rate limiter was not called
        mock_rate_limiter.assert_not_called()

    @patch("new_england_listings.main.get_extractor_for_url")
    @patch("new_england_listings.main.get_page_content_async")
    async def test_process_listing_retries(self, mock_get_page, mock_get_extractor):
        """Test retrying after failure."""
        # Setup mocks
        mock_get_extractor.return_value = MockExtractor(
            "https://example.com/test")

        # Make get_page fail once then succeed
        mock_get_page.side_effect = [
            ValueError("Test error"),  # First call fails
            BeautifulSoup("<html><body>Test</body></html>",
                          'html.parser')  # Second call succeeds
        ]

        # Test
        result = await main.process_listing("https://example.com/test", max_retries=2)

        # Verify result and that get_page was called twice
        assert result["listing_name"] == "Mock Listing"
        assert mock_get_page.call_count == 2

    @patch("new_england_listings.main.get_extractor_for_url")
    @patch("new_england_listings.main.get_page_content_async")
    async def test_process_listing_max_retries_exceeded(self, mock_get_page, mock_get_extractor):
        """Test handling when max retries are exceeded."""
        # Setup mocks
        mock_get_extractor.return_value = MockExtractor(
            "https://example.com/test")

        # Make get_page always fail
        mock_get_page.side_effect = ValueError("Test error")

        # Test
        with pytest.raises(Exception, match="Failed to process listing after"):
            await main.process_listing("https://example.com/test", max_retries=2)

        # Verify get_page was called max_retries times
        assert mock_get_page.call_count == 2


@pytest.mark.asyncio
class TestProcessListings:
    @patch("new_england_listings.main.process_listing")
    async def test_process_listings_success(self, mock_process_listing):
        """Test successful processing of multiple listings."""
        # Setup mock to return different values for different URLs
        async def mock_process(url, **kwargs):
            if url == "https://example.com/1":
                return {"listing_name": "Listing 1", "url": url}
            else:
                return {"listing_name": "Listing 2", "url": url}

        mock_process_listing.side_effect = mock_process

        # Test
        urls = ["https://example.com/1", "https://example.com/2"]
        results = await main.process_listings(urls)

        # Verify results
        assert len(results) == 2
        assert results[0]["listing_name"] == "Listing 1"
        assert results[1]["listing_name"] == "Listing 2"

        # Verify mock was called for each URL
        assert mock_process_listing.call_count == 2

    @patch("new_england_listings.main.process_listing")
    async def test_process_listings_partial_failure(self, mock_process_listing):
        """Test handling when some listings fail."""
        # Setup mock to succeed for first URL and fail for second
        async def mock_process(url, **kwargs):
            if url == "https://example.com/1":
                return {"listing_name": "Listing 1", "url": url}
            else:
                raise ValueError("Test error")

        mock_process_listing.side_effect = mock_process

        # Test
        urls = ["https://example.com/1", "https://example.com/2"]
        results = await main.process_listings(urls)

        # Verify results
        assert len(results) == 2
        assert results[0]["listing_name"] == "Listing 1"
        assert "error" in results[1]
        assert results[1]["url"] == "https://example.com/2"
        assert results[1]["extraction_status"] == "failed"

    @patch("new_england_listings.main.process_listing")
    async def test_process_listings_concurrency(self, mock_process_listing):
        """Test processing with concurrency control."""
        # Setup mock to track when calls are made
        call_times = []

        async def mock_process(url, **kwargs):
            call_times.append(asyncio.get_event_loop().time())
            # Simulate processing time
            await asyncio.sleep(0.1)
            return {"listing_name": f"Listing {url}", "url": url}

        mock_process_listing.side_effect = mock_process

        # Test with high concurrency
        urls = [f"https://example.com/{i}" for i in range(5)]
        await main.process_listings(urls, concurrency=5)

        # With high concurrency, all calls should start at almost the same time
        # Calculate the max time difference between first and last call
        max_diff = max(call_times) - min(call_times)
        assert max_diff < 0.05  # All calls should start within 50ms

        # Reset for next test
        call_times.clear()
        mock_process_listing.reset_mock()

        # Test with low concurrency
        await main.process_listings(urls, concurrency=1)

        # With concurrency=1, calls should be sequential
        # Each call should start after the previous one finished
        for i in range(1, len(call_times)):
            # Each call should be at least 0.1s after the previous one
            assert call_times[i] - call_times[i-1] >= 0.09

    @patch("new_england_listings.main.process_listing")
    async def test_process_listings_with_notion(self, mock_process_listing):
        """Test processing with Notion integration."""
        # Setup mock
        async def mock_process(url, **kwargs):
            # Return kwargs so we can verify them
            return {"url": url, "kwargs": kwargs}

        mock_process_listing.side_effect = mock_process

        # Test with use_notion=True
        urls = ["https://example.com/1"]
        results = await main.process_listings(urls, use_notion=True)

        # Verify use_notion was passed correctly
        assert results[0]["kwargs"]["use_notion"] is True

        # Test with use_notion=False
        results = await main.process_listings(urls, use_notion=False)

        # Verify use_notion was passed correctly
        assert results[0]["kwargs"]["use_notion"] is False


class TestRealtorSpecialCase:
    @patch("new_england_listings.main.get_extractor_for_url")
    @patch("new_england_listings.main.get_page_content_async")
    @patch("new_england_listings.main.rate_limiter.async_wait_if_needed")
    @patch("new_england_listings.main.create_notion_entry")
    @pytest.mark.asyncio
    async def test_realtor_special_case(self, mock_notion, mock_rate_limiter, mock_get_page, mock_get_extractor):
        """Test special handling for Realtor.com URLs."""
        # URL containing realtor.com
        url = "https://www.realtor.com/property/123"

        # Setup mocks
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = {
            "platform": "Realtor.com", "url": url}
        mock_get_extractor.return_value = mock_extractor

        # Make page content seem like it has blocking content
        soup = BeautifulSoup(
            "<html><body>captcha verification required</body></html>", 'html.parser')
        mock_get_page.return_value = soup

        # Test
        result = await main.process_listing(url)

        # Verify that even with blocking content, extraction proceeds
        assert mock_extractor.extract.called

        # Verify meta tag was added to signal blocking
        calls = mock_extractor.extract.call_args_list
        called_soup = calls[0][0][0]  # First arg of first call
        assert called_soup.find(
            "meta", {"name": "extraction-status"}) is not None


class TestSetupLogging:
    def test_setup_logging_basic(self):
        """Test basic logging setup."""
        logger = main.setup_logging(level="INFO")
        assert logger is not None

        # Check that handlers were added
        assert len(logger.handlers) > 0

    def test_setup_logging_with_file(self):
        """Test logging setup with file."""
        # Use a temporary directory for log files
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "test.log")
            logger = main.setup_logging(level="INFO", log_file=log_file)

            # Check that log file was created
            logger.info("Test message")
            assert os.path.exists(log_file)

            # Check that message was written
            with open(log_file, 'r') as f:
                content = f.read()
                assert "Test message" in content


@pytest.mark.asyncio
class TestMainFunction:
    @patch("new_england_listings.main.process_listings")
    @patch("new_england_listings.main.setup_logging")
    async def test_main_with_urls(self, mock_setup_logging, mock_process_listings):
        """Test main function with provided URLs."""
        # Setup mock
        mock_process_listings.return_value = [
            {"listing_name": "Listing 1", "url": "https://example.com/1"},
            {"listing_name": "Listing 2", "url": "https://example.com/2"}
        ]

        # Test
        await main.main(urls=["https://example.com/1", "https://example.com/2"])

        # Verify logging was setup
        mock_setup_logging.assert_called_once()

        # Verify process_listings was called with URLs
        mock_process_listings.assert_called_once_with(
            ["https://example.com/1", "https://example.com/2"]
        )

    @patch("new_england_listings.main.process_listings")
    @patch("new_england_listings.main.setup_logging")
    @patch("builtins.input", return_value="https://example.com/1,https://example.com/2")
    @patch("sys.argv", ["script.py"])
    async def test_main_with_input(self, mock_input, mock_setup_logging, mock_process_listings):
        """Test main function with input from user."""
        # Setup mock
        mock_process_listings.return_value = [
            {"listing_name": "Listing 1", "url": "https://example.com/1"},
            {"listing_name": "Listing 2", "url": "https://example.com/2"}
        ]

        # Test
        await main.main()

        # Verify input was called
        mock_input.assert_called_once()

        # Verify process_listings was called with URLs from input
        mock_process_listings.assert_called_once_with(
            ["https://example.com/1", "https://example.com/2"]
        )

    @patch("new_england_listings.main.process_listings")
    @patch("new_england_listings.main.setup_logging")
    @patch("sys.argv", ["script.py", "https://example.com/1", "https://example.com/2"])
    async def test_main_with_argv(self, mock_setup_logging, mock_process_listings):
        """Test main function with arguments from command line."""
        # Setup mock
        mock_process_listings.return_value = [
            {"listing_name": "Listing 1", "url": "https://example.com/1"},
            {"listing_name": "Listing 2", "url": "https://example.com/2"}
        ]

        # Test
        await main.main()

        # Verify process_listings was called with URLs from argv
        mock_process_listings.assert_called_once_with(
            ["https://example.com/1", "https://example.com/2"]
        )

    @patch("new_england_listings.main.process_listings")
    @patch("new_england_listings.main.setup_logging")
    @patch("builtins.print")
    async def test_main_with_error(self, mock_print, mock_setup_logging, mock_process_listings):
        """Test main function error handling."""
        # Setup mock to raise exception
        mock_process_listings.side_effect = Exception("Test error")

        # Test
        with pytest.raises(SystemExit):
            await main.main(urls=["https://example.com/1"])

        # Verify error was printed
        mock_print.assert_called()
