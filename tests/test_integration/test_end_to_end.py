# tests/test_integration/test_end_to_end.py
import pytest
import asyncio
import os
import json
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime
from unittest.mock import patch

from new_england_listings import process_listing, process_listings
from new_england_listings.extractors import get_extractor_for_url
from new_england_listings.utils.browser import get_page_content_async
from new_england_listings.utils.notion.client import create_notion_entry


# ------------------- Fixtures -------------------

@pytest.fixture
def test_data_dir():
    """Get the test data directory path."""
    return Path(__file__).parent.parent / "fixtures" / "html_samples"


@pytest.fixture
def sample_urls():
    """Return a list of sample URLs for testing."""
    return [
        "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101_M12345-67890",
        "https://www.landandfarm.com/property/10_Acres_in_Brunswick-12345",
        "https://www.zillow.com/homedetails/123-Main-St-Portland-ME-04101/12345_zpid/"
    ]


@pytest.fixture
def vcr_config():
    """Configure VCR for recording HTTP interactions."""
    return {
        'filter_headers': [
            'authorization', 'Authorization', 'Cookie', 'Set-Cookie',
            'User-Agent', 'Accept', 'Accept-Encoding'
        ],
        'filter_post_data_parameters': ['api_key', 'token'],
        'record_mode': 'once'
    }


# ------------------- Selective Mocking Helpers -------------------

def get_cached_or_live_html(url, cache_dir, skip_cache=False):
    """
    Get HTML either from cache or live website.
    
    This allows tests to work offline using cached responses,
    but also refresh the cache when needed.
    """
    # Create a unique filename based on the URL
    import hashlib
    filename = hashlib.md5(url.encode()).hexdigest() + ".html"
    cache_path = Path(cache_dir) / filename

    # Check if we have a cached version
    if not skip_cache and cache_path.exists() and cache_path.stat().st_size > 0:
        with open(cache_path, 'r', encoding='utf-8') as f:
            html = f.read()
        return BeautifulSoup(html, 'html.parser')

    # If not cached or skipping cache, fetch live
    try:
        # This uses aiohttp under the hood
        from new_england_listings.utils.browser import get_stealth_driver
        driver = get_stealth_driver()
        driver.get(url)
        html = driver.page_source

        # Cache the result
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return BeautifulSoup(html, 'html.parser')
    except Exception as e:
        pytest.skip(f"Could not fetch live URL: {url}. Error: {str(e)}")


async def cached_get_page_content(url, use_selenium=False, **kwargs):
    """Wrapper around get_page_content_async that uses cache."""
    cache_dir = Path(__file__).parent.parent / "fixtures" / "cached_pages"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return get_cached_or_live_html(url, cache_dir)


# ------------------- Selective Real API Testing -------------------

def check_notion_credentials():
    """Check if real Notion credentials are available for testing."""
    notion_api_key = os.environ.get("NOTION_API_KEY")
    notion_database_id = os.environ.get("NOTION_DATABASE_ID")

    if notion_api_key and notion_database_id:
        return True
    return False


def use_real_notion():
    """Determine if real Notion API should be used."""
    return os.environ.get("USE_REAL_NOTION") == "1" and check_notion_credentials()


# ------------------- Test Markers -------------------

# Create marks for different test categories
pytestmark = pytest.mark.integration

# Define specific markers
requires_internet = pytest.mark.skipif(
    not os.environ.get("RUN_INTERNET_TESTS"),
    reason="Requires internet connection. Set RUN_INTERNET_TESTS=1 to run."
)

uses_notion_api = pytest.mark.skipif(
    not use_real_notion(),
    reason="Requires Notion API credentials. Set USE_REAL_NOTION=1 and provide credentials to run."
)


# ------------------- Test Classes -------------------

@pytest.mark.asyncio
class TestEndToEndExtraction:
    """End-to-end tests for extraction process with minimal mocking."""

    @pytest.mark.parametrize("platform,expected_fields", [
        ("realtor.com", ["listing_name", "location",
         "price", "price_bucket", "property_type"]),
        ("landandfarm.com", ["listing_name", "location",
         "price", "price_bucket", "acreage"]),
        ("zillow.com", ["listing_name", "location", "price", "price_bucket"])
    ])
    async def test_extraction_with_cached_pages(self, platform, expected_fields, sample_urls, test_data_dir):
        """Test extraction using cached HTML pages."""
        # Find a matching URL for the platform
        url = next((u for u in sample_urls if platform in u), None)
        if not url:
            pytest.skip(f"No test URL found for platform: {platform}")

        # Get the appropriate extractor
        extractor_class = get_extractor_for_url(url)
        if not extractor_class:
            pytest.skip(f"No extractor available for platform: {platform}")

        # Use cached page content
        with patch('new_england_listings.main.get_page_content_async', side_effect=cached_get_page_content):
            # Process the listing
            result = await process_listing(url, use_notion=False)

            # Check that result contains expected fields
            for field in expected_fields:
                assert field in result, f"Missing expected field: {field}"

            # Check that the platform is correct
            assert platform in result["platform"].lower()

            # Verify URL is preserved
            assert result["url"] == url

    @requires_internet
    @pytest.mark.slow
    async def test_live_extraction_minimum_fields(self, sample_urls):
        """Test extraction from live websites with minimal validation."""
        # Only test the first URL to avoid rate limiting
        url = sample_urls[0]

        # Process with minimal mocking - use real browser but mock Notion
        with patch('new_england_listings.main.create_notion_entry'):
            result = await process_listing(url, use_notion=True)

            # Basic validation of essential fields
            assert "listing_name" in result
            assert "location" in result
            assert "price" in result or "price_bucket" in result
            assert result["url"] == url

            # Check the extraction status
            assert "extraction_error" not in result, f"Extraction error: {result.get('extraction_error')}"

            # Print a summary of the result for debugging
            print(f"\nExtracted data summary for {url}:")
            print(f"  Platform: {result.get('platform')}")
            print(f"  Listing: {result.get('listing_name')}")
            print(f"  Location: {result.get('location')}")
            print(f"  Price: {result.get('price')}")

    @requires_internet
    @pytest.mark.slow
    async def test_multi_extraction_concurrency(self, sample_urls):
        """Test concurrent extraction of multiple listings."""
        # Use only two URLs to avoid rate limiting
        test_urls = sample_urls[:2]

        # Process with concurrency
        with patch('new_england_listings.main.create_notion_entry'):
            results = await process_listings(test_urls, use_notion=False, concurrency=2)

            # Check that we got results for all URLs
            assert len(results) == len(test_urls)

            # Check that the basic structure is correct
            for result in results:
                assert "listing_name" in result
                assert "platform" in result
                assert "location" in result


@uses_notion_api
@pytest.mark.asyncio
class TestNotionIntegration:
    """Tests for Notion integration with real API calls."""

    async def test_notion_entry_creation(self):
        """Test creating a Notion entry with real credentials."""
        # Create a test listing
        test_listing = {
            "url": "https://example.com/integration-test",
            "platform": "Integration Test",
            "listing_name": f"Test Property {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "location": "Portland, ME",
            "price": "$500,000",
            "price_bucket": "$300K - $600K",
            "property_type": "Single Family",
            "acreage": "10.0 acres",
            "acreage_bucket": "Medium (5-20 acres)"
        }

        # Create the entry
        response = create_notion_entry(test_listing)

        # Check the response
        assert response is not None
        assert "id" in response

        # Verify the entry was created
        from notion_client import Client
        client = Client(auth=os.environ.get("NOTION_API_KEY"))
        page = client.pages.retrieve(response["id"])

        # Check page contents
        assert page["id"] == response["id"]

        # Clean up - archive the test page
        client.pages.update(response["id"], archived=True)

    @pytest.mark.parametrize("platform", ["realtor.com", "landandfarm.com"])
    async def test_end_to_end_with_notion(self, platform, sample_urls):
        """Test complete extraction and Notion creation flow."""
        # Find a matching URL for the platform
        url = next((u for u in sample_urls if platform in u), None)
        if not url:
            pytest.skip(f"No test URL found for platform: {platform}")

        # Process with cached content but real Notion
        with patch('new_england_listings.main.get_page_content_async', side_effect=cached_get_page_content):
            result = await process_listing(url, use_notion=True)

            # Check that the listing was processed
            assert "listing_name" in result
            assert platform in result["platform"].lower()

            # Since we're using real Notion, we should have created an entry
            # We need a way to verify this - ideally we'd get back the Notion page ID
            # This depends on how your integration is set up

            # Clean up - ideally would archive the created page
            # This would require modifying process_listing to return the Notion page ID


@pytest.mark.performance
class TestPerformanceBaseline:
    """Performance tests to establish baselines."""

    @pytest.mark.asyncio
    async def test_extraction_timing(self, sample_urls):
        """Measure extraction time for different platforms."""
        # Only use first URL to avoid rate limits
        url = sample_urls[0]

        import time

        # Use cached content
        with patch('new_england_listings.main.get_page_content_async', side_effect=cached_get_page_content):
            with patch('new_england_listings.main.create_notion_entry'):
                start_time = time.time()
                await process_listing(url, use_notion=False)
                end_time = time.time()

                duration = end_time - start_time
                print(f"\nExtraction time for {url}: {duration:.2f} seconds")

                # This is a baseline test, so we're just checking it completes
                # In the future, compare against established baselines
                assert duration > 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("concurrency", [1, 2, 4])
    async def test_concurrency_scaling(self, sample_urls, concurrency):
        """Test how extraction time scales with concurrency."""
        # Use all sample URLs
        urls = sample_urls * 2  # Duplicate to get more data points

        import time

        # Use cached content and mock Notion
        with patch('new_england_listings.main.get_page_content_async', side_effect=cached_get_page_content):
            with patch('new_england_listings.main.create_notion_entry'):
                start_time = time.time()
                await process_listings(urls, use_notion=False, concurrency=concurrency)
                end_time = time.time()

                duration = end_time - start_time
                print(
                    f"\nProcessing {len(urls)} URLs with concurrency={concurrency}: {duration:.2f} seconds")

                # This is a baseline test, so we're just checking it completes
                # In the future, compare against established baselines
                assert duration > 0


# Use this conditional to enable running the tests directly
if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
