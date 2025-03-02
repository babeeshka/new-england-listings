# tests/test_regression/test_known_bugs.py
"""
Regression tests for known bugs in New England Listings.

Each test case in this module corresponds to a specific bug that was previously
identified and fixed. These tests help ensure that fixed bugs don't resurface
in future versions.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from pathlib import Path

from new_england_listings import process_listing
from new_england_listings.extractors import (
    RealtorExtractor, LandAndFarmExtractor, FarmlandExtractor, ZillowExtractor,
    get_extractor_for_url
)
from new_england_listings.utils.text import TextProcessor
from new_england_listings.utils.dates import DateExtractor


# ------------------- Fixtures -------------------

@pytest.fixture
def html_fixtures_dir():
    """Get the directory containing HTML fixtures for regression tests."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return fixtures_dir


@pytest.fixture
def mock_soup(html_fixtures_dir):
    """Create a BeautifulSoup object from a test HTML file."""
    def _get_soup(filename):
        """Load HTML from file and return a soup object."""
        html_path = html_fixtures_dir / filename
        if html_path.exists():
            with open(html_path, "r", encoding="utf-8") as f:
                html = f.read()
            return BeautifulSoup(html, "html.parser")
        else:
            # Create minimal HTML if file doesn't exist
            return BeautifulSoup("<html><body>Minimal test page</body></html>", "html.parser")

    return _get_soup


# ------------------- Regression Tests for Extractors -------------------

class TestRealtorExtractorRegressions:
    """Regression tests for RealtorExtractor."""

    def test_realtor_blocked_page_handling(self, mock_soup):
        """
        Test handling of blocked Realtor.com pages.
        
        Bug: When Realtor.com blocked the scraper with a CAPTCHA page,
        the extractor would raise an exception instead of extracting data from URL.
        
        Fix: Added detection of blocking and fallback to URL-based extraction.
        """
        # Create a CAPTCHA/blocking page
        captcha_html = """
        <html>
            <head><title>Security Check</title></head>
            <body>
                <h1>Please complete this captcha</h1>
                <div>We need to verify you're not a robot.</div>
            </body>
        </html>
        """
        soup = BeautifulSoup(captcha_html, "html.parser")

        # Create extractor with test URL
        url = "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101_M12345-67890"
        extractor = RealtorExtractor(url)

        # The extractor should not raise an exception
        result = extractor.extract(soup)

        # Should fall back to URL extraction
        assert result["location"] == "Portland, ME"
        assert result["url"] == url

    def test_realtor_metadata_extraction(self, mock_soup):
        """
        Test extraction of additional data added by the main.py module.
        
        Bug: When main.py added metadata tags to the soup, the extractor
        wasn't correctly handling them.
        
        Fix: Added detection and handling of metadata tags.
        """
        # Create a soup with metadata
        html = """
        <html>
            <head>
                <meta name="extraction-status" content="blocked-but-attempting">
                <meta name="url-extracted-location" content="Portland, ME">
            </head>
            <body>Minimal content</body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        # Create extractor
        url = "https://www.realtor.com/test"
        extractor = RealtorExtractor(url)

        # Extract location
        location = extractor.extract_location()

        # Should use metadata
        assert location == "Portland, ME"


class TestLandAndFarmExtractorRegressions:
    """Regression tests for LandAndFarmExtractor."""

    def test_landandfarm_acreage_extraction(self):
        """
        Test extraction of acreage from LandAndFarm.com listings.
        
        Bug: Acreage extraction failed when the acreage was formatted in certain ways,
        such as "Approx. 10 acres" or "10 Acre Lot".
        
        Fix: Added more robust patterns for acreage extraction.
        """
        # Test various acreage formats
        formats = [
            "10 acres of prime farmland",
            "Approximately 10 acres of land",
            "About 10 acres with views",
            "10 acre lot with barn",
            "10 acre parcel near town"
        ]

        for format_str in formats:
            # Create HTML with the acreage format
            html = f"""
            <html>
                <body>
                    <div class="property-details">{format_str}</div>
                </body>
            </html>
            """
            soup = BeautifulSoup(html, "html.parser")

            # Create extractor
            extractor = LandAndFarmExtractor(
                "https://www.landandfarm.com/test")
            extractor.soup = soup

            # Extract acreage
            acreage, bucket = extractor.extract_acreage_info()

            # Should extract correctly
            assert acreage == "10.0 acres"
            assert bucket == "Medium (5-20 acres)"


class TestZillowExtractorRegressions:
    """Regression tests for ZillowExtractor."""

    def test_zillow_nested_price_extraction(self):
        """
        Test extraction of price from nested JSON in Zillow pages.
        
        Bug: Price extraction failed when the price was in a nested structure
        in the JSON data, such as price.value instead of price directly.
        
        Fix: Added support for nested price paths.
        """
        # Create extractor with test URL
        url = "https://www.zillow.com/homedetails/test/12345_zpid/"
        extractor = ZillowExtractor(url)

        # Mock property_data with nested price
        extractor.property_data = {
            "price": {
                "value": 500000
            }
        }

        # Create minimal soup
        extractor.soup = BeautifulSoup("<html></html>", "html.parser")

        # Extract price
        price, bucket = extractor.extract_price()

        # Should extract correctly
        assert price == "$500,000"
        assert bucket == "$300K - $600K"


class TestGetExtractorRegressions:
    """Regression tests for get_extractor_for_url function."""

    def test_extractor_selection_edge_cases(self):
        """
        Test URL pattern matching for extractor selection.
        
        Bug: Some valid URLs weren't matching the expected patterns,
        leading to None being returned instead of the correct extractor.
        
        Fix: Improved regex patterns for URL matching.
        """
        # Test various URL formats for each platform
        test_cases = [
            # Realtor.com variations
            ("https://www.realtor.com/realestateandhomes-detail/abc-123", RealtorExtractor),
            ("http://realtor.com/realestateandhomes-detail/abc", RealtorExtractor),
            ("https://realtor.com/property/123", RealtorExtractor),

            # Land and Farm variations
            ("https://www.landandfarm.com/property/abc", LandAndFarmExtractor),
            ("http://landandfarm.com/property/123", LandAndFarmExtractor),

            # Zillow variations
            ("https://www.zillow.com/homedetails/abc/123_zpid", ZillowExtractor),
            ("http://zillow.com/homedetails/abc/123_zpid/", ZillowExtractor),
        ]

        for url, expected_extractor in test_cases:
            extractor_class = get_extractor_for_url(url)
            assert extractor_class == expected_extractor, f"Failed for URL: {url}"


# ------------------- Regression Tests for Text Processing -------------------

class TestTextProcessorRegressions:
    """Regression tests for TextProcessor."""

    def test_html_entity_cleaning(self):
        """
        Test cleaning of HTML entities.
        
        Bug: Some HTML entities weren't being properly cleaned,
        leading to them remaining in the output text.
        
        Fix: Added more comprehensive entity handling.
        """
        # Test various HTML entities
        entities = [
            ("Hello&nbsp;World", "Hello World"),
            ("This&amp;That", "This&That"),
            ("Less&lt;More", "Less<More"),
            ("Greater&gt;Than", "Greater>Than"),
            ("Quote&quot;Text", "Quote\"Text"),
            ("Apostrophe&#39;s", "Apostrophe's"),
        ]

        for input_text, expected in entities:
            result = TextProcessor.clean_html_text(input_text)
            assert result == expected

    def test_price_formatting_edge_cases(self):
        """
        Test price formatting for edge cases.
        
        Bug: Price formatting failed for certain formats,
        such as "$1.2M" or "$500K".
        
        Fix: Added support for K and M notation.
        """
        # Test various price formats
        formats = [
            ("$1.2M", "$1.2M", "$1.2M - $1.5M"),
            ("$1.5M", "$1.5M", "$1.5M - $2M"),
            ("$500K", "$500,000", "$300K - $600K"),
            ("$2,500K", "$2.5M", "$2M+"),
        ]

        for input_price, expected_price, expected_bucket in formats:
            price, bucket = TextProcessor.standardize_price(input_price)
            assert price == expected_price
            assert bucket == expected_bucket


class TestDateExtractorRegressions:
    """Regression tests for DateExtractor."""

    def test_date_parsing_variations(self):
        """
        Test parsing of various date formats.
        
        Bug: Some date formats weren't being correctly parsed,
        especially abbreviated month names like "Sept".
        
        Fix: Added more robust date pattern matching and special handling for variants.
        """
        # Test various date formats
        formats = [
            ("January 15, 2023", "2023-01-15"),
            ("Jan 15, 2023", "2023-01-15"),
            ("Sept 15, 2023", "2023-09-15"),
            ("Sep 15, 2023", "2023-09-15"),
            ("01/15/2023", "2023-01-15"),
            ("2023-01-15", "2023-01-15"),
            ("15.01.2023", "2023-01-15"),
            ("Listed on January 15, 2023", "2023-01-15"),
            ("Date Listed: 01/15/2023", "2023-01-15"),
        ]

        for input_date, expected in formats:
            result = DateExtractor.parse_date_string(input_date)
            assert result == expected


# ------------------- Regression Tests for Main Process Flow -------------------

@pytest.mark.asyncio
class TestProcessListingRegressions:
    """Regression tests for process_listing function."""

    async def test_rate_limit_handling(self):
        """
        Test handling of rate limiting.
        
        Bug: Rate limiting exceptions weren't being properly caught and
        retried, leading to failures instead of waiting and retrying.
        
        Fix: Added specific exception handling for RateLimitExceeded.
        """
        from new_england_listings.utils.rate_limiting import RateLimitExceeded

        # Mock dependencies
        with patch("new_england_listings.main.get_extractor_for_url") as mock_get_extractor:
            with patch("new_england_listings.main.get_page_content_async") as mock_get_page:
                with patch("new_england_listings.main.rate_limiter.async_wait_if_needed") as mock_wait:
                    # Configure mocks
                    mock_extractor = MagicMock()
                    mock_extractor.extract.return_value = {"test": "data"}
                    mock_get_extractor.return_value = lambda url: mock_extractor

                    mock_soup = MagicMock()
                    mock_get_page.return_value = mock_soup

                    # Make wait_if_needed raise RateLimitExceeded once, then succeed
                    mock_wait.side_effect = [
                        RateLimitExceeded("Rate limit exceeded"),
                        None
                    ]

                    # Should retry after rate limit exception
                    await process_listing("https://example.com/test", max_retries=2)

                    # Verify wait_if_needed was called twice
                    assert mock_wait.call_count == 2

    async def test_retry_mechanism(self):
        """
        Test retry mechanism for failed requests.
        
        Bug: The retry mechanism wasn't waiting between retries,
        leading to immediate retries that would also fail.
        
        Fix: Added exponential backoff with jitter between retries.
        """
        # Mock dependencies
        with patch("new_england_listings.main.get_extractor_for_url") as mock_get_extractor:
            with patch("new_england_listings.main.get_page_content_async") as mock_get_page:
                with patch("new_england_listings.main.rate_limiter.async_wait_if_needed"):
                    with patch("asyncio.sleep") as mock_sleep:
                        # Configure mocks
                        mock_extractor = MagicMock()
                        mock_extractor.extract.return_value = {"test": "data"}
                        mock_get_extractor.return_value = lambda url: mock_extractor

                        # Make get_page_content_async fail, then succeed
                        mock_get_page.side_effect = [
                            Exception("Test error"),
                            MagicMock()
                        ]

                        # Should retry after failure
                        await process_listing("https://example.com/test", max_retries=2)

                        # Verify sleep was called between retries
                        mock_sleep.assert_called_once()


# ------------------- Regression Tests for Browser/Scraping -------------------

class TestBrowserRegressions:
    """Regression tests for browser/scraping functionality."""

    def test_user_agent_rotation(self):
        """
        Test rotation of user agents to avoid detection.
        
        Bug: Using the same user agent for all requests made it
        easier for sites to detect and block scraping.
        
        Fix: Added rotation of different, realistic user agents.
        """
        from new_england_listings.utils.browser import get_random_user_agent

        # Get multiple user agents
        agents = [get_random_user_agent() for _ in range(5)]

        # Should have at least 2 different agents in 5 tries
        unique_agents = set(agents)
        assert len(unique_agents) >= 2

        # All should be valid user agents
        for agent in agents:
            assert "Mozilla" in agent

    def test_stealth_driver_configuration(self):
        """
        Test stealth configuration for ChromeDriver.
        
        Bug: Default ChromeDriver was easily detected as automation.
        
        Fix: Added comprehensive stealth settings to avoid detection.
        """
        from new_england_listings.utils.browser import get_stealth_driver

        # Mock ChromeDriver
        with patch("selenium.webdriver.Chrome") as mock_chrome:
            with patch("webdriver_manager.chrome.ChromeDriverManager.install") as mock_install:
                mock_install.return_value = "/path/to/chromedriver"

                driver = get_stealth_driver()

                # Check that execute_cdp_cmd was called with stealth settings
                execute_cdp_calls = [
                    call for call in driver.execute_cdp_cmd.call_args_list
                    if call[0][0] == 'Network.setUserAgentOverride'
                ]

                assert len(execute_cdp_calls) > 0

                # Check for stealth arguments
                options = mock_chrome.call_args[1]["options"]
                stealth_args = [
                    arg for arg in options.arguments
                    if "disable-blink-features=AutomationControlled" in arg
                ]

                assert len(stealth_args) > 0


# ------------------- Run Tests -------------------

if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
