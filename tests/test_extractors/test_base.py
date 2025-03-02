# tests/test_extractors/test_base.py
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
import json
from datetime import datetime
from new_england_listings.extractors.base import BaseExtractor, ExtractionError

# Create a concrete implementation of BaseExtractor for testing


class TestExtractor(BaseExtractor):
    @property
    def platform_name(self):
        return "Test Platform"

    def extract_listing_name(self):
        return "Test Listing"

    def extract_location(self):
        return "Portland, ME"

    def extract_price(self):
        return "$500,000", "$300K - $600K"

    def extract_acreage_info(self):
        return "10.0 acres", "Medium (5-20 acres)"


class TestBaseExtractorInit:
    def test_init_base_values(self):
        """Test initializing BaseExtractor with default values."""
        extractor = TestExtractor("https://example.com/test")

        # Verify URL is stored
        assert extractor.url == "https://example.com/test"

        # Verify raw_data is initialized with basic info
        assert "extraction_source" in extractor.raw_data
        assert extractor.raw_data["extraction_source"] == "Test Platform"
        assert extractor.raw_data["url"] == "https://example.com/test"

        # Verify data is initialized with default values
        assert extractor.data["url"] == "https://example.com/test"
        assert extractor.data["platform"] == "Test Platform"
        assert extractor.data["listing_name"] == "Untitled Listing"
        assert extractor.data["location"] == "Location Unknown"
        assert extractor.data["price"] == "Contact for Price"
        assert extractor.data["price_bucket"] == "N/A"

        # Verify service objects are initialized
        assert extractor.location_service is not None
        assert extractor.text_processor is not None


class TestExtractionWithFallbacks:
    @pytest.fixture
    def extractor(self):
        return TestExtractor("https://example.com/test")

    def test_extract_with_fallbacks_first_method_succeeds(self, extractor):
        """Test using the first method when it succeeds."""
        def method1():
            return "Success"

        def method2():
            return "Fallback"

        result = extractor.extract_with_fallbacks(
            [method1, method2], default_value="Default")
        assert result == "Success"

    def test_extract_with_fallbacks_first_method_fails(self, extractor):
        """Test falling back to the second method when the first fails."""
        def method1():
            raise ValueError("Test error")

        def method2():
            return "Fallback"

        result = extractor.extract_with_fallbacks(
            [method1, method2], default_value="Default")
        assert result == "Fallback"

    def test_extract_with_fallbacks_all_methods_fail(self, extractor):
        """Test using default value when all methods fail."""
        def method1():
            raise ValueError("Test error 1")

        def method2():
            raise ValueError("Test error 2")

        result = extractor.extract_with_fallbacks(
            [method1, method2], default_value="Default")
        assert result == "Default"

    def test_extract_with_fallbacks_empty_methods(self, extractor):
        """Test handling empty methods list."""
        result = extractor.extract_with_fallbacks([], default_value="Default")
        assert result == "Default"


class TestPageContentVerification:
    @pytest.fixture
    def extractor(self):
        return TestExtractor("https://example.com/test")

    def test_verify_page_content_valid(self, extractor):
        """Test verifying valid page content."""
        # Create a soup with sufficient content
        html = """
        <html>
            <body>
                <h1>Test Listing</h1>
                <div>This is a test listing with sufficient content to pass validation.</div>
                <p>Here is some more content to ensure the text length exceeds the minimum requirement.</p>
                <p>Even more content to be extra sure.</p>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor._verify_page_content() is True

    def test_verify_page_content_insufficient(self, extractor):
        """Test verifying insufficient page content."""
        # Create a soup with minimal content
        html = "<html><body>Too short</body></html>"
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor._verify_page_content() is False

    def test_verify_page_content_blocking(self, extractor):
        """Test detecting blocking content."""
        # Create a soup with CAPTCHA content
        html = """
        <html>
            <body>
                <h1>Security Check</h1>
                <div>Please complete this captcha to continue.</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor._verify_page_content() is False

    def test_verify_page_content_none(self, extractor):
        """Test handling None soup."""
        extractor.soup = None
        assert extractor._verify_page_content() is False


@patch("new_england_listings.extractors.base.LocationService")
class TestProcessLocation:
    @pytest.fixture
    def extractor(self):
        return TestExtractor("https://example.com/test")

    def test_process_location_valid(self, mock_location_service, extractor):
        """Test processing valid location."""
        # Setup mock
        mock_instance = mock_location_service.return_value
        mock_instance.get_comprehensive_location_info.return_value = {
            "nearest_city": "Portland",
            "state": "ME",
            "distance_to_portland": 0,
            "school_district": "Portland School District"
        }

        # Test
        result = extractor._process_location("Portland, ME")

        # Verify
        assert result["is_valid"] is True
        assert result["raw"] == "Portland, ME"
        assert result["nearest_city"] == "Portland"
        assert result["state"] == "ME"
        mock_instance.get_comprehensive_location_info.assert_called_once_with(
            "Portland, ME")

    def test_process_location_invalid(self, mock_location_service, extractor):
        """Test processing invalid location."""
        result = extractor._process_location("Location Unknown")
        assert result["is_valid"] is False
        assert result["raw"] == "Location Unknown"

    def test_process_location_empty(self, mock_location_service, extractor):
        """Test processing empty location."""
        result = extractor._process_location("")
        assert result["is_valid"] is False
        assert result["raw"] == ""

        result = extractor._process_location(None)
        assert result["is_valid"] is False
        assert result["raw"] is None

    def test_process_location_error(self, mock_location_service, extractor):
        """Test handling errors during location processing."""
        # Setup mock to raise exception
        mock_instance = mock_location_service.return_value
        mock_instance.get_comprehensive_location_info.side_effect = Exception(
            "Test error")

        # Test
        result = extractor._process_location("Portland, ME")

        # Verify
        assert result["is_valid"] is False
        assert result["raw"] == "Portland, ME"


class TestMainExtraction:
    @pytest.fixture
    def extractor(self):
        return TestExtractor("https://example.com/test")

    @pytest.fixture
    def sample_soup(self):
        html = """
        <html>
            <head><title>Test Listing</title></head>
            <body>
                <h1>Test Listing in Portland, ME</h1>
                <div class="price">$500,000</div>
                <div class="location">Portland, ME</div>
                <div class="details">10 acres of beautiful land</div>
                <div class="description">This is a test description for a property.</div>
            </body>
        </html>
        """
        return BeautifulSoup(html, 'html.parser')

    @patch.object(TestExtractor, "extract_listing_name")
    @patch.object(TestExtractor, "extract_location")
    @patch.object(TestExtractor, "extract_price")
    @patch.object(TestExtractor, "extract_acreage_info")
    @patch.object(TestExtractor, "_extract_house_details")
    @patch.object(TestExtractor, "_extract_farm_details")
    @patch.object(TestExtractor, "_extract_description")
    def test_extract_full_success(self, mock_desc, mock_farm, mock_house,
                                  mock_acreage, mock_price, mock_location,
                                  mock_name, extractor, sample_soup):
        """Test successful extraction of all data."""
        # Setup mocks
        mock_name.return_value = "Test Listing"
        mock_location.return_value = "Portland, ME"
        mock_price.return_value = ("$500,000", "$300K - $600K")
        mock_acreage.return_value = ("10.0 acres", "Medium (5-20 acres)")
        mock_house.return_value = "3 bed | 2 bath"
        mock_farm.return_value = "Barn | Pasture"
        mock_desc.return_value = "This is a test description."

        # Test
        result = extractor.extract(sample_soup)

        # Verify results
        assert result["listing_name"] == "Test Listing"
        assert result["location"] == "Portland, ME"
        assert result["price"] == "$500,000"
        assert result["price_bucket"] == "$300K - $600K"
        assert result["acreage"] == "10.0 acres"
        assert result["acreage_bucket"] == "Medium (5-20 acres)"
        assert result["house_details"] == "3 bed | 2 bath"
        assert result["farm_details"] == "Barn | Pasture"
        assert result["notes"] == "This is a test description."

        # Verify mocks were called
        mock_name.assert_called_once()
        mock_location.assert_called_once()
        mock_price.assert_called_once()
        mock_acreage.assert_called_once()

    @patch.object(TestExtractor, "extract_listing_name")
    def test_extract_with_errors(self, mock_name, extractor, sample_soup):
        """Test extraction with errors in some methods."""
        # Setup mock to raise exception
        mock_name.side_effect = Exception("Test error")

        # Test
        result = extractor.extract(sample_soup)

        # Verify extraction continued despite error
        assert "extraction_error" in result
        assert result["extraction_status"] == "failed"

        # Core fields should still be extracted using the concrete implementation methods
        assert result["location"] == "Portland, ME"
        assert result["price"] == "$500,000"
        assert result["price_bucket"] == "$300K - $600K"

    def test_extract_with_invalid_page(self, extractor):
        """Test handling invalid page content."""
        # Create a soup with insufficient content
        bad_soup = BeautifulSoup(
            "<html><body>Too short</body></html>", 'html.parser')

        # Patch _verify_page_content to fail
        with patch.object(TestExtractor, '_verify_page_content', return_value=False):
            result = extractor.extract(bad_soup)

            # Even with verification failure, extraction should continue
            # From our concrete implementation
            assert result["listing_name"] == "Test Listing"
            assert result["location"] == "Portland, ME"
            assert result["price"] == "$500,000"


class TestHelperMethods:
    @pytest.fixture
    def extractor(self):
        return TestExtractor("https://example.com/test")

    @pytest.fixture
    def sample_soup(self):
        html = """
        <html>
            <body>
                <div class="property-details">
                    <p>3 bedrooms, 2 bathrooms, 2000 sq ft</p>
                    <p>Built in 2010 with garage</p>
                </div>
                <div class="farm-details">
                    <p>10 acres tillable, barn, irrigation system</p>
                    <p>2 silos and fencing</p>
                </div>
                <div class="property-description">
                    <p>This is a beautiful property with mountain views.</p>
                    <p>Great location near schools and shops.</p>
                </div>
            </body>
        </html>
        """
        return BeautifulSoup(html, 'html.parser')

    def test_extract_house_details(self, extractor, sample_soup):
        """Test extracting house details."""
        extractor.soup = sample_soup
        result = extractor._extract_house_details()
        assert "bedrooms" in result.lower()
        assert "bathrooms" in result.lower()
        assert "sq ft" in result.lower()

    def test_extract_farm_details(self, extractor, sample_soup):
        """Test extracting farm details."""
        extractor.soup = sample_soup
        result = extractor._extract_farm_details()
        assert "acres tillable" in result.lower()
        assert "barn" in result.lower()
        assert "irrigation" in result.lower()

    def test_extract_description(self, extractor, sample_soup):
        """Test extracting property description."""
        extractor.soup = sample_soup
        result = extractor._extract_description()
        assert "beautiful property" in result.lower()
        assert "mountain views" in result.lower()

    def test_extract_restaurants_nearby(self, extractor):
        """Test extracting restaurants nearby (should return None by default)."""
        result = extractor._extract_restaurants_nearby()
        assert result is None

    def test_extract_grocery_stores_nearby(self, extractor):
        """Test extracting grocery stores nearby (should return None by default)."""
        result = extractor._extract_grocery_stores_nearby()
        assert result is None


class TestExtractionError:
    def test_extraction_error_init(self):
        """Test initializing ExtractionError."""
        error = ExtractionError(
            message="Test error",
            extractor="Test Extractor",
            raw_data={"test": "data"},
            original_exception=ValueError("Original error")
        )

        assert str(error) == "Test error"
        assert error.extractor == "Test Extractor"
        assert error.raw_data == {"test": "data"}
        assert isinstance(error.timestamp, datetime)
        assert isinstance(error.original_exception, ValueError)
        assert error.stacktrace is not None

    def test_extraction_error_without_exception(self):
        """Test initializing ExtractionError without original exception."""
        error = ExtractionError(
            message="Test error",
            extractor="Test Extractor"
        )

        assert str(error) == "Test error"
        assert error.extractor == "Test Extractor"
        assert error.raw_data == {}
        assert error.original_exception is None
