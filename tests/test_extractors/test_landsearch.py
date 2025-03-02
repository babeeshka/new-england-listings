# tests/test_extractors/test_landsearch.py
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from new_england_listings.extractors.landsearch import LandSearchExtractor, LANDSEARCH_SELECTORS


class TestLandSearchExtractorInit:
    def test_init(self):
        """Test initialization of LandSearchExtractor."""
        url = "https://landsearch.com/properties/12345"
        extractor = LandSearchExtractor(url)

        assert extractor.platform_name == "LandSearch"
        assert extractor.url == url
        assert extractor.data["platform"] == "LandSearch"


class TestContentVerification:
    @pytest.fixture
    def extractor(self):
        return LandSearchExtractor("https://landsearch.com/properties/12345")

    def test_verify_page_content_valid(self, extractor):
        """Test verification of valid page content."""
        html = """
        <html>
            <body>
                <div class="property-price">$500,000</div>
                <div class="property-details">Details about the property</div>
                <div class="property-location">Portland, ME</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor._verify_page_content() is True

    def test_verify_page_content_insufficient(self, extractor):
        """Test verification with insufficient content."""
        html = """
        <html>
            <body>
                <div>Minimal content</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor._verify_page_content() is False

    def test_verify_debug_output(self, extractor):
        """Test that debug output is generated for content."""
        html = """
        <html>
            <body>
                <div class="property-price">$500,000</div>
                <h1 class="page-title">Property Title</h1>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Use a logger mock to verify logging output
        with patch('new_england_listings.extractors.landsearch.logger') as mock_logger:
            extractor._verify_page_content()

            # Verify debug logs are generated
            assert mock_logger.debug.call_count > 0

            # Verify found elements are logged
            found_elements_call = False
            for call in mock_logger.debug.call_args_list:
                if "Found elements" in str(call) or "Found div classes" in str(call):
                    found_elements_call = True
                    break

            assert found_elements_call is True


class TestListingNameExtraction:
    @pytest.fixture
    def extractor(self):
        return LandSearchExtractor("https://landsearch.com/properties/12345")

    def test_extract_listing_name_title_container(self, extractor):
        """Test extracting listing name from title container."""
        html = """
        <html>
            <div class="property-title">
                <h1>Beautiful Land for Sale in Maine</h1>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor.extract_listing_name() == "Beautiful Land for Sale in Maine"

    def test_extract_listing_name_heading(self, extractor):
        """Test extracting listing name from heading when container not found."""
        html = """
        <html>
            <h1>Beautiful Land for Sale in Maine</h1>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor.extract_listing_name() == "Beautiful Land for Sale in Maine"

    def test_extract_listing_name_page_title(self, extractor):
        """Test extracting listing name from page title."""
        html = """
        <html>
            <head>
                <title>Beautiful Land for Sale in Maine - LandSearch</title>
            </head>
            <body>Content</body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor.extract_listing_name() == "Beautiful Land for Sale in Maine"

    def test_extract_listing_name_url_fallback(self, extractor):
        """Test extracting listing name from URL as fallback."""
        html = """
        <html>
            <body>No title elements</body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Set URL to something that can be parsed
        extractor.url = "https://landsearch.com/properties/beautiful-land-maine-12345"

        assert "Land Maine" in extractor.extract_listing_name()


class TestPriceExtraction:
    @pytest.fixture
    def extractor(self):
        return LandSearchExtractor("https://landsearch.com/properties/12345")

    def test_extract_price_container(self, extractor):
        """Test extracting price from price container."""
        html = """
        <html>
            <div class="property-price">
                <div class="price-amount">$450,000</div>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = extractor.extract_price()
        assert price == "$450,000"
        assert bucket == "$300K - $600K"

    def test_extract_price_amount(self, extractor):
        """Test extracting price from amount element directly."""
        html = """
        <html>
            <div class="price-amount">$450,000</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = extractor.extract_price()
        assert price == "$450,000"
        assert bucket == "$300K - $600K"

    def test_extract_price_text_patterns(self, extractor):
        """Test extracting price from text patterns."""
        html = """
        <html>
            <div>This property is listed for $750,000</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = extractor.extract_price()
        assert price == "$750,000"
        assert bucket == "$600K - $900K"

    def test_extract_price_not_found(self, extractor):
        """Test handling when price is not found."""
        html = """
        <html>
            <body>No price information</body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = extractor.extract_price()
        assert price == "Contact for Price"
        assert bucket == "N/A"


class TestLocationExtraction:
    @pytest.fixture
    def extractor(self):
        return LandSearchExtractor("https://landsearch.com/properties/12345")

    def test_extract_location_full_address(self, extractor):
        """Test extracting location from full address element."""
        html = """
        <html>
            <div class="property-location">
                <div class="full-address">123 Main St, Portland, ME 04101</div>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor.extract_location() == "123 Main St, Portland, ME 04101"

    def test_extract_location_city_state(self, extractor):
        """Test extracting location from city and state elements."""
        html = """
        <html>
            <div class="property-location">
                <div class="city">Portland</div>
                <div class="state">ME</div>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        assert extractor.extract_location() == "Portland, ME"

    def test_extract_location_from_url(self, extractor):
        """Test extracting location from URL."""
        html = """
        <html>
            <body>No location info</body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Set URL to something that contains location information
        extractor.url = "https://landsearch.com/properties/portland-me-12345"

        assert "Portland, ME" in extractor.extract_location()

    def test_extract_location_not_found(self, extractor):
        """Test handling when location cannot be found."""
        html = """
        <html>
            <body>No location info</body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Set URL without location info
        extractor.url = "https://landsearch.com/properties/12345"

        assert extractor.extract_location() == "Location Unknown"


class TestAcreageExtraction:
    @pytest.fixture
    def extractor(self):
        return LandSearchExtractor("https://landsearch.com/properties/12345")

    def test_extract_acreage_from_title(self, extractor):
        """Test extracting acreage from page title."""
        html = """
        <html>
            <head>
                <title>40 Acres in Maine - LandSearch</title>
            </head>
            <body>Content</body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "40.0 acres"
        assert bucket == "Large (20-50 acres)"

    def test_extract_acreage_from_details(self, extractor):
        """Test extracting acreage from property details section."""
        html = """
        <html>
            <div class="property-details">
                <div class="property-acreage">20 acres</div>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "20.0 acres"
        assert bucket == "Medium (5-20 acres)"

    def test_extract_acreage_from_detail_sections(self, extractor):
        """Test extracting acreage from detail sections."""
        html = """
        <html>
            <div class="property-details">
                <div class="detail-section">Property size: 15 acres</div>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "15.0 acres"
        assert bucket == "Medium (5-20 acres)"

    def test_extract_acreage_from_full_text(self, extractor):
        """Test extracting acreage from full page text."""
        html = """
        <html>
            <body>
                <div>This beautiful property includes 30 acres of diverse terrain.</div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "30.0 acres"
        assert bucket == "Medium (5-20 acres)"

    def test_extract_acreage_not_found(self, extractor):
        """Test handling when acreage is not found."""
        html = """
        <html>
            <body>No acreage information</body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        acreage, bucket = extractor.extract_acreage_info()
        assert acreage == "Not specified"
        assert bucket == "Unknown"


class TestAdditionalDataExtraction:
    @pytest.fixture
    def extractor(self):
        return LandSearchExtractor("https://landsearch.com/properties/12345")

    @patch("new_england_listings.extractors.landsearch.LocationService.get_comprehensive_location_info")
    def test_extract_additional_data_with_attributes(self, mock_location_info, extractor):
        """Test extracting additional data with attributes section."""
        # Create HTML with attributes section
        html = """
        <html>
            <section class="accordion__section" data-type="attributes">
                <section class="property-info__column">
                    <h3>Listing</h3>
                    <div class="definitions__group">
                        <dt>Type</dt>
                        <dd>Residential</dd>
                    </div>
                    <div class="definitions__group">
                        <dt>Subtype</dt>
                        <dd>Single Family Residence</dd>
                    </div>
                </section>
                <section class="property-info__column">
                    <h3>Structure</h3>
                    <div class="definitions__group">
                        <dt>Bedrooms</dt>
                        <dd>3</dd>
                    </div>
                    <div class="definitions__group">
                        <dt>Bathrooms</dt>
                        <dd>2</dd>
                    </div>
                </section>
            </section>
            <div class="property-description">Beautiful property with mountain views.</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock location info
        mock_location_info.return_value = {
            "distance_to_portland": 25.5,
            "portland_distance_bucket": "21-40",
            "town_population": 15000,
            "town_pop_bucket": "Medium (15K-50K)",
            "school_district": "Local Schools",
            "school_rating": 7.5,
            "school_rating_cat": "Above Average (8-9)",
            "hospital_distance": 10.2,
            "hospital_distance_bucket": "0-10",
            "closest_hospital": "Regional Hospital",
            "restaurants_nearby": 5,
            "grocery_stores_nearby": 2
        }

        # Set valid location
        extractor.data["location"] = "Brunswick, ME"

        # Mock extract_house_details and _extract_description
        with patch.multiple(
            extractor,
            _extract_house_details=MagicMock(
                return_value="3 bedrooms | 2 bathrooms"),
            _extract_description=MagicMock(
                return_value="Beautiful property with mountain views.")
        ):
            # Extract additional data
            extractor.extract_additional_data()

            # Check that house details were extracted
            assert extractor.data["house_details"] == "3 bedrooms | 2 bathrooms"

            # Check that description was extracted as notes
            assert extractor.data["notes"] == "Beautiful property with mountain views."

            # Check property type (should be Single Family based on attributes)
            assert extractor.data["property_type"] == "Single Family"

            # Check location data enrichment
            assert extractor.data["distance_to_portland"] == 25.5
            assert extractor.data["portland_distance_bucket"] == "21-40"
            assert extractor.data["town_population"] == 15000
            assert extractor.data["town_pop_bucket"] == "Medium (15K-50K)"
            assert extractor.data["school_district"] == "Local Schools"
            assert extractor.data["school_rating"] == 7.5
            assert extractor.data["restaurants_nearby"] == 5
            assert extractor.data["grocery_stores_nearby"] == 2

    def test_extract_additional_data_error_handling(self, extractor):
        """Test error handling during additional data extraction."""
        html = """
        <html>
            <body>Basic content</body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock super().extract_additional_data to raise exception
        with patch('new_england_listings.extractors.base.BaseExtractor.extract_additional_data', side_effect=Exception("Test error")):
            # Should not raise exception
            extractor.extract_additional_data()

            # Error should be logged, but default values should be set
            assert extractor.data.get("restaurants_nearby") == 1
            assert extractor.data.get("grocery_stores_nearby") == 1

    def test_extract_additional_data_fallback_values(self, extractor):
        """Test that fallback values are set when location processing fails."""
        html = """
        <html>
            <body>Basic content</body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Set location to Unknown
        extractor.data["location"] = "Location Unknown"

        # Extract additional data
        extractor.extract_additional_data()

        # Check that fallback values are set
        assert extractor.data.get("restaurants_nearby") == 1
        assert extractor.data.get("grocery_stores_nearby") == 1
        assert extractor.data.get(
            "school_district") == "Nearby School District"
        assert extractor.data.get("school_rating") == 6.0
        assert extractor.data.get("hospital_distance") == 20.0
        assert extractor.data.get("closest_hospital") == "Nearby Hospital"


class TestHouseAndFarmDetailsExtraction:
    @pytest.fixture
    def extractor(self):
        return LandSearchExtractor("https://landsearch.com/properties/12345")

    def test_extract_house_details(self, extractor):
        """Test extracting house details."""
        html = """
        <html>
            <body>
                <div class="raw_data">
                    <div class="details">
                        <p>Room Count: 7</p>
                        <p>Rooms: Bedroom x 3, Bathroom x 2, Kitchen, Living Room</p>
                        <p>Structure - Materials: Frame</p>
                        <p>Structure - Roof: Metal</p>
                    </div>
                </div>
            </body>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Add raw_data details that would be extracted by the accessor
        extractor.raw_data = {
            "details": {
                "Room Count": "7",
                "Rooms": "Bedroom x 3, Bathroom x 2, Kitchen, Living Room",
                "Structure - Materials": "Frame",
                "Structure - Roof": "Metal"
            }
        }

        result = extractor._extract_house_details()
        assert "Room Count: 7" in result
        assert "Rooms: Bedroom x 3" in result
        assert "Materials: Frame" in result
        assert "Roof: Metal" in result

    def test_extract_farm_details(self, extractor):
        """Test extracting farm details."""
        html = """
        <html>
            <div class="property-description">
                <p>This farm includes 20 acres of tillable land, a large barn, and irrigation systems.</p>
                <p>Fencing is in good condition around pastures.</p>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Set property type to Farm to ensure farm details are extracted
        extractor.data["property_type"] = "Farm"

        result = extractor._extract_farm_details()
        assert result is not None
        assert "tillable land" in result.lower()
        assert "barn" in result.lower()
        assert "irrigation" in result.lower()

    def test_extract_farm_details_non_farm_property(self, extractor):
        """Test that farm details are not extracted for non-farm properties."""
        html = """
        <html>
            <div class="property-description">
                <p>This property includes 5 acres of land with wooded areas.</p>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Set property type to Single Family
        extractor.data["property_type"] = "Single Family"

        result = extractor._extract_farm_details()
        assert result is None


class TestMainExtraction:
    @pytest.fixture
    def extractor(self):
        return LandSearchExtractor("https://landsearch.com/properties/12345")

    @patch.object(LandSearchExtractor, "_verify_page_content", return_value=True)
    @patch.object(LandSearchExtractor, "extract_listing_name", return_value="Beautiful Land in Maine")
    @patch.object(LandSearchExtractor, "extract_location", return_value="Knox County, ME")
    @patch.object(LandSearchExtractor, "extract_price", return_value=("$350,000", "$300K - $600K"))
    @patch.object(LandSearchExtractor, "extract_acreage_info", return_value=("25.0 acres", "Large (20-50 acres)"))
    @patch.object(LandSearchExtractor, "extract_additional_data")
    def test_extract_successful(self, mock_additional, mock_acreage, mock_price,
                                mock_location, mock_name, mock_verify, extractor):
        """Test successful extraction."""
        # Create sample soup
        soup = BeautifulSoup("<html><body>Test</body></html>", 'html.parser')

        # Test
        result = extractor.extract(soup)

        # Verify results
        assert result["listing_name"] == "Beautiful Land in Maine"
        assert result["location"] == "Knox County, ME"
        assert result["price"] == "$350,000"
        assert result["price_bucket"] == "$300K - $600K"
        assert result["acreage"] == "25.0 acres"
        assert result["acreage_bucket"] == "Large (20-50 acres)"

        # Verify extraction status
        assert extractor.raw_data["extraction_status"] == "success"

        # Verify mocks were called
        mock_verify.assert_called_once()
        mock_name.assert_called_once()
        mock_location.assert_called_once()
        mock_price.assert_called_once()
        mock_acreage.assert_called_once()
        mock_additional.assert_called_once()

    @patch.object(LandSearchExtractor, "_verify_page_content", return_value=False)
    def test_extract_verification_failed(self, mock_verify, extractor):
        """Test handling failed page verification."""
        # Create sample soup
        soup = BeautifulSoup(
            "<html><body>Failed verification</body></html>", 'html.parser')

        # Test
        result = extractor.extract(soup)

        # Even with verification failure, basic data should be present
        assert "listing_name" in result
        assert "location" in result
        assert "price" in result
        assert "acreage" in result

        # Verify extraction status
        assert extractor.raw_data["extraction_status"] == "failed"

    def test_extract_with_error(self, extractor):
        """Test handling errors during extraction."""
        # Create sample soup
        soup = BeautifulSoup("<html><body>Test</body></html>", 'html.parser')

        # Mock extract_listing_name to raise exception
        with patch.object(extractor, 'extract_listing_name', side_effect=Exception("Test error")):
            # Test - should not raise exception
            result = extractor.extract(soup)

            # Error should be recorded and extraction marked as failed
            assert extractor.raw_data["extraction_status"] == "failed"
            assert "extraction_error" in extractor.raw_data
            
