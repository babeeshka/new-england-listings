# tests/test_utils/test_location_service.py
import pytest
from unittest.mock import patch, MagicMock
from new_england_listings.utils.location_service import (
    LocationService, TextProcessingService,
)


@pytest.fixture
def location_service():
    """Create LocationService instance."""
    return LocationService()


@pytest.fixture
def mock_geolocator():
    """Mock geopy.geocoders.Nominatim."""
    with patch('new_england_listings.utils.location_service.Nominatim') as mock:
        # Setup the mock geocode method
        instance = mock.return_value

        # Configure geocode to return different results based on query
        def mock_geocode(query, **kwargs):
            if "Portland, ME" in query:
                result = MagicMock()
                result.latitude = 43.6591
                result.longitude = -70.2568
                return result
            elif "Brunswick, ME" in query:
                result = MagicMock()
                result.latitude = 43.9145
                result.longitude = -69.9653
                return result
            return None

        instance.geocode = mock_geocode
        yield mock


class TestLocationService:

    def test_parse_location(self, location_service):
        """Test parsing different location formats."""
        # Test standard "City, State" format
        result = location_service.parse_location("Portland, ME")
        assert result["is_valid"] is True
        assert result["parsed_components"]["city"] == "Portland"
        assert result["parsed_components"]["state"] == "ME"
        assert result["standardized_name"] == "Portland, ME"

        # Test "City, State ZIP" format
        result = location_service.parse_location("Portland, ME 04101")
        assert result["is_valid"] is True
        assert result["parsed_components"]["city"] == "Portland"
        assert result["parsed_components"]["state"] == "ME"
        assert result["parsed_components"]["zip_code"] == "04101"

        # Test county format
        result = location_service.parse_location("Cumberland County, ME")
        assert result["is_valid"] is True
        assert "county" in result["parsed_components"]

        # Test invalid location
        result = location_service.parse_location("")
        assert result["is_valid"] is False

        result = location_service.parse_location("Location Unknown")
        assert result["is_valid"] is False

    def test_parse_location_from_url(self, location_service):
        """Test extracting location from URL."""
        # Test Realtor.com URL
        url = "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101"
        result = location_service.parse_location_from_url(url)
        assert result is not None
        assert "Portland" in result
        assert "ME" in result

        # Test URL without location
        url = "https://example.com/property"
        result = location_service.parse_location_from_url(url)
        assert result is None

    @patch('new_england_listings.utils.location_service.LocationService.get_location_coordinates')
    def test_get_distance(self, mock_get_coords, location_service):
        """Test distance calculation."""
        # Mock coordinates for two points
        mock_get_coords.side_effect = [
            (43.6591, -70.2568),  # Portland
            (43.9145, -69.9653)   # Brunswick
        ]

        # Calculate distance between Portland and Brunswick
        distance = location_service.get_distance(
            "Portland, ME", "Brunswick, ME")

        # Should be approximately 20 miles
        assert 15 <= distance <= 25

        # Test with direct coordinates
        distance = location_service.get_distance(
            (43.6591, -70.2568),  # Portland
            (43.9145, -69.9653)   # Brunswick
        )
        assert 15 <= distance <= 25

    def test_get_bucket(self, location_service):
        """Test bucket categorization."""
        # Test price buckets
        buckets = {
            0: "Under $300K",
            300000: "$300K - $600K",
            600000: "$600K - $900K",
            900000: "$900K - $1.2M"
        }

        assert location_service.get_bucket(250000, buckets) == "Under $300K"
        assert location_service.get_bucket(450000, buckets) == "$300K - $600K"
        assert location_service.get_bucket(750000, buckets) == "$600K - $900K"
        assert location_service.get_bucket(1000000, buckets) == "$900K - $1.2M"

        # Test default strategy for value above all thresholds
        assert location_service.get_bucket(2000000, buckets) == "$900K - $1.2M"

        # Test first strategy for value above all thresholds
        assert location_service.get_bucket(
            2000000, buckets, default_strategy='first') == "Under $300K"

        # Test none strategy for value above all thresholds
        assert location_service.get_bucket(
            2000000, buckets, default_strategy='none') is None

    @patch('new_england_listings.utils.location_service.LocationService.get_location_coordinates')
    @patch('new_england_listings.utils.location_service.LocationService.get_distance')
    def test_get_comprehensive_location_info(self, mock_distance, mock_coords, location_service):
        """Test comprehensive location info retrieval."""
        # Mock coordinates for Portland
        mock_coords.return_value = (43.6591, -70.2568)

        # Mock distances
        mock_distance.return_value = 15.5

        # Get info for Brunswick
        result = location_service.get_comprehensive_location_info(
            "Brunswick, ME")

        # Verify basic location data
        assert result["state"] == "ME"
        assert result["latitude"] == 43.6591
        assert result["longitude"] == -70.2568

        # Verify calculated fields
        assert "distance_to_portland" in result
        assert "portland_distance_bucket" in result

        # Verify defaults for amenities
        assert result["restaurants_nearby"] >= 1
        assert result["grocery_stores_nearby"] >= 1

        # Test with invalid location
        mock_coords.return_value = None
        result = location_service.get_comprehensive_location_info(
            "Invalid Location")

        # Should still have basic defaults
        assert "restaurants_nearby" in result
        assert "grocery_stores_nearby" in result


class TestTextProcessingService:

    def test_standardize_price(self):
        """Test price standardization."""
        # Create service
        service = TextProcessingService()

        # Test various price formats
        assert service.standardize_price(
            "$500,000") == ("$500,000", "$300K - $600K")
        assert service.standardize_price(
            "$1,500,000") == ("$1.5M", "$1.5M - $2M")
        assert service.standardize_price(
            "$250k") == ("$250,000", "Under $300K")

        # Test contact for price
        assert service.standardize_price(
            "Contact agent") == ("Contact for Price", "N/A")
        assert service.standardize_price("") == ("Contact for Price", "N/A")
        assert service.standardize_price(None) == ("Contact for Price", "N/A")

    def test_standardize_acreage(self):
        """Test acreage standardization."""
        # Create service
        service = TextProcessingService()

        # Test various acreage formats
        assert service.standardize_acreage("10 acres") == (
            "10.0 acres", "Medium (5-20 acres)")
        assert service.standardize_acreage("2.5 acres") == (
            "2.5 acres", "Small (1-5 acres)")
        assert service.standardize_acreage("150 acres") == (
            "150.0 acres", "Extensive (100+ acres)")

        # Test not specified
        assert service.standardize_acreage("") == ("Not specified", "Unknown")
        assert service.standardize_acreage(
            None) == ("Not specified", "Unknown")

    def test_extract_property_type(self):
        """Test property type extraction."""
        # Create service
        service = TextProcessingService()

        # Test various property descriptions
        assert service.extract_property_type(
            "Single Family Home") == "Single Family"
        assert service.extract_property_type("Farm land with barn") == "Farm"
        assert service.extract_property_type(
            "Commercial property") == "Commercial"
        assert service.extract_property_type("Vacant land") == "Land"
        assert service.extract_property_type("Unknown") == "Unknown"

    def test_clean_html_text(self):
        """Test HTML text cleaning."""
        # Create service
        service = TextProcessingService()

        # Test cleaning of various text
        assert service.clean_html_text("  Hello  World  ") == "Hello World"
        assert service.clean_html_text("Hello&nbsp;World") == "Hello World"
        assert service.clean_html_text(
            "Line 1\nLine 2\tTab") == "Line 1 Line 2 Tab"
        assert service.clean_html_text("") == ""
        assert service.clean_html_text(None) == ""
