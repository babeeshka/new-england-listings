# tests/test_integration/test_integration_mocks.py
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from new_england_listings import process_listing, process_listings
from new_england_listings.extractors import (
    get_extractor_for_url, RealtorExtractor, LandAndFarmExtractor, FarmlandExtractor
)

# Sample HTML content for mocking web responses


@pytest.fixture
def sample_realtor_html():
    """Sample HTML for Realtor.com"""
    return """
    <html>
        <head>
            <title>123 Main St, Portland, ME 04101 | realtor.com</title>
        </head>
        <body>
            <h1 data-testid="listing-title">123 Main St</h1>
            <div data-testid="price">$500,000</div>
            <div data-testid="address">123 Main St, Portland, ME 04101</div>
            <div data-testid="property-meta">
                <div data-testid="property-meta-beds">3 bed</div>
                <div data-testid="property-meta-baths">2 bath</div>
                <div data-testid="property-meta-sqft">2,000 sqft</div>
                <div data-testid="property-meta-lot-size">0.25 acres</div>
            </div>
            <div data-testid="property-type">Single Family</div>
        </body>
    </html>
    """


@pytest.fixture
def sample_landandfarm_html():
    """Sample HTML for LandAndFarm"""
    return """
    <html>
        <head>
            <title>40 Acres Farm Land in Brunswick, ME | Land and Farm</title>
        </head>
        <body>
            <h1 class="_2233487">40 Acres Farm Land in Brunswick, ME</h1>
            <div class="cff3611">$350,000</div>
            <div class="location-container">
                <div class="property-address">123 Rural Rd, Brunswick, ME 04011</div>
            </div>
            <div class="property-details">
                <div class="details-section">
                    <p>40 acres of prime farmland</p>
                </div>
                <div class="property-features">
                    <ul>
                        <li>Farm land</li>
                        <li>Well water</li>
                        <li>Road frontage</li>
                    </ul>
                </div>
            </div>
            <div class="_5ae12cd">
                <p>Beautiful farm property with rich soil and established fields.</p>
            </div>
        </body>
    </html>
    """


@pytest.fixture
def sample_farmland_html():
    """Sample HTML for Maine Farmland Trust"""
    return """
    <html>
        <head>
            <title>Farm Property | Maine Farmland Trust</title>
        </head>
        <body>
            <h1 class="page-title">75 Acre Farm in Kennebec County</h1>
            <div class="field-group--columns">
                <div class="info-section">
                    <span>Total number of acres</span>
                    <div>75</div>
                </div>
                <div class="info-section">
                    <span>Location</span>
                    <div>Kennebec County, ME</div>
                </div>
                <div class="info-section">
                    <span>Price</span>
                    <div>$650,000</div>
                </div>
            </div>
            <div class="content">
                <p>Beautiful farm property with established infrastructure.</p>
            </div>
        </body>
    </html>
    """

# Mock the get_page_content function to return our sample HTML


@pytest.fixture
def mock_get_page_content(sample_realtor_html, sample_landandfarm_html, sample_farmland_html):
    """Mock the get_page_content function to return different HTML based on URL."""
    with patch('new_england_listings.main.get_page_content_async') as mock:
        # Configure mock to return different content based on URL
        async def side_effect(url, **kwargs):
            if "realtor.com" in url:
                return BeautifulSoup(sample_realtor_html, 'html.parser')
            elif "landandfarm.com" in url:
                return BeautifulSoup(sample_landandfarm_html, 'html.parser')
            elif "mainefarmlandtrust.org" in url:
                return BeautifulSoup(sample_farmland_html, 'html.parser')
            else:
                return BeautifulSoup("<html><body>No content</body></html>", 'html.parser')

        # Use AsyncMock for async functions
        mock.side_effect = side_effect
        yield mock

# Mock create_notion_entry to avoid actual Notion API calls


@pytest.fixture
def mock_create_notion_entry():
    """Mock create_notion_entry function."""
    with patch('new_england_listings.main.create_notion_entry') as mock:
        mock.return_value = {"id": "test-notion-id", "status": "success"}
        yield mock


@pytest.mark.asyncio
async def test_process_listing_realtor(mock_get_page_content, mock_create_notion_entry):
    """Test processing a Realtor.com listing with mocked responses."""
    url = "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101"

    result = await process_listing(url, use_notion=True)

    # Verify extractor was used correctly
    assert result["platform"] == "Realtor.com"
    assert result["listing_name"] == "123 Main St"
    assert result["location"] == "Portland, ME 04101"
    assert result["price"] == "$500,000"
    assert result["price_bucket"] == "$300K - $600K"
    assert result["property_type"] == "Single Family"
    assert result["acreage"] == "0.25 acres"

    # Verify Notion API was called
    mock_create_notion_entry.assert_called_once()


@pytest.mark.asyncio
async def test_process_listing_landandfarm(mock_get_page_content, mock_create_notion_entry):
    """Test processing a Land and Farm listing with mocked responses."""
    url = "https://www.landandfarm.com/property/40_Acres_in_Brunswick-123456"

    result = await process_listing(url, use_notion=True)

    # Verify extractor was used correctly
    assert result["platform"] == "Land and Farm"
    assert "Brunswick" in result["location"]
    assert result["price"] == "$350,000"
    assert result["price_bucket"] == "$300K - $600K"
    assert result["acreage"] == "40.0 acres"

    # Verify Notion API was called
    mock_create_notion_entry.assert_called_once()


@pytest.mark.asyncio
async def test_process_listing_farmland(mock_get_page_content, mock_create_notion_entry):
    """Test processing a Maine Farmland Trust listing with mocked responses."""
    url = "https://farmlink.mainefarmlandtrust.org/property/75-acre-farm"

    result = await process_listing(url, use_notion=False)

    # Verify extractor was used correctly
    assert result["platform"] == "Maine Farmland Trust"
    assert "Kennebec" in result["location"]
    assert result["price"] == "$650,000"
    assert result["price_bucket"] == "$600K - $900K"
    assert result["acreage"] == "75.0 acres"

    # Verify Notion API was NOT called (use_notion=False)
    mock_create_notion_entry.assert_not_called()


@pytest.mark.asyncio
async def test_process_listings_multiple(mock_get_page_content, mock_create_notion_entry):
    """Test processing multiple listings at once."""
    urls = [
        "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101",
        "https://www.landandfarm.com/property/40_Acres_in_Brunswick-123456",
        "https://farmlink.mainefarmlandtrust.org/property/75-acre-farm"
    ]

    results = await process_listings(urls, use_notion=True, concurrency=2)

    # Verify we got all results
    assert len(results) == 3

    # Check that each result has the expected platform
    platforms = [r["platform"] for r in results]
    assert "Realtor.com" in platforms
    assert "Land and Farm" in platforms
    assert "Maine Farmland Trust" in platforms

    # Verify Notion API was called for each listing
    assert mock_create_notion_entry.call_count == 3


@pytest.mark.asyncio
async def test_process_listings_with_error(mock_get_page_content, mock_create_notion_entry):
    """Test processing listings where one fails."""
    # Make one URL fail by returning invalid HTML
    async def side_effect(url, **kwargs):
        if "invalid.com" in url:
            return BeautifulSoup("<html><body>Invalid content</body></html>", 'html.parser')
        else:
            return await mock_get_page_content.side_effect(url, **kwargs)

    mock_get_page_content.side_effect = side_effect

    urls = [
        "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101",
        "https://www.invalid.com/no-extractor",
        "https://www.landandfarm.com/property/40_Acres_in_Brunswick-123456"
    ]

    results = await process_listings(urls, use_notion=True)

    # Should get all results, with one error
    assert len(results) == 3

    # Count successful and failed results
    success_count = sum(1 for r in results if "error" not in r)
    error_count = sum(1 for r in results if "error" in r)

    assert success_count == 2
    assert error_count == 1

    # Verify Notion API was called only for successful listings
    assert mock_create_notion_entry.call_count == 2


@pytest.mark.asyncio
async def test_extractor_selection(mock_get_page_content):
    """Test that the correct extractor is selected for each URL."""
    # Test Realtor.com URL
    url = "https://www.realtor.com/example"
    extractor = get_extractor_for_url(url)
    assert extractor == RealtorExtractor

    # Test Land and Farm URL
    url = "https://www.landandfarm.com/example"
    extractor = get_extractor_for_url(url)
    assert extractor == LandAndFarmExtractor

    # Test Maine Farmland Trust URL
    url = "https://farmlink.mainefarmlandtrust.org/example"
    extractor = get_extractor_for_url(url)
    assert extractor.__name__ == "FarmLinkExtractor"

    # Test unsupported URL
    url = "https://example.com"
    extractor = get_extractor_for_url(url)
    assert extractor is None
