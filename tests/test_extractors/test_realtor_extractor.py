# tests/test_extractors/test_realtor_extractor.py
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from new_england_listings.extractors.realtor import RealtorExtractor, REALTOR_SELECTORS


class TestRealtorExtractorInit:
    def test_init(self):
        """Test initialization of RealtorExtractor."""
        extractor = RealtorExtractor(
            "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101_M12345-67890")

        # Verify basic properties
        assert extractor.platform_name == "Realtor.com"
        assert extractor.url == "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101_M12345-67890"

        # URL data should be extracted
        assert isinstance(extractor.url_data, dict)
        assert "location" in extractor.url_data
        assert "Portland, ME" in extractor.url_data["location"]


class TestUrlDataExtraction:
    def test_extract_from_url_basic(self):
        """Test extracting data from a standard Realtor.com URL."""
        extractor = RealtorExtractor(
            "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101_M12345-67890")
        url_data = extractor._extract_from_url()

        assert url_data["location"] == "Portland, ME 04101"
        assert url_data["listing_name"] == "123 Main St, Portland, ME 04101"

    def test_extract_from_url_with_property_details(self):
        """Test extracting property details from URL with embedded information."""
        extractor = RealtorExtractor(
            "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101_M12345-67890/3-bed-2-bath-1500-sq-ft")
        url_data = extractor._extract_from_url()

        assert "house_details" in url_data
        assert "3 bedrooms" in url_data["house_details"]
        assert "2 bathrooms" in url_data["house_details"]
        assert "1500 sqft" in url_data["house_details"]

    def test_extract_from_url_with_price(self):
        """Test extracting price from URL with embedded price information."""
        extractor = RealtorExtractor(
            "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101_M12345-67890/price-500000")
        url_data = extractor._extract_from_url()

        assert "price" in url_data
        assert url_data["price"] == "$500,000"


class TestContentVerification:
    @pytest.fixture
    def extractor(self):
        return RealtorExtractor("https://www.realtor.com/example")

    def test_verify_page_content_valid(self, extractor):
        """Test verification of valid page content."""
        html = """
        <html>
            <head><title>Test Listing</title></head>
            <body>
                <div data-testid="list-price">$500,000</div>
                <div data-testid="property-meta"></div>
                <div data-testid="address">123 Main St, Portland, ME</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor._verify_page_content() is True

    def test_verify_page_content_blocked(self, extractor):
        """Test detection of blocked content."""
        html = """
        <html>
            <head><title>Security Check</title></head>
            <body>
                <h1>Please complete this captcha</h1>
                <div>We need to verify you're not a robot.</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        with patch.object(extractor.soup, 'get_text', return_value="please verify you are not a robot captcha"):
            assert extractor._verify_page_content() is False

    def test_verify_page_content_meta_blocked(self, extractor):
        """Test detection of blocked content via meta tag."""
        html = """
        <html>
            <head>
                <meta name="extraction-status" content="blocked-but-attempting">
            </head>
            <body>
                <div>Some content</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        # This should return True because we want to continue extraction even when blocked
        assert extractor._verify_page_content() is True


class TestListingNameExtraction:
    @pytest.fixture
    def extractor(self):
        return RealtorExtractor("https://www.realtor.com/example")

    def test_extract_listing_name_from_address(self, extractor):
        """Test extracting listing name from address element."""
        html = """
        <html>
            <div data-testid="address">123 Main St, Portland, ME</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor.extract_listing_name() == "123 Main St, Portland, ME"

    def test_extract_listing_name_from_h1(self, extractor):
        """Test extracting listing name from h1 when address not found."""
        html = """
        <html>
            <h1>456 Oak St, Portland, ME</h1>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor.extract_listing_name() == "456 Oak St, Portland, ME"

    def test_extract_listing_name_fallback_to_url(self, extractor):
        """Test falling back to URL data when name can't be extracted from page."""
        html = """<html><body>No address here</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock URL data
        extractor.url_data = {"listing_name": "789 Pine St, Portland, ME"}

        assert extractor.extract_listing_name() == "789 Pine St, Portland, ME"

    def test_extract_listing_name_error_handling(self, extractor):
        """Test error handling during name extraction."""
        html = """<html><body>Error test</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock to raise exception
        with patch.object(extractor.soup, 'find', side_effect=Exception("Test error")):
            # Should fall back to URL data
            extractor.url_data = {"listing_name": "Error Fallback"}
            assert extractor.extract_listing_name() == "Error Fallback"

            # If no URL fallback, should return default
            extractor.url_data = {}
            assert extractor.extract_listing_name() == "Untitled Listing"


class TestLocationExtraction:
    @pytest.fixture
    def extractor(self):
        return RealtorExtractor("https://www.realtor.com/example")

    def test_extract_location_from_components(self, extractor):
        """Test extracting location from address and city/state components."""
        html = """
        <html>
            <div data-testid="address">123 Main St</div>
            <div data-testid="city-state">Portland, ME</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor.extract_location() == "123 Main St, Portland, ME"

    def test_extract_location_from_h1_h2(self, extractor):
        """Test extracting location from headings when selectors not found."""
        html = """
        <html>
            <h1>Beautiful Home in Portland, ME</h1>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor.extract_location() == "Portland, ME"

    def test_extract_location_fallback_to_url(self, extractor):
        """Test falling back to URL data when location can't be extracted from page."""
        html = """<html><body>No location here</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock URL data
        extractor.url_data = {"location": "Lewiston, ME"}

        assert extractor.extract_location() == "Lewiston, ME"

    def test_extract_location_with_meta_tag(self, extractor):
        """Test extracting location from meta tag."""
        html = """
        <html>
            <head>
                <meta name="url-extracted-location" content="Augusta, ME">
            </head>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor.extract_location() == "Augusta, ME"

    def test_validate_location(self, extractor):
        """Test location validation."""
        assert extractor._validate_location("Portland, ME") is True
        assert extractor._validate_location("Boston, MA") is True
        assert extractor._validate_location(
            "New York, NY") is False  # Not in New England
        assert extractor._validate_location("") is False
        assert extractor._validate_location(None) is False


class TestPriceExtraction:
    @pytest.fixture
    def extractor(self):
        return RealtorExtractor("https://www.realtor.com/example")

    def test_extract_price_main_element(self, extractor):
        """Test extracting price from main price element."""
        html = """
        <html>
            <div data-testid="list-price">$500,000</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = extractor.extract_price()
        assert price == "$500,000"
        assert bucket == "$300K - $600K"

    def test_extract_price_formatted_element(self, extractor):
        """Test extracting price from formatted price element."""
        html = """
        <html>
            <div data-testid="price">$750,000</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = extractor.extract_price()
        assert price == "$750,000"
        assert bucket == "$600K - $900K"

    def test_extract_price_container(self, extractor):
        """Test extracting price from price container."""
        html = """
        <html>
            <div class="Price__Component">$1,200,000</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = extractor.extract_price()
        assert price == "$1.2M"
        assert bucket == "$1.2M - $1.5M"

    def test_extract_price_text_pattern(self, extractor):
        """Test extracting price from text pattern."""
        html = """
        <html>
            <div>Beautiful home for $850,000</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = extractor.extract_price()
        assert price == "$850,000"
        assert bucket == "$600K - $900K"

    def test_extract_price_not_found(self, extractor):
        """Test handling when price is not found."""
        html = """<html><body>No price here</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = extractor.extract_price()
        assert price == "Contact for Price"
        assert bucket == "N/A"


class TestAcreageExtraction:
    @pytest.fixture
    def extractor(self):
        return RealtorExtractor("https://www.realtor.com/example")

    def test_extract_acreage_from_lot_element(self, extractor):
        """Test extracting acreage from lot element."""
        html = """
        <html>
            <div data-testid="property-meta-lot-size">2 acres</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "2.0 acres"
        assert bucket == "Small (1-5 acres)"

    def test_extract_acreage_from_sqft(self, extractor):
        """Test extracting acreage from square feet."""
        html = """
        <html>
            <div data-testid="property-meta-lot-size">43560 sq ft</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "1.00 acres"
        assert bucket == "Small (1-5 acres)"

    def test_extract_acreage_from_text(self, extractor):
        """Test extracting acreage from general text."""
        html = """
        <html>
            <div>Property includes 5 acres of land</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "5.0 acres"
        assert bucket == "Medium (5-20 acres)"

    def test_extract_acreage_from_description(self, extractor):
        """Test extracting acreage from description."""
        html = """
        <html>
            <div class="property-description">Beautiful 10 acre property with mountain views.</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock _extract_description method
        with patch.object(extractor, '_extract_description', return_value="Beautiful 10 acre property with mountain views."):
            acreage, bucket = extractor.extract_acreage_info()
            assert acreage == "10.0 acres"
            assert bucket == "Medium (5-20 acres)"

    def test_extract_acreage_not_found(self, extractor):
        """Test handling when acreage is not found."""
        html = """<html><body>No acreage here</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')
        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "Not specified"
        assert bucket == "Unknown"


class TestPropertyDetailsExtraction:
    @pytest.fixture
    def extractor(self):
        return RealtorExtractor("https://www.realtor.com/example")

    def test_extract_property_details_basic(self, extractor):
        """Test extracting basic property details."""
        html = """
        <html>
            <div data-testid="property-meta">
                <div data-testid="property-meta-beds">3</div>
                <div data-testid="property-meta-baths">2</div>
                <div data-testid="property-meta-sqft">2000</div>
                <div data-testid="property-type">Single Family</div>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        details = extractor.extract_property_details()

        assert details["beds"] == "3"
        assert details["baths"] == "2"
        assert details["sqft"] == "2000"
        assert details["property_type"] == "Single Family"

    def test_extract_property_details_generic(self, extractor):
        """Test extracting details from generic elements when specific selectors not found."""
        html = """
        <html>
            <div>3 bed, 2 bath, 2000 sq ft Single Family Home</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        details = extractor.extract_property_details()

        assert details["beds"] == "3"
        assert details["baths"] == "2"
        assert details.get("sqft") is not None

    def test_extract_property_details_no_details(self, extractor):
        """Test handling when no details are found."""
        html = """<html><body>No details here</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')
        details = extractor.extract_property_details()

        assert isinstance(details, dict)
        assert len(details) == 0


class TestPropertyTypeDetection:
    @pytest.fixture
    def extractor(self):
        return RealtorExtractor("https://www.realtor.com/example")

    def test_determine_property_type_explicit(self, extractor):
        """Test determining property type from explicit type in details."""
        details = {"property_type": "single family"}
        assert extractor.determine_property_type(details) == "Single Family"

        details = {"property_type": "farm"}
        assert extractor.determine_property_type(details) == "Farm"

        details = {"property_type": "commercial"}
        assert extractor.determine_property_type(details) == "Commercial"

    def test_determine_property_type_from_features(self, extractor):
        """Test determining property type from features."""
        details = {
            "features": ["barn", "pasture", "farmhouse"]
        }
        assert extractor.determine_property_type(details) == "Farm"

        details = {
            "features": ["living room", "bedroom", "bathroom"]
        }
        assert extractor.determine_property_type(details) == "Single Family"

    def test_determine_property_type_from_beds_baths(self, extractor):
        """Test determining property type from bedrooms and bathrooms."""
        details = {
            "beds": "3",
            "baths": "2"
        }
        assert extractor.determine_property_type(details) == "Single Family"

    def test_determine_property_type_fallback(self, extractor):
        """Test fallback to URL data."""
        details = {}
        extractor.url_data = {"property_type": "Land"}
        assert extractor.determine_property_type(details) == "Land"

    def test_determine_property_type_unknown(self, extractor):
        """Test when property type cannot be determined."""
        details = {}
        extractor.url_data = {}
        assert extractor.determine_property_type(details) == "Unknown"


class TestAdditionalDataExtraction:
    @pytest.fixture
    def extractor(self):
        return RealtorExtractor("https://www.realtor.com/example")

    @patch.object(RealtorExtractor, "extract_property_details")
    def test_extract_additional_data_complete(self, mock_details, extractor):
        """Test extracting complete additional data."""
        # Setup mock
        mock_details.return_value = {
            "beds": "3",
            "baths": "2",
            "sqft": "2000",
            "property_type": "Single Family",
            "features": ["Garage", "Swimming Pool", "Fireplace"]
        }

        # Also mock _extract_description
        with patch.object(extractor, '_extract_description', return_value="Beautiful home with great views."):
            # Test
            extractor.extract_additional_data()

            # Verify results
            assert extractor.data["property_type"] == "Single Family"
            assert extractor.data["house_details"] == "3 bedrooms | 2 bathrooms | 2000 sqft"
            assert extractor.data["notes"] == "Beautiful home with great views."
            assert extractor.data["other_amenities"] == "Garage | Swimming Pool | Fireplace"

    @patch.object(RealtorExtractor, "extract_property_details")
    @patch.object(RealtorExtractor, "_extract_description")
    def test_extract_additional_data_with_error(self, mock_desc, mock_details, extractor):
        """Test error handling during additional data extraction."""
        # Setup mocks to raise exception
        mock_details.side_effect = Exception("Test error")
        mock_desc.return_value = "Description"

        # Test - should not raise exception
        extractor.extract_additional_data()

        # Error should be recorded
        assert "extraction_error" in extractor.raw_data


class TestMainExtraction:
    @pytest.fixture
    def extractor(self):
        return RealtorExtractor("https://www.realtor.com/example")

    @patch.object(RealtorExtractor, "_verify_page_content", return_value=True)
    @patch.object(RealtorExtractor, "extract_listing_name", return_value="Test Listing")
    @patch.object(RealtorExtractor, "extract_location", return_value="Portland, ME")
    @patch.object(RealtorExtractor, "extract_price", return_value=("$500,000", "$300K - $600K"))
    @patch.object(RealtorExtractor, "extract_acreage_info", return_value=("10.0 acres", "Medium (5-20 acres)"))
    @patch.object(RealtorExtractor, "extract_additional_data")
    def test_extract_successful(self, mock_additional, mock_acreage, mock_price,
                                mock_location, mock_name, mock_verify, extractor):
        """Test successful extraction."""
        # Create sample soup
        soup = BeautifulSoup("<html><body>Test</body></html>", 'html.parser')

        # Test
        result = extractor.extract(soup)

        # Verify results
        assert result["listing_name"] == "Test Listing"
        assert result["location"] == "Portland, ME"
        assert result["price"] == "$500,000"
        assert result["price_bucket"] == "$300K - $600K"
        assert result["acreage"] == "10.0 acres"
        assert result["acreage_bucket"] == "Medium (5-20 acres)"

        # Verify mocks were called
        mock_verify.assert_called_once()
        mock_name.assert_called_once()
        mock_location.assert_called_once()
        mock_price.assert_called_once()
        mock_acreage.assert_called_once()
        mock_additional.assert_called_once()

    @patch.object(RealtorExtractor, "_verify_page_content", return_value=False)
    def test_extract_blocked_page(self, mock_verify, extractor):
        """Test extraction when page is blocked but continuing with URL data."""
        # Create sample soup
        soup = BeautifulSoup(
            "<html><body>Blocked</body></html>", 'html.parser')

        # Setup URL data
        extractor.url_data = {
            "listing_name": "URL Listing",
            "location": "URL Location, ME",
            "price": "$600,000",
            "house_details": "3 bedrooms | 2 bathrooms"
        }

        # Test - should not raise exception and should use URL data
        result = extractor.extract(soup)

        # Verify URL data was used
        assert result["listing_name"] == "URL Listing"
        assert result["location"] == "URL Location, ME"

    @patch.object(RealtorExtractor, "extract_listing_name")
    def test_extract_with_error(self, mock_name, extractor):
        """Test handling errors during extraction."""
        # Setup mock to raise exception
        mock_name.side_effect = Exception("Test error")

        # Create sample soup
        soup = BeautifulSoup("<html><body>Test</body></html>", 'html.parser')

        # Test - should not raise exception
        result = extractor.extract(soup)

        # Error should be recorded but extraction should continue
        assert "extraction_error" in result
