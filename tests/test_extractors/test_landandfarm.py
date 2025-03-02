# tests/test_extractors/test_landandfarm.py
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from new_england_listings.extractors import LandAndFarmExtractor


class TestLandAndFarmExtractor:
    """Tests for the LandAndFarm extractor which processes listings from landandfarm.com."""

    @pytest.fixture
    def extractor(self):
        """Create a LandAndFarmExtractor instance for testing."""
        return LandAndFarmExtractor("https://www.landandfarm.com/property/test-123456/")

    @pytest.fixture
    def sample_html(self):
        """Create sample HTML for a Land and Farm property listing."""
        return """
        <html>
            <head>
                <title>40 Acres Farm in Brunswick, ME | Land and Farm</title>
            </head>
            <body>
                <h1 class="property-title">40 Acres Farm in Brunswick, ME</h1>
                <div class="price-container">
                    <span class="price">$499,000</span>
                </div>
                <div class="location-container">
                    <div class="address">123 Farm Road</div>
                    <div class="city">Brunswick</div>
                    <div class="state">ME</div>
                    <div class="zip">04011</div>
                </div>
                <div class="property-details">
                    <ul>
                        <li>40 acres of beautiful farmland</li>
                        <li>Built in 2005</li>
                        <li>3 bedrooms, 2 bathrooms</li>
                        <li>Barn and equipment storage</li>
                    </ul>
                </div>
                <div class="property-description">
                    <p>Beautiful farm property with established fields and infrastructure.</p>
                </div>
            </body>
        </html>
        """

    def test_platform_name(self, extractor):
        """Test that the platform name is correct."""
        assert extractor.platform_name == "Land and Farm"

    def test_extract_with_sample_html(self, extractor, sample_html):
        """Test extraction with sample HTML."""
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(sample_html, 'html.parser')

        # Extract data
        data = extractor.extract(soup)

        # Verify extracted data
        assert data["platform"] == "Land and Farm"
        assert data["listing_name"] == "40 Acres Farm in Brunswick, ME"
        assert "Brunswick, ME" in data["location"]
        assert data["price"] == "$499,000"
        assert data["price_bucket"] == "$300K - $600K"
        assert data["acreage"] == "40.0 acres"
        assert data["acreage_bucket"] == "Large (20-50 acres)"
        assert data["property_type"] == "Farm"
        assert "Beautiful farm property" in data["notes"]

    def test_extract_listing_name(self, extractor, sample_html):
        """Test extracting listing name."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        extractor.soup = soup

        result = extractor.extract_listing_name()
        assert result == "40 Acres Farm in Brunswick, ME"

        # Test with missing title
        soup = BeautifulSoup(
            "<html><body>No title</body></html>", 'html.parser')
        extractor.soup = soup

        # Should fall back to URL or default
        with patch.object(extractor, '_extract_listing_name_from_url', return_value="URL Listing Name"):
            result = extractor.extract_listing_name()
            assert result == "URL Listing Name"

    def test_extract_location(self, extractor, sample_html):
        """Test extracting location."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        extractor.soup = soup

        result = extractor.extract_location()
        assert "Brunswick, ME" in result

        # Test with missing location elements
        soup = BeautifulSoup(
            "<html><body>No location</body></html>", 'html.parser')
        extractor.soup = soup

        # Should fall back to URL
        with patch.object(extractor.location_service, 'parse_location_from_url', return_value="Augusta, ME"):
            result = extractor.extract_location()
            assert result == "Augusta, ME"

        # Test with no location info at all
        with patch.object(extractor.location_service, 'parse_location_from_url', return_value=None):
            result = extractor.extract_location()
            assert result == "Location Unknown"

    def test_extract_price(self, extractor, sample_html):
        """Test extracting price."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        extractor.soup = soup

        price, bucket = extractor.extract_price()
        assert price == "$499,000"
        assert bucket == "$300K - $600K"

        # Test with missing price
        soup = BeautifulSoup(
            "<html><body>No price</body></html>", 'html.parser')
        extractor.soup = soup

        price, bucket = extractor.extract_price()
        assert price == "Contact for Price"
        assert bucket == "N/A"

    def test_extract_acreage_info(self, extractor, sample_html):
        """Test extracting acreage information."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        extractor.soup = soup

        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "40.0 acres"
        assert bucket == "Large (20-50 acres)"

        # Test with missing acreage
        soup = BeautifulSoup(
            "<html><body>No acreage</body></html>", 'html.parser')
        extractor.soup = soup

        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "Not specified"
        assert bucket == "Unknown"

    def test_extract_property_type(self, extractor, sample_html):
        """Test determining property type."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        extractor.soup = soup

        # Title contains "Farm" so should determine it's a farm
        property_type = extractor._determine_property_type()
        assert property_type == "Farm"

        # Test with different property type indicators
        soup = BeautifulSoup(
            "<html><body><div>Residential property with 3 bedrooms</div></body></html>", 'html.parser')
        extractor.soup = soup

        property_type = extractor._determine_property_type()
        assert property_type == "Single Family"

        # Test with vacant land
        soup = BeautifulSoup(
            "<html><body><div>Vacant land for sale</div></body></html>", 'html.parser')
        extractor.soup = soup

        property_type = extractor._determine_property_type()
        assert property_type == "Land"

    @patch('new_england_listings.utils.location_service.LocationService.get_comprehensive_location_info')
    def test_extract_additional_data(self, mock_location_info, extractor, sample_html):
        """Test extracting additional data."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        extractor.soup = soup

        # Simulate basic extraction first
        data = extractor.extract(soup)
        extractor.data = data

        # Mock location info
        mock_location_info.return_value = {
            "distance_to_portland": 25.5,
            "portland_distance_bucket": "21-40",
            "town_population": 20000,
            "town_pop_bucket": "Medium (15K-50K)",
            "school_district": "Brunswick Schools",
            "school_rating": 8.0,
            "school_rating_cat": "Above Average (8-9)",
            "hospital_distance": 10.5,
            "hospital_distance_bucket": "0-10",
            "closest_hospital": "Mid Coast Hospital",
            "restaurants_nearby": 5,
            "grocery_stores_nearby": 2
        }

        # Extract additional data
        extractor.extract_additional_data()

        # Verify enriched data
        assert extractor.data["distance_to_portland"] == 25.5
        assert extractor.data["portland_distance_bucket"] == "21-40"
        assert extractor.data["town_population"] == 20000
        assert extractor.data["town_pop_bucket"] == "Medium (15K-50K)"
        assert extractor.data["school_district"] == "Brunswick Schools"
        assert extractor.data["school_rating"] == 8.0
        assert extractor.data["school_rating_cat"] == "Above Average (8-9)"
        assert extractor.data["restaurants_nearby"] == 5
        assert extractor.data["grocery_stores_nearby"] == 2

        # Verify house details
        assert "3 bedrooms" in extractor.data["house_details"]
        assert "2 bathrooms" in extractor.data["house_details"]

        # Verify farm details
        assert "Barn" in extractor.data["farm_details"]
        assert "equipment storage" in extractor.data["farm_details"]

    def test_error_handling(self, extractor):
        """Test error handling during extraction."""
        # Create minimal HTML
        soup = BeautifulSoup(
            "<html><body>Minimal content</body></html>", 'html.parser')

        # Simulate error in extract_listing_name
        with patch.object(extractor, 'extract_listing_name', side_effect=Exception("Test error")):
            # Should not raise exception but record the error
            result = extractor.extract(soup)

            assert "extraction_error" in result
            assert result["extraction_status"] == "failed"
            # Basic data still present
            assert result["platform"] == "Land and Farm"

        # Verify specific extraction fail-safe
        soup = BeautifulSoup(
            "<html><body>Missing info</body></html>", 'html.parser')
        extractor.soup = soup

        # Test with error in location extraction but other methods working
        with patch.object(extractor, 'extract_location', side_effect=Exception("Location error")):
            with patch.object(extractor, 'extract_listing_name', return_value="Test Listing"):
                with patch.object(extractor, 'extract_price', return_value=("$500,000", "$300K - $600K")):
                    with patch.object(extractor, 'extract_acreage_info', return_value=("10 acres", "Medium (5-20 acres)")):
                        # Should continue and use fallbacks for missing data
                        result = extractor.extract(soup)

                        # These should be from our mocks
                        assert result["listing_name"] == "Test Listing"
                        assert result["price"] == "$500,000"
                        assert result["acreage"] == "10 acres"

                        # This should be the default due to our error
                        assert result["location"] == "Location Unknown"

    def test_integration_minimal(self):
        """A simple integration test with minimal real input."""
        # Using a fake URL to test just the initialization and basic behavior
        url = "https://www.landandfarm.com/property/test-123456/"
        extractor = LandAndFarmExtractor(url)

        # Verify basic properties
        assert extractor.platform_name == "Land and Farm"
        assert extractor.url == url
