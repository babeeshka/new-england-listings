# tests/test_integration/test_notion.py
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from new_england_listings.utils.notion.client import (
    NotionClient, create_notion_entry, NotionAPIError,
    parse_price_to_number, parse_acreage_to_number, truncate_text
)
from new_england_listings.models.base import PropertyListing

# Sample test data


@pytest.fixture
def sample_property_data():
    return {
        "url": "https://example.com/test-property",
        "platform": "Test Platform",
        "listing_name": "Test Property Listing",
        "location": "Portland, ME",
        "price": "$500,000",
        "price_bucket": "$300K - $600K",
        "property_type": "Single Family",
        "acreage": "5.0 acres",
        "acreage_bucket": "Medium (5-20 acres)",
        "listing_date": "2023-01-15",
        "distance_to_portland": 10.5,
        "portland_distance_bucket": "0-10",
        "school_rating": 8.5,
        "school_rating_cat": "Above Average (8-9)",
        "other_amenities": "Schools | Shopping | Parks"
    }


@pytest.fixture
def mock_notion_client():
    with patch('notion_client.Client') as mock_client:
        # Setup mock client
        instance = mock_client.return_value
        instance.pages.create.return_value = {"id": "test-page-id"}
        instance.pages.update.return_value = {
            "id": "test-page-id", "updated": True}
        instance.databases.query.return_value = {"results": []}

        yield mock_client


class TestNotionClient:

    def test_initialization(self, mock_notion_client):
        """Test NotionClient initialization."""
        client = NotionClient(api_key="test-key", database_id="test-db")
        assert client.api_key == "test-key"
        assert client.database_id == "test-db"
        mock_notion_client.assert_called_once_with(auth="test-key")

    def test_create_entry(self, mock_notion_client, sample_property_data):
        """Test creating a new entry in Notion."""
        client = NotionClient(api_key="test-key", database_id="test-db")

        # Configure mock to return no existing entries
        mock_notion_client.return_value.databases.query.return_value = {
            "results": []}

        # Call create_entry
        result = client.create_entry(sample_property_data)

        # Verify the result
        assert result["id"] == "test-page-id"

        # Verify the client was called with correct parameters
        mock_notion_client.return_value.pages.create.assert_called_once()
        call_args = mock_notion_client.return_value.pages.create.call_args
        assert call_args[1]["parent"]["database_id"] == "test-db"

        # Verify properties were formatted correctly
        properties = call_args[1]["properties"]
        assert properties["Listing Name"]["title"][0]["text"]["content"] == "Test Property Listing"
        assert properties["URL"]["url"] == "https://example.com/test-property"
        assert properties["Platform"]["select"]["name"] == "Test Platform"
        assert properties["Price"]["number"] == 500000
        assert properties["Acreage"]["number"] == 5.0

    def test_update_existing_entry(self, mock_notion_client, sample_property_data):
        """Test updating an existing entry in Notion."""
        client = NotionClient(api_key="test-key", database_id="test-db")

        # Configure mock to return an existing entry
        mock_notion_client.return_value.databases.query.return_value = {
            "results": [{"id": "existing-page-id"}]
        }

        # Call create_entry (should update existing)
        result = client.create_entry(
            sample_property_data, update_if_exists=True)

        # Verify the client was called with correct parameters
        mock_notion_client.return_value.pages.update.assert_called_once()
        call_args = mock_notion_client.return_value.pages.update.call_args
        assert call_args[1]["page_id"] == "existing-page-id"

    def test_api_error_handling(self, mock_notion_client, sample_property_data):
        """Test handling of API errors."""
        client = NotionClient(api_key="test-key", database_id="test-db")

        # Configure mock to raise an error
        mock_notion_client.return_value.pages.create.side_effect = Exception(
            "API Error")

        # Should raise NotionAPIError
        with pytest.raises(Exception):
            client.create_entry(sample_property_data)

    def test_property_formatting(self, sample_property_data):
        """Test property formatting for Notion."""
        client = NotionClient(api_key="test-key", database_id="test-db")

        # Format properties
        properties = client._format_properties(sample_property_data)

        # Verify formatting
        assert properties["Listing Name"]["title"][0]["text"]["content"] == "Test Property Listing"
        assert properties["URL"]["url"] == "https://example.com/test-property"
        assert properties["Platform"]["select"]["name"] == "Test Platform"
        assert properties["Price"]["number"] == 500000
        assert properties["Acreage"]["number"] == 5.0
        assert properties["Listing Date"]["rich_text"][0]["text"]["content"] == "2023-01-15"

        # Verify multi-select formatting for amenities
        assert len(properties["Other Amenities"]["multi_select"]) == 3
        assert properties["Other Amenities"]["multi_select"][0]["name"] == "Schools"

    def test_with_pydantic_model(self, mock_notion_client):
        """Test using a Pydantic model directly."""
        # Create a PropertyListing model
        model = PropertyListing(
            url="https://example.com/model-test",
            platform="Test Platform",
            listing_name="Pydantic Model Test",
            location="Portland, ME",
            price="$400,000",
            price_bucket="$300K - $600K",
            property_type="Single Family",
            acreage="10.0 acres",
            acreage_bucket="Medium (5-20 acres)"
        )

        client = NotionClient(api_key="test-key", database_id="test-db")

        # Call create_entry with model
        result = client.create_entry(model)

        # Verify the result
        assert result["id"] == "test-page-id"

        # Verify the client was called with correct parameters
        call_args = mock_notion_client.return_value.pages.create.call_args
        properties = call_args[1]["properties"]
        assert properties["Listing Name"]["title"][0]["text"]["content"] == "Pydantic Model Test"


class TestUtilityFunctions:

    def test_truncate_text(self):
        """Test text truncation function."""
        # Test normal case
        assert truncate_text("Short text", 20) == "Short text"

        # Test truncation
        long_text = "This is a very long text that should be truncated"
        assert truncate_text(long_text, 20) == "This is a very long..."
        assert len(truncate_text(long_text, 20)) == 20

        # Test empty text
        assert truncate_text("", 20) == ""
        assert truncate_text(None, 20) == ""

    def test_parse_price_to_number(self):
        """Test price parsing function."""
        # Test normal formats
        assert parse_price_to_number("$500,000") == 500000
        assert parse_price_to_number("$1.5M") == 1500000
        assert parse_price_to_number("$2,500K") == 2500000

        # Test invalid formats
        assert parse_price_to_number("Contact for Price") is None
        assert parse_price_to_number("") is None
        assert parse_price_to_number(None) is None

    def test_parse_acreage_to_number(self):
        """Test acreage parsing function."""
        # Test normal formats
        assert parse_acreage_to_number("5.0 acres") == 5.0
        assert parse_acreage_to_number("10 acres") == 10.0
        assert parse_acreage_to_number("2.5 acre lot") == 2.5

        # Test invalid formats
        assert parse_acreage_to_number("Not specified") is None
        assert parse_acreage_to_number("") is None
        assert parse_acreage_to_number(None) is None


@pytest.mark.parametrize("entry_data", [
    # Basic property data
    {
        "url": "https://example.com/test1",
        "platform": "Test Platform",
        "listing_name": "Basic Property",
        "location": "Portland, ME",
        "price": "$300,000",
        "price_bucket": "$300K - $600K",
        "property_type": "Single Family",
    },
    # Property with all fields
    {
        "url": "https://example.com/test2",
        "platform": "Test Platform",
        "listing_name": "Complete Property",
        "location": "Brunswick, ME",
        "price": "$750,000",
        "price_bucket": "$600K - $900K",
        "property_type": "Farm",
        "acreage": "25.0 acres",
        "acreage_bucket": "Large (20-50 acres)",
        "listing_date": "2023-01-15",
        "last_updated": datetime.now(),
        "notes": "Beautiful property with mountain views",
        "house_details": "4 bedrooms | 3 bathrooms | 2500 sqft",
        "farm_details": "Barn | Pasture | Stream",
        "other_amenities": "Schools | Parks | Hospital"
    }
])
def test_create_notion_entry(mock_notion_client, entry_data):
    """Test create_notion_entry with various data formats."""
    # Call the convenience function
    result = create_notion_entry(entry_data)

    # Verify result
    assert result["id"] == "test-page-id"

    # Verify client was called
    mock_notion_client.return_value.pages.create.assert_called_once()
