# tests/test_extractors/test_farmlink.py
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from new_england_listings.extractors import FarmLinkExtractor


@pytest.fixture
def farmlink_extractor():
    """Create FarmLinkExtractor instance."""
    return FarmLinkExtractor("https://farmlink.mainefarmlandtrust.org/farm-id-1234")


@pytest.fixture
def sample_html():
    """Create sample HTML for FarmLink."""
    return """
    <html>
        <head>
            <title>Farm ID 1234 | Maine Farmland Trust</title>
        </head>
        <body>
            <div class="info-right_property-description">
                <h2>Farm ID 1234</h2>
                <div>
                    <span class="text-color-primary text-weight-bold">ME County:</span>
                    <div class="text-color-primary display-inline">Kennebec</div>
                </div>
                <div>
                    <span class="text-color-primary text-weight-bold">Total Acres:</span>
                    <div class="text-color-primary display-inline">75</div>
                </div>
                <div>
                    <span class="text-color-primary text-weight-bold">Price:</span>
                    <div class="text-color-primary display-inline">$650,000</div>
                </div>
                <div>
                    <span class="text-color-primary text-weight-bold">Farm House:</span>
                    <div class="text-color-primary display-inline">Yes, 3 bedrooms</div>
                </div>
                <div>
                    <span class="text-color-primary text-weight-bold">Entry Date:</span>
                    <div class="text-color-primary display-inline">January 15, 2023</div>
                </div>
                <div class="text-color-primary w-richtext">
                    <p>Beautiful farm property with 75 acres of land. Features include:</p>
                    <ul>
                        <li>50 acres of tillable land</li>
                        <li>25 acres of woodland</li>
                        <li>Barn and equipment storage</li>
                        <li>Well water and irrigation system</li>
                        <li>3 bedroom farmhouse</li>
                    </ul>
                </div>
            </div>
        </body>
    </html>
    """


class TestFarmLinkExtractor:

    def test_platform_name(self, farmlink_extractor):
        """Test platform name property."""
        assert farmlink_extractor.platform_name == "Maine FarmLink"

    def test_find_field_value(self, farmlink_extractor, sample_html):
        """Test finding field values."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        farmlink_extractor.soup = soup

        # Test finding values for different fields
        assert farmlink_extractor._find_field_value("ME County:") == "Kennebec"
        assert farmlink_extractor._find_field_value("Total Acres:") == "75"
        assert farmlink_extractor._find_field_value("Price:") == "$650,000"
        assert farmlink_extractor._find_field_value(
            "Farm House:") == "Yes, 3 bedrooms"
        assert farmlink_extractor._find_field_value(
            "Entry Date:") == "January 15, 2023"

        # Test field that doesn't exist
        assert farmlink_extractor._find_field_value(
            "Nonexistent Field:") is None

    def test_extract_listing_name(self, farmlink_extractor, sample_html):
        """Test listing name extraction."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        farmlink_extractor.soup = soup

        listing_name = farmlink_extractor.extract_listing_name()
        assert listing_name == "Farm ID 1234"

        # Test fallback to URL
        simple_html = "<html><body>Empty page</body></html>"
        soup = BeautifulSoup(simple_html, 'html.parser')
        farmlink_extractor.soup = soup

        listing_name = farmlink_extractor.extract_listing_name()
        assert "Farm ID" in listing_name

    def test_extract_location(self, farmlink_extractor, sample_html):
        """Test location extraction."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        farmlink_extractor.soup = soup

        location = farmlink_extractor.extract_location()
        assert location == "Kennebec County, ME"

        # Test missing location
        simple_html = "<html><body>Empty page</body></html>"
        soup = BeautifulSoup(simple_html, 'html.parser')
        farmlink_extractor.soup = soup

        location = farmlink_extractor.extract_location()
        assert location == "Location Unknown"

    def test_extract_price(self, farmlink_extractor, sample_html):
        """Test price extraction."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        farmlink_extractor.soup = soup

        price, price_bucket = farmlink_extractor.extract_price()
        assert price == "$650,000"
        assert price_bucket == "$600K - $900K"

        # Test missing price
        simple_html = "<html><body>Empty page</body></html>"
        soup = BeautifulSoup(simple_html, 'html.parser')
        farmlink_extractor.soup = soup

        price, price_bucket = farmlink_extractor.extract_price()
        assert price == "Contact for Price"
        assert price_bucket == "N/A"

    def test_extract_acreage_info(self, farmlink_extractor, sample_html):
        """Test acreage extraction."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        farmlink_extractor.soup = soup

        acreage, acreage_bucket = farmlink_extractor.extract_acreage_info()
        assert acreage == "75.0 acres"
        assert acreage_bucket == "Very Large (50-100 acres)"

        # Test missing acreage
        simple_html = "<html><body>Empty page</body></html>"
        soup = BeautifulSoup(simple_html, 'html.parser')
        farmlink_extractor.soup = soup

        acreage, acreage_bucket = farmlink_extractor.extract_acreage_info()
        assert acreage == "Not specified"
        assert acreage_bucket == "Unknown"

    def test_extract_amenities(self, farmlink_extractor, sample_html):
        """Test amenities extraction."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        farmlink_extractor.soup = soup

        amenities = farmlink_extractor.extract_amenities()
        assert len(amenities) > 0
        assert "Barn" in amenities
        assert "Well water" in amenities
        assert "Irrigation system" in amenities

    def test_extract_additional_data(self, farmlink_extractor, sample_html):
        """Test extraction of additional property data."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        farmlink_extractor.soup = soup

        # Start with basic data
        farmlink_extractor.data = {
            "platform": "Maine FarmLink",
            "listing_name": "Farm ID 1234",
            "location": "Kennebec County, ME",
            "price": "$650,000",
            "price_bucket": "$600K - $900K",
            "acreage": "75.0 acres",
            "acreage_bucket": "Very Large (50-100 acres)",
            "property_type": "Farm"
        }

        # Call extract_additional_data
        farmlink_extractor.extract_additional_data()

        # Check extracted additional data
        assert "house_details" in farmlink_extractor.data
        assert "3 bedrooms" in farmlink_extractor.data["house_details"]

        assert "notes" in farmlink_extractor.data
        assert "Beautiful farm property" in farmlink_extractor.data["notes"]

        assert "listing_date" in farmlink_extractor.data
        assert farmlink_extractor.data["listing_date"] == "2023-01-15"

    def test_extract(self, farmlink_extractor, sample_html):
        """Test full extraction process."""
        soup = BeautifulSoup(sample_html, 'html.parser')
        result = farmlink_extractor.extract(soup)

        # Check core data
        assert result["platform"] == "Maine FarmLink"
        assert result["listing_name"] == "Farm ID 1234"
        assert result["location"] == "Kennebec County, ME"
        assert result["price"] == "$650,000"
        assert result["price_bucket"] == "$600K - $900K"
        assert result["acreage"] == "75.0 acres"
        assert result["acreage_bucket"] == "Very Large (50-100 acres)"
        assert result["property_type"] == "Farm"

        # Check additional data
        assert "house_details" in result
        assert "notes" in result
        assert "listing_date" in result

        # Check raw data
        assert "extraction_status" in result
        assert result["extraction_status"] == "success"
