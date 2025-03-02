# tests/test_extractors/test_zillow.py
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from new_england_listings.extractors.zillow import ZillowExtractor


class TestZillowExtractorInit:
    def test_init(self):
        """Test initialization of ZillowExtractor."""
        url = "https://www.zillow.com/homedetails/123-Main-St-Portland-ME-04101/12345_zpid/"
        extractor = ZillowExtractor(url)

        assert extractor.platform_name == "Zillow"
        assert extractor.url == url
        assert extractor.zpid == "12345"
        assert extractor.property_data is None
        assert extractor.is_blocked is False


class TestZpidExtraction:
    def test_extract_zpid_from_url(self):
        """Test extracting the Zillow Property ID (zpid) from URL."""
        url = "https://www.zillow.com/homedetails/123-Main-St-Portland-ME-04101/12345_zpid/"
        extractor = ZillowExtractor(url)

        assert extractor.zpid == "12345"

    def test_extract_zpid_from_complex_url(self):
        """Test extracting zpid from URL with additional parameters."""
        url = "https://www.zillow.com/homedetails/123-Main-St-Portland-ME-04101/12345_zpid/?view=photos"
        extractor = ZillowExtractor(url)

        assert extractor.zpid == "12345"

    def test_extract_zpid_missing(self):
        """Test handling URL without zpid."""
        url = "https://www.zillow.com/homes/for_sale/Portland-ME/"
        extractor = ZillowExtractor(url)

        assert extractor.zpid is None


class TestBlockingDetection:
    @pytest.fixture
    def extractor(self):
        return ZillowExtractor("https://www.zillow.com/homedetails/12345_zpid/")

    def test_check_for_blocking_positive(self, extractor):
        """Test detecting blocking/CAPTCHA content."""
        html = """
        <html>
            <body>
                <h1>Security Check</h1>
                <p>Please verify you are human by completing this captcha.</p>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        assert extractor._check_for_blocking() is True

    def test_check_for_blocking_empty_content(self, extractor):
        """Test detecting blocking via minimal content."""
        html = """
        <html>
            <body>
                <div>Minimal text</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        assert extractor._check_for_blocking() is True

    def test_check_for_blocking_missing_key_elements(self, extractor):
        """Test detecting blocking through missing key elements."""
        html = """
        <html>
            <body>
                <div>This page has content but no price or address elements</div>
                <p>More content to exceed the minimal length check</p>
                <p>Even more content to be sure we get past that check</p>
                <p>But it's missing key Zillow data elements</p>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        assert extractor._check_for_blocking() is True

    def test_check_for_blocking_negative(self, extractor):
        """Test normal page not detected as blocked."""
        html = """
        <html>
            <body>
                <span data-testid="price">$500,000</span>
                <div data-testid="home-details-chip">123 Main St, Portland, ME</div>
                <div data-testid="facts-container">
                    <div>3 bds</div>
                    <div>2 ba</div>
                    <div>2,000 sqft</div>
                </div>
                <div>Lots of other content that makes this a valid page</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        assert extractor._check_for_blocking() is False


class TestLocationFromUrl:
    @pytest.fixture
    def extractor(self):
        return ZillowExtractor("https://www.zillow.com/homedetails/12345_zpid/")

    def test_extract_location_from_url_full(self, extractor):
        """Test extracting location from URL with city, state, zip."""
        extractor.url = "https://www.zillow.com/homedetails/123-Main-St-Portland-ME-04101/12345_zpid/"

        result = extractor._extract_location_from_url()
        assert result == "Portland, ME"

    def test_extract_location_from_url_no_zip(self, extractor):
        """Test extracting location from URL without zip code."""
        extractor.url = "https://www.zillow.com/homedetails/123-Main-St-Brunswick-ME/12345_zpid/"

        result = extractor._extract_location_from_url()
        assert result == "Brunswick, ME"

    def test_extract_location_from_url_complex_city(self, extractor):
        """Test extracting location with multi-word city name."""
        extractor.url = "https://www.zillow.com/homedetails/123-Main-St-South-Portland-ME-04106/12345_zpid/"

        result = extractor._extract_location_from_url()
        assert result == "South Portland, ME"

    def test_extract_location_from_url_invalid(self, extractor):
        """Test handling invalid URL format."""
        extractor.url = "https://www.zillow.com/homes/Portland-ME/"

        result = extractor._extract_location_from_url()
        assert result is None


class TestListingNameFromUrl:
    @pytest.fixture
    def extractor(self):
        return ZillowExtractor("https://www.zillow.com/homedetails/12345_zpid/")

    def test_extract_listing_name_from_url(self, extractor):
        """Test generating listing name from URL."""
        extractor.url = "https://www.zillow.com/homedetails/123-Main-St-Portland-ME-04101/12345_zpid/"

        result = extractor._extract_listing_name_from_url()
        assert "123 Main St Portland ME" in result

    def test_extract_listing_name_from_url_cleanup(self, extractor):
        """Test cleaning up listing name from URL."""
        extractor.url = "https://www.zillow.com/homedetails/Beautiful-Cape-123-Oak-St-Brunswick-ME-04011/12345_zpid/"

        result = extractor._extract_listing_name_from_url()
        assert "Beautiful Cape 123 Oak St Brunswick ME" in result

    def test_extract_listing_name_from_url_fallback(self, extractor):
        """Test fallback when URL doesn't have name components."""
        extractor.url = "https://www.zillow.com/homes/for_sale/12345_zpid/"

        result = extractor._extract_listing_name_from_url()
        assert "Zillow Property 12345" in result


class TestListingNameExtraction:
    @pytest.fixture
    def extractor(self):
        return ZillowExtractor("https://www.zillow.com/homedetails/12345_zpid/")

    def test_extract_listing_name_from_json(self, extractor):
        """Test extracting listing name from property JSON data."""
        # Setup property_data
        extractor.property_data = {
            "address": {
                "streetAddress": "123 Main St",
                "city": "Portland",
                "state": "ME",
                "zipcode": "04101"
            }
        }

        # Create minimal soup
        extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

        assert extractor.extract_listing_name() == "123 Main St, Portland, ME 04101"

    def test_extract_listing_name_from_address_element(self, extractor):
        """Test extracting listing name from address element."""
        html = """
        <html>
            <body>
                <div data-testid="home-details-chip">123 Main St, Portland, ME 04101</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        assert extractor.extract_listing_name() == "123 Main St, Portland, ME 04101"

    def test_extract_listing_name_from_h1(self, extractor):
        """Test extracting listing name from h1 element."""
        html = """
        <html>
            <body>
                <h1>123 Main St, Portland, ME 04101</h1>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        assert extractor.extract_listing_name() == "123 Main St, Portland, ME 04101"

    def test_extract_listing_name_from_url_fallback(self, extractor):
        """Test fallback to URL extraction when no elements found."""
        html = """<html><body>No address info</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock _extract_listing_name_from_url
        with patch.object(extractor, '_extract_listing_name_from_url', return_value="123 Main St Portland ME"):
            assert extractor.extract_listing_name() == "123 Main St Portland ME"


class TestLocationExtraction:
    @pytest.fixture
    def extractor(self):
        return ZillowExtractor("https://www.zillow.com/homedetails/12345_zpid/")

    def test_extract_location_from_json(self, extractor):
        """Test extracting location from property JSON data."""
        # Setup property_data
        extractor.property_data = {
            "address": {
                "city": "Portland",
                "state": "ME",
                "zipcode": "04101"
            }
        }

        # Create minimal soup
        extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

        assert extractor.extract_location() == "Portland, ME 04101"

    def test_extract_location_from_address_element(self, extractor):
        """Test extracting location from address element."""
        html = """
        <html>
            <body>
                <div data-testid="home-details-chip">123 Main St, Portland, ME 04101</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        assert "Portland, ME" in extractor.extract_location()

    def test_extract_location_from_meta_tags(self, extractor):
        """Test extracting location from meta tags."""
        html = """
        <html>
            <head>
                <meta property="og:locality" content="Portland">
                <meta property="og:region" content="ME">
            </head>
            <body>
                <div>Content</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        assert extractor.extract_location() == "Portland, ME"

    def test_extract_location_from_url_fallback(self, extractor):
        """Test fallback to URL extraction when no elements found."""
        html = """<html><body>No location info</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock _extract_location_from_url
        with patch.object(extractor, '_extract_location_from_url', return_value="Brunswick, ME"):
            assert extractor.extract_location() == "Brunswick, ME"

    def test_extract_location_not_found(self, extractor):
        """Test handling when location cannot be found."""
        html = """<html><body>No location info</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock _extract_location_from_url to return None
        with patch.object(extractor, '_extract_location_from_url', return_value=None):
            assert extractor.extract_location() == "Location Unknown"


class TestPriceExtraction:
    @pytest.fixture
    def extractor(self):
        return ZillowExtractor("https://www.zillow.com/homedetails/12345_zpid/")

    def test_extract_price_from_json_direct(self, extractor):
        """Test extracting price from direct price property in JSON."""
        # Setup property_data with direct price
        extractor.property_data = {
            "price": 500000
        }

        # Create minimal soup
        extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

        price, bucket = extractor.extract_price()
        assert price == "$500,000"
        assert bucket == "$300K - $600K"

    def test_extract_price_from_json_formatted(self, extractor):
        """Test extracting price from formatted price property in JSON."""
        # Setup property_data with formatted price
        extractor.property_data = {
            "priceFormatted": "$750,000"
        }

        # Create minimal soup
        extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

        price, bucket = extractor.extract_price()
        assert price == "$750,000"
        assert bucket == "$600K - $900K"

    def test_extract_price_from_json_nested(self, extractor):
        """Test extracting price from nested property in JSON."""
        # Setup property_data with nested price
        extractor.property_data = {
            "price": {
                "value": 1200000
            }
        }

        # Create minimal soup
        extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

        price, bucket = extractor.extract_price()
        assert price == "$1.2M"
        assert bucket == "$1.2M - $1.5M"

    def test_extract_price_from_element(self, extractor):
        """Test extracting price from price element."""
        html = """
        <html>
            <body>
                <span data-testid="price">$650,000</span>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        price, bucket = extractor.extract_price()
        assert price == "$650,000"
        assert bucket == "$600K - $900K"

    def test_extract_price_from_text_pattern(self, extractor):
        """Test extracting price from text pattern."""
        html = """
        <html>
            <body>
                <div>Home Value: $890,000</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        price, bucket = extractor.extract_price()
        assert price == "$890,000"
        assert bucket == "$600K - $900K"

    def test_extract_price_from_url(self, extractor):
        """Test extracting price from URL."""
        extractor.url = "https://www.zillow.com/homedetails/123-Main-St-Portland-ME-04101-475k/12345_zpid/"

        # Create minimal soup
        extractor.soup = BeautifulSoup(
            "<html><body>No price info</body></html>", 'html.parser')

        # Mock property_data to be None
        extractor.property_data = None

        price, bucket = extractor.extract_price()
        assert price == "$475,000"
        assert bucket == "$300K - $600K"

    def test_extract_price_not_found(self, extractor):
        """Test handling when price cannot be found."""
        html = """<html><body>No price info</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock property_data to be None
        extractor.property_data = None

        price, bucket = extractor.extract_price()
        assert price == "Contact for Price"
        assert bucket == "N/A"


class TestAcreageExtraction:
    @pytest.fixture
    def extractor(self):
        return ZillowExtractor("https://www.zillow.com/homedetails/12345_zpid/")

    def test_extract_acreage_from_json_with_unit(self, extractor):
        """Test extracting acreage from JSON with unit."""
        # Setup property_data
        extractor.property_data = {
            "resoFacts": {
                "lotSize": 2.5,
                "lotSizeUnit": "acres"
            }
        }

        # Create minimal soup
        extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "2.5 acres"
        assert bucket == "Small (1-5 acres)"

    def test_extract_acreage_from_json_sqft(self, extractor):
        """Test extracting acreage from JSON with square feet."""
        # Setup property_data
        extractor.property_data = {
            "resoFacts": {
                "lotSize": 43560,
                "lotSizeUnit": "sqft"
            }
        }

        # Create minimal soup
        extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "1.00 acres"
        assert bucket == "Small (1-5 acres)"

    def test_extract_acreage_from_json_direct(self, extractor):
        """Test extracting acreage from direct properties in JSON."""
        # Setup property_data
        extractor.property_data = {
            "lotSize": 10,
            "lotSizeUnit": "acres"
        }

        # Create minimal soup
        extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "10.0 acres"
        assert bucket == "Medium (5-20 acres)"

    def test_extract_acreage_from_hdp_data(self, extractor):
        """Test extracting acreage from hdpData in JSON."""
        # Setup property_data
        extractor.property_data = {
            "hdpData": {
                "homeInfo": {
                    "lotSize": 87120  # 2 acres in sqft
                }
            }
        }

        # Create minimal soup
        extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "2.00 acres"
        assert bucket == "Small (1-5 acres)"

    def test_extract_acreage_not_found(self, extractor):
        """Test handling when acreage cannot be found."""
        html = """<html><body>No acreage info</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock property_data to be None
        extractor.property_data = None

        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "Not specified"
        assert bucket == "Unknown"


class TestAdditionalDataExtraction:
    @pytest.fixture
    def extractor(self):
        return ZillowExtractor("https://www.zillow.com/homedetails/12345_zpid/")

    @patch("new_england_listings.extractors.zillow.LocationService.get_comprehensive_location_info")
    def test_extract_additional_data_with_location(self, mock_location_info, extractor):
        """Test extracting additional data with valid location."""
        # Mock property details extraction
        with patch.object(extractor, 'extract_property_details', return_value={
            "bedrooms": "3",
            "bathrooms": "2",
            "sqft": "2000",
            "year_built": "2015",
            "description": "Beautiful property with mountain views."
        }):
            # Mock location info
            mock_location_info.return_value = {
                "distance_to_portland": 30.5,
                "portland_distance_bucket": "21-40",
                "town_population": 20000,
                "town_pop_bucket": "Medium (15K-50K)",
                "school_district": "Brunswick Schools",
                "school_rating": 8.0,
                "school_rating_cat": "Above Average (8-9)",
                "hospital_distance": 15.2,
                "hospital_distance_bucket": "11-20",
                "closest_hospital": "Brunswick Hospital",
                "restaurants_nearby": 4,
                "grocery_stores_nearby": 2
            }

            # Set valid location and other necessary data
            extractor.data = {
                "location": "Brunswick, ME",
                "platform": "Zillow"
            }

            # Create minimal soup
            extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

            # Extract additional data
            extractor.extract_additional_data()

            # Check that house details were extracted
            assert extractor.data["house_details"] == "3 bedrooms | 2 bathrooms | 2000 sqft | Built 2015"

            # Check that description was extracted as notes
            assert extractor.data["notes"] == "Beautiful property with mountain views."

            # Check location data enrichment
            assert extractor.data["distance_to_portland"] == 30.5
            assert extractor.data["portland_distance_bucket"] == "21-40"
            assert extractor.data["town_population"] == 20000
            assert extractor.data["town_pop_bucket"] == "Medium (15K-50K)"
            assert extractor.data["school_district"] == "Brunswick Schools"
            assert extractor.data["school_rating"] == 8.0
            assert extractor.data["restaurants_nearby"] == 4
            assert extractor.data["grocery_stores_nearby"] == 2

    def test_extract_additional_data_error_handling(self, extractor):
        """Test error handling during additional data extraction."""
        # Mock super().extract_additional_data to raise exception
        with patch('new_england_listings.extractors.base.BaseExtractor.extract_additional_data',
                   side_effect=Exception("Test error")):
            # Set minimal data
            extractor.data = {
                "location": "Location Unknown",
                "platform": "Zillow"
            }

            # Create minimal soup
            extractor.soup = BeautifulSoup("<html></html>", 'html.parser')

            # Should not raise exception
            extractor.extract_additional_data()

            # Error should be logged
            assert "extraction_error" in extractor.raw_data

            # Default values should be set
            assert extractor.data.get("restaurants_nearby") is not None
            assert extractor.data.get("grocery_stores_nearby") is not None


class TestMainExtraction:
    @pytest.fixture
    def extractor(self):
        return ZillowExtractor("https://www.zillow.com/homedetails/12345_zpid/")

    @patch.object(ZillowExtractor, "_check_for_blocking", return_value=False)
    @patch.object(ZillowExtractor, "extract_listing_name", return_value="123 Main St, Portland, ME")
    @patch.object(ZillowExtractor, "extract_location", return_value="Portland, ME")
    @patch.object(ZillowExtractor, "extract_price", return_value=("$550,000", "$300K - $600K"))
    @patch.object(ZillowExtractor, "extract_acreage_info", return_value=("0.25 acres", "Tiny (Under 1 acre)"))
    @patch.object(ZillowExtractor, "extract_additional_data")
    def test_extract_successful(self, mock_additional, mock_acreage, mock_price,
                                mock_location, mock_name, mock_blocking, extractor):
        """Test successful extraction."""
        # Create sample soup
        soup = BeautifulSoup("<html><body>Test</body></html>", 'html.parser')

        # Test
        result = extractor.extract(soup)

        # Verify results
        assert result["listing_name"] == "123 Main St, Portland, ME"
        assert result["location"] == "Portland, ME"
        assert result["price"] == "$550,000"
        assert result["price_bucket"] == "$300K - $600K"
        assert result["acreage"] == "0.25 acres"
        assert result["acreage_bucket"] == "Tiny (Under 1 acre)"

        # Verify extraction status
        assert extractor.raw_data["extraction_status"] == "success"

        # Verify mocks were called
        mock_blocking.assert_called_once()
        mock_name.assert_called_once()
        mock_location.assert_called_once()
        mock_price.assert_called_once()
        mock_acreage.assert_called_once()
        mock_additional.assert_called_once()

    @patch.object(ZillowExtractor, "_check_for_blocking", return_value=True)
    @patch.object(ZillowExtractor, "_extract_location_from_url", return_value="Portland, ME")
    @patch.object(ZillowExtractor, "_extract_listing_name_from_url", return_value="123 Main St Portland ME")
    def test_extract_when_blocked(self, mock_name, mock_location, mock_blocking, extractor):
        """Test extraction when page is blocked."""
        # Create sample soup
        soup = BeautifulSoup(
            "<html><body>Blocked</body></html>", 'html.parser')

        # Test
        result = extractor.extract(soup)

        # Verify results include minimal data from URL
        assert result["listing_name"] == "123 Main St Portland ME"
        assert result["location"] == "Portland, ME"
        assert "extraction_blocked" in result
        assert result["extraction_blocked"] is True

        # Verify mocks were called
        mock_blocking.assert_called_once()
        mock_location.assert_called_once()
        mock_name.assert_called_once()

    def test_extract_with_error(self, extractor):
        """Test handling errors during extraction."""
        # Create sample soup
        soup = BeautifulSoup("<html><body>Test</body></html>", 'html.parser')

        # Mock _check_for_blocking to raise exception
        with patch.object(extractor, '_check_for_blocking', side_effect=Exception("Test error")):
            # Test - should not raise exception
            result = extractor.extract(soup)

            # Error should be recorded and extraction marked as failed
            assert extractor.raw_data["extraction_status"] == "failed"
            assert "extraction_error" in extractor.raw_data
