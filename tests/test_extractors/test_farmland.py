# tests/test_extractors/test_farmland.py
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from new_england_listings.extractors.farmland import FarmlandExtractor, FARMLAND_SELECTORS


class TestFarmlandExtractorInit:
    def test_init_maine_farmland_trust(self):
        """Test initialization with Maine Farmland Trust URL."""
        url = "https://mainefarmlandtrust.org/farm-123"
        extractor = FarmlandExtractor(url)

        assert extractor.is_mft is True
        assert extractor.is_neff is False
        assert extractor.platform_name == "Maine Farmland Trust"
        assert extractor.data["property_type"] == "Farm"

    def test_init_new_england_farmland_finder(self):
        """Test initialization with New England Farmland Finder URL."""
        url = "https://newenglandfarmlandfinder.org/farm-456"
        extractor = FarmlandExtractor(url)

        assert extractor.is_mft is False
        assert extractor.is_neff is True
        assert extractor.platform_name == "New England Farmland Finder"
        assert extractor.data["property_type"] == "Farm"


class TestUrlDataExtraction:
    def test_extract_from_url_basic(self):
        """Test extracting basic information from URL."""
        url = "https://mainefarmlandtrust.org/property/beautiful-10-acres-in-brunswick-me"
        extractor = FarmlandExtractor(url)
        url_data = extractor._extract_from_url()

        assert url_data["location"] == "Brunswick, ME"
        assert "acreage" in url_data
        assert url_data["acreage"] == "10 acres"
        assert "listing_name" in url_data
        assert "Brunswick" in url_data["listing_name"]

    def test_extract_from_url_with_county(self):
        """Test extracting county information from URL."""
        url = "https://newenglandfarmlandfinder.org/5-acres-farmland-in-cumberland-county-me"
        extractor = FarmlandExtractor(url)
        url_data = extractor._extract_from_url()

        assert "Cumberland County" in url_data["location"]
        assert "ME" in url_data["location"]
        assert url_data["acreage"] == "5 acres"

    def test_extract_from_url_with_property_type(self):
        """Test extracting property type from URL."""
        url = "https://mainefarmlandtrust.org/farmland-for-sale-50-acres-in-waldo-me"
        extractor = FarmlandExtractor(url)
        url_data = extractor._extract_from_url()

        assert url_data["property_type"] == "Farm"
        assert url_data["acreage"] == "50 acres"
        assert "Waldo, ME" in url_data["location"]


class TestContentVerification:
    @pytest.fixture
    def mft_extractor(self):
        return FarmlandExtractor("https://mainefarmlandtrust.org/example")

    @pytest.fixture
    def neff_extractor(self):
        return FarmlandExtractor("https://newenglandfarmlandfinder.org/example")

    def test_verify_page_content_mft(self, mft_extractor):
        """Test verification of Maine Farmland Trust page content."""
        html = """
        <html>
            <div class="field-group--columns">
                <h1 class="page-title">Beautiful Farm</h1>
                <div class="content">Farm details here</div>
            </div>
        </html>
        """
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')
        assert mft_extractor._verify_page_content() is True

    def test_verify_page_content_neff(self, neff_extractor):
        """Test verification of New England Farmland Finder page content."""
        html = """
        <html>
            <h1 class="farmland__title">Vermont Farm Property</h1>
            <article>Farm details here</article>
        </html>
        """
        neff_extractor.soup = BeautifulSoup(html, 'html.parser')
        assert neff_extractor._verify_page_content() is True

    def test_verify_page_content_insufficient(self, mft_extractor):
        """Test verification with insufficient content."""
        html = "<html><body>Too little content</body></html>"
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')
        assert mft_extractor._verify_page_content() is False


class TestFindWithSelector:
    @pytest.fixture
    def extractor(self):
        return FarmlandExtractor("https://mainefarmlandtrust.org/example")

    def test_find_with_selector_single_class(self, extractor):
        """Test finding element with single class."""
        html = """
        <html>
            <div class="property-title">Farm Title</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        element = extractor._find_with_selector("title", "main")
        assert element is not None
        assert element.text == "Farm Title"

    def test_find_with_selector_multiple_classes(self, extractor):
        """Test finding element with multiple possible classes."""
        html = """
        <html>
            <div class="farmland__title">Farm Title</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        element = extractor._find_with_selector("title", "main")
        assert element is not None
        assert element.text == "Farm Title"

    def test_find_with_selector_not_found(self, extractor):
        """Test handling when selector doesn't match any elements."""
        html = """
        <html>
            <div class="wrong-class">No Match</div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        element = extractor._find_with_selector("title", "main")
        assert element is None


class TestFindWithText:
    @pytest.fixture
    def extractor(self):
        return FarmlandExtractor("https://mainefarmlandtrust.org/example")

    def test_find_with_text_single_pattern(self, extractor):
        """Test finding element with text matching a single pattern."""
        html = """
        <html>
            <div>
                <p>Total number of acres: 10</p>
                <p>Other information</p>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        container = extractor.soup.find("div")

        element = extractor._find_with_text(container, "Total number of acres")
        assert element is not None
        assert "10" in element.parent.text

    def test_find_with_text_multiple_patterns(self, extractor):
        """Test finding element with text matching one of multiple patterns."""
        html = """
        <html>
            <div>
                <p>Acreage: 15</p>
                <p>Other information</p>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        container = extractor.soup.find("div")

        patterns = ["Total number of acres", "Acreage", "Property size"]
        element = extractor._find_with_text(container, patterns)
        assert element is not None
        assert "15" in element.parent.text

    def test_find_with_text_not_found(self, extractor):
        """Test handling when text pattern doesn't match."""
        html = """
        <html>
            <div>
                <p>No matching text</p>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        container = extractor.soup.find("div")

        element = extractor._find_with_text(container, "Total number of acres")
        assert element is None

    def test_find_with_text_container_none(self, extractor):
        """Test handling when container is None."""
        element = extractor._find_with_text(None, "Any pattern")
        assert element is None


class TestListingNameExtraction:
    @pytest.fixture
    def mft_extractor(self):
        return FarmlandExtractor("https://mainefarmlandtrust.org/example")

    @pytest.fixture
    def neff_extractor(self):
        return FarmlandExtractor("https://newenglandfarmlandfinder.org/example")

    def test_extract_listing_name_mft_page_title(self, mft_extractor):
        """Test extracting listing name from Maine Farmland Trust page title."""
        html = """
        <html>
            <h1 class="page-title">Beautiful Farm in Knox County</h1>
        </html>
        """
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')
        assert mft_extractor.extract_listing_name() == "Beautiful Farm in Knox County"

    def test_extract_listing_name_neff_farmland_title(self, neff_extractor):
        """Test extracting listing name from New England Farmland Finder title."""
        html = """
        <html>
            <h1 class="farmland__title">Organic Farm • Cumberland County, ME</h1>
        </html>
        """
        neff_extractor.soup = BeautifulSoup(html, 'html.parser')
        assert neff_extractor.extract_listing_name() == "Organic Farm"

    def test_extract_listing_name_neff_additional_info(self, neff_extractor):
        """Test extracting farm name from Additional Information section."""
        html = """
        <html>
            <div>Additional Information</div>
            <div>The Green Valley Farm is located in a beautiful area.</div>
        </html>
        """
        neff_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Set up the soup to find Additional Information
        with patch.object(neff_extractor.soup, 'find', return_value=neff_extractor.soup.find('div')):
            assert neff_extractor.extract_listing_name() == "Green Valley Farm"

    def test_extract_listing_name_fallback_url(self, mft_extractor):
        """Test falling back to URL data when name can't be extracted from page."""
        html = """<html><body>No title here</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Add URL data
        mft_extractor.url_data = {"listing_name": "URL Farm Name"}

        assert mft_extractor.extract_listing_name() == "URL Farm Name"

    def test_extract_listing_name_h1_fallback(self, mft_extractor):
        """Test falling back to any h1 when other methods fail."""
        html = """
        <html>
            <h1>Generic Farm Title</h1>
        </html>
        """
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        assert mft_extractor.extract_listing_name() == "Generic Farm Title"

    def test_extract_listing_name_default(self, mft_extractor):
        """Test using default name when all methods fail."""
        html = """<html><body>No title or h1</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # No URL data
        mft_extractor.url_data = {}

        assert mft_extractor.extract_listing_name() == "Untitled Farm Property"


class TestLocationExtraction:
    @pytest.fixture
    def mft_extractor(self):
        return FarmlandExtractor("https://mainefarmlandtrust.org/example")

    @pytest.fixture
    def neff_extractor(self):
        return FarmlandExtractor("https://newenglandfarmlandfinder.org/example")

    def test_extract_location_neff_direct_field(self, neff_extractor):
        """Test extracting location from NEFF direct location field."""
        html = """
        <html>
            <div>Location</div>
            <div>Knox County, ME</div>
        </html>
        """
        neff_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Set up the soup to find Location
        with patch.object(neff_extractor.soup, 'find', return_value=neff_extractor.soup.find('div')):
            assert neff_extractor.extract_location() == "Knox County, ME"

    def test_extract_location_neff_title(self, neff_extractor):
        """Test extracting location from NEFF title when direct field not found."""
        html = """
        <html>
            <h1>Beautiful Farm • Knox County, ME</h1>
        </html>
        """
        neff_extractor.soup = BeautifulSoup(html, 'html.parser')
        assert neff_extractor.extract_location() == "Knox County, ME"

    def test_extract_location_mft_property_location(self, mft_extractor):
        """Test extracting location from MFT property location."""
        html = """
        <html>
            <div class="property-location">Belfast, ME</div>
        </html>
        """
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')
        assert mft_extractor.extract_location() == "Belfast, ME"

    def test_extract_location_mft_county(self, mft_extractor):
        """Test extracting location from MFT county name."""
        html = """
        <html>
            <div class="county-name">Waldo County</div>
        </html>
        """
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')
        assert mft_extractor.extract_location() == "Waldo County, ME"

    def test_extract_location_url_fallback(self, mft_extractor):
        """Test falling back to URL data when location not found in page."""
        html = """<html><body>No location here</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Add URL data
        mft_extractor.url_data = {"location": "Cumberland County, ME"}

        assert mft_extractor.extract_location() == "Cumberland County, ME"

    def test_extract_location_from_url(self, mft_extractor):
        """Test extracting location from URL as last resort."""
        html = """<html><body>No location here</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # No URL data
        mft_extractor.url_data = {}

        # Mock parse_location_from_url
        with patch.object(mft_extractor.location_service, 'parse_location_from_url', return_value="Hancock County, ME"):
            assert mft_extractor.extract_location() == "Hancock County, ME"

    def test_extract_location_unknown(self, mft_extractor):
        """Test handling when location cannot be found."""
        html = """<html><body>No location here</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # No URL data
        mft_extractor.url_data = {}

        # Mock parse_location_from_url to return None
        with patch.object(mft_extractor.location_service, 'parse_location_from_url', return_value=None):
            assert mft_extractor.extract_location() == "Location Unknown"


class TestPriceExtraction:
    @pytest.fixture
    def mft_extractor(self):
        return FarmlandExtractor("https://mainefarmlandtrust.org/example")

    @pytest.fixture
    def neff_extractor(self):
        return FarmlandExtractor("https://newenglandfarmlandfinder.org/example")

    def test_extract_price_neff_sale_price(self, neff_extractor):
        """Test extracting price from NEFF sale price field."""
        html = """
        <html>
            <div>Sale price</div>
            <div>$500,000</div>
        </html>
        """
        neff_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Set up the soup to find Sale price
        with patch.object(neff_extractor.soup, 'find', return_value=neff_extractor.soup.find('div')):
            price, bucket = neff_extractor.extract_price()
            assert price == "$500,000"
            assert bucket == "$300K - $600K"

    def test_extract_price_neff_lease(self, neff_extractor):
        """Test handling lease terms in NEFF."""
        html = """
        <html>
            <div>Available for lease</div>
        </html>
        """
        neff_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Create a find method that returns lease element
        def mock_find(string=None, **kwargs):
            if string and callable(string) and "lease" in neff_extractor.soup.text.lower():
                return neff_extractor.soup.find('div')
            return None

        with patch.object(neff_extractor.soup, 'find', side_effect=mock_find):
            price, bucket = neff_extractor.extract_price()
            assert price == "Contact for Lease Terms"
            assert bucket == "N/A"

    def test_extract_price_mft_price_container(self, mft_extractor):
        """Test extracting price from MFT price container."""
        html = """
        <html>
            <div class="price-section">
                <div class="price-amount">$750,000</div>
            </div>
        </html>
        """
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = mft_extractor.extract_price()
        assert price == "$750,000"
        assert bucket == "$600K - $900K"

    def test_extract_price_mft_text_pattern(self, mft_extractor):
        """Test extracting price from MFT text pattern."""
        html = """
        <html>
            <div class="listing-details">
                Price: $600,000 for this beautiful farm
            </div>
        </html>
        """
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = mft_extractor.extract_price()
        assert price == "$600,000"
        assert bucket == "$600K - $900K"

    def test_extract_price_mft_lease_terms(self, mft_extractor):
        """Test handling lease terms in MFT."""
        html = """
        <html>
            <div class="listing-details">
                This farm is available for lease at $5,000 per year
            </div>
        </html>
        """
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = mft_extractor.extract_price()
        assert price == "$5,000"
        assert bucket == "Under $300K"

    def test_extract_price_not_found(self, mft_extractor):
        """Test handling when price is not found."""
        html = """<html><body>No price information</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')
        price, bucket = mft_extractor.extract_price()
        assert price == "Contact for Price"
        assert bucket == "N/A"


class TestAcreageExtraction:
    @pytest.fixture
    def mft_extractor(self):
        return FarmlandExtractor("https://mainefarmlandtrust.org/example")

    @pytest.fixture
    def neff_extractor(self):
        return FarmlandExtractor("https://newenglandfarmlandfinder.org/example")

    def test_extract_acreage_neff_total_acres(self, neff_extractor):
        """Test extracting acreage from NEFF total acres field."""
        html = """
        <html>
            <div>Total number of acres</div>
            <div>75</div>
        </html>
        """
        neff_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Set up the soup to find Total number of acres
        with patch.object(neff_extractor.soup, 'find', return_value=neff_extractor.soup.find('div')):
            acreage, bucket = neff_extractor.extract_acreage_info()
            assert acreage == "75.0 acres"
            assert bucket == "Very Large (50-100 acres)"

    def test_extract_acreage_neff_sum_fields(self, neff_extractor):
        """Test summing individual acreage fields in NEFF."""
        cropland_html = """
        <div>Acres of cropland</div>
        <div>20</div>
        """
        pasture_html = """
        <div>Acres of pasture</div>
        <div>15</div>
        """
        forest_html = """
        <div>Acres of forested land</div>
        <div>10</div>
        """

        # Create a find method that returns different elements based on search text
        def mock_find(string=None, **kwargs):
            if string and callable(string):
                if "cropland" in string("Acres of cropland"):
                    return BeautifulSoup(cropland_html, 'html.parser').find('div')
                elif "pasture" in string("Acres of pasture"):
                    return BeautifulSoup(pasture_html, 'html.parser').find('div')
                elif "forested" in string("Acres of forested land"):
                    return BeautifulSoup(forest_html, 'html.parser').find('div')
            return None

        # Mock soup.find to use our custom function
        neff_extractor.soup = BeautifulSoup("<html></html>", 'html.parser')
        with patch.object(neff_extractor.soup, 'find', side_effect=mock_find):
            acreage, bucket = neff_extractor.extract_acreage_info()
            assert acreage == "45.0 acres"
            assert bucket == "Large (20-50 acres)"

    def test_extract_acreage_neff_title(self, neff_extractor):
        """Test extracting acreage from NEFF title."""
        html = """
        <html>
            <h1>Beautiful Farm with 30 acres</h1>
        </html>
        """
        neff_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock find_next methods
        def mock_find_next(tag):
            return None

        with patch.object(neff_extractor.soup.find('h1'), 'find_next', side_effect=mock_find_next):
            acreage, bucket = neff_extractor.extract_acreage_info()
            assert acreage == "30.0 acres"
            assert bucket == "Medium (5-20 acres)"

    def test_extract_acreage_mft_property_details(self, mft_extractor):
        """Test extracting acreage from MFT property details."""
        html = """
        <html>
            <div class="property-details">
                <p>10 acres of beautiful land</p>
            </div>
        </html>
        """
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')
        acreage, bucket = mft_extractor.extract_acreage_info()
        assert acreage == "10.0 acres"
        assert bucket == "Medium (5-20 acres)"

    def test_extract_acreage_url_fallback(self, mft_extractor):
        """Test falling back to URL data when acreage not found in page."""
        html = """<html><body>No acreage here</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Add URL data
        mft_extractor.url_data = {
            "acreage": "15 acres",
            "acreage_bucket": "Medium (5-20 acres)"
        }

        acreage, bucket = mft_extractor.extract_acreage_info()
        assert acreage == "15 acres"
        assert bucket == "Medium (5-20 acres)"

    def test_extract_acreage_not_found(self, mft_extractor):
        """Test handling when acreage is not found."""
        html = """<html><body>No acreage here</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # No URL data
        mft_extractor.url_data = {}

        acreage, bucket = mft_extractor.extract_acreage_info()
        assert acreage == "Not specified"
        assert bucket == "Unknown"


class TestAgriculturalDetailsExtraction:
    @pytest.fixture
    def extractor(self):
        return FarmlandExtractor("https://mainefarmlandtrust.org/example")

    def test_extract_agricultural_details_soil_quality(self, extractor):
        """Test extracting soil quality."""
        html = """
        <html>
            <div class="property-details">
                <div class="soil-quality">Prime agricultural soil</div>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')
        details = extractor.extract_agricultural_details()
        assert "soil_quality" in details
        assert details["soil_quality"] == "Prime agricultural soil"

    def test_extract_agricultural_details_water_sources(self, extractor):
        """Test extracting water sources."""
        html = """
        <html>
            <div class="property-details">
                <div>Water sources</div>
                <div>Well, spring, and pond</div>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock find_next for water sources
        def mock_find(string=None, **kwargs):
            if string and callable(string) and "Water sources" in string("Water sources"):
                return extractor.soup.find('div')
            return None

        with patch.object(extractor.soup, 'find', side_effect=mock_find):
            details = extractor.extract_agricultural_details()
            assert "water_sources" in details
            assert "Well, spring, and pond" in details["water_sources"]

    def test_extract_agricultural_details_infrastructure(self, extractor):
        """Test extracting infrastructure details."""
        html = """
        <html>
            <div class="property-details">
                <div>Farm infrastructure</div>
                <div>Barn, greenhouse, equipment shed</div>
            </div>
        </html>
        """
        extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock find_next for infrastructure
        def mock_find(string=None, **kwargs):
            if string and callable(string) and "Farm infrastructure" in string("Farm infrastructure"):
                return extractor.soup.find('div')
            return None

        with patch.object(extractor.soup, 'find', side_effect=mock_find):
            details = extractor.extract_agricultural_details()
            assert "infrastructure" in details
            assert "Barn, greenhouse" in details["infrastructure"]

    def test_extract_agricultural_details_empty(self, extractor):
        """Test handling when no agricultural details are found."""
        html = """<html><body>No agricultural details</body></html>"""
        extractor.soup = BeautifulSoup(html, 'html.parser')
        details = extractor.extract_agricultural_details()
        assert isinstance(details, dict)
        assert len(details) == 0


class TestAdditionalDataExtraction:
    @pytest.fixture
    def mft_extractor(self):
        return FarmlandExtractor("https://mainefarmlandtrust.org/example")

    @pytest.fixture
    def neff_extractor(self):
        return FarmlandExtractor("https://newenglandfarmlandfinder.org/example")

    @patch.object(FarmlandExtractor, "extract_agricultural_details")
    def test_extract_additional_data_mft(self, mock_ag_details, mft_extractor):
        """Test extracting additional data for MFT listing."""
        # Setup mock
        mock_ag_details.return_value = {
            "soil_quality": "Prime agricultural soil",
            "water_sources": "Well and spring",
            "infrastructure": "Barn and greenhouse"
        }

        # Basic HTML
        html = """
        <html>
            <div class="property-description">Beautiful farmland with views</div>
        </html>
        """
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Extract additional data
        mft_extractor.extract_additional_data()

        # Check farm details
        assert "farm_details" in mft_extractor.data
        assert "Soil: Prime agricultural soil" in mft_extractor.data["farm_details"]
        assert "Water: Well and spring" in mft_extractor.data["farm_details"]
        assert "Infrastructure: Barn and greenhouse" in mft_extractor.data["farm_details"]

    @patch.object(FarmlandExtractor, "extract_house_details")
    def test_extract_additional_data_house_details(self, mock_house_details, mft_extractor):
        """Test extracting house details."""
        # Setup mock
        mock_house_details.return_value = "3 bedroom | 2 bathroom | Basement"

        # Basic HTML
        html = """<html><body>Basic content</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Extract additional data
        mft_extractor.extract_additional_data()

        # Check house details
        assert "house_details" in mft_extractor.data
        assert mft_extractor.data["house_details"] == "3 bedroom | 2 bathroom | Basement"

    @patch.object(FarmlandExtractor, "extract_amenities")
    def test_extract_additional_data_amenities(self, mock_amenities, mft_extractor):
        """Test extracting amenities."""
        # Setup mock
        mock_amenities.return_value = [
            "Well water", "Fenced areas", "Solar power"]

        # Basic HTML
        html = """<html><body>Basic content</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Extract additional data
        mft_extractor.extract_additional_data()

        # Check amenities
        assert "other_amenities" in mft_extractor.data
        assert mft_extractor.data["other_amenities"] == "Well water | Fenced areas | Solar power"

    @patch("new_england_listings.utils.location_service.LocationService.get_comprehensive_location_info")
    def test_extract_additional_data_location_enrichment(self, mock_location_info, mft_extractor):
        """Test location data enrichment."""
        # Setup mock
        mock_location_info.return_value = {
            "distance_to_portland": 35.5,
            "portland_distance_bucket": "21-40",
            "nearest_city": "Augusta, ME",
            "nearest_city_distance": 15.2,
            "nearest_city_distance_bucket": "11-20",
            "town_population": 19000,
            "town_pop_bucket": "Medium (15K-50K)",
            "school_district": "Augusta Schools",
            "school_rating": 7.5,
            "school_rating_cat": "Above Average (8-9)",
            "hospital_distance": 12.3,
            "hospital_distance_bucket": "11-20",
            "closest_hospital": "Augusta General Hospital"
        }

        # Set valid location
        mft_extractor.data["location"] = "Augusta, ME"

        # Basic HTML
        html = """<html><body>Basic content</body></html>"""
        mft_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Extract additional data
        mft_extractor.extract_additional_data()

        # Check location data
        assert mft_extractor.data["distance_to_portland"] == 35.5
        assert mft_extractor.data["portland_distance_bucket"] == "21-40"
        assert mft_extractor.data["nearest_city"] == "Augusta, ME"
        assert mft_extractor.data["school_district"] == "Augusta Schools"
        assert mft_extractor.data["school_rating"] == 7.5
        assert mft_extractor.data["hospital_distance"] == 12.3
        assert mft_extractor.data["closest_hospital"] == "Augusta General Hospital"

    def test_extract_additional_data_neff_specific(self, neff_extractor):
        """Test NEFF-specific data extraction."""
        html = """
        <html>
            <div>Date posted</div>
            <div>January 15, 2023</div>
            <div>Property owner</div>
            <div>Private individual</div>
        </html>
        """
        neff_extractor.soup = BeautifulSoup(html, 'html.parser')

        # Mock basic methods
        with patch.multiple(
            neff_extractor,
            _extract_basic_details=MagicMock(),
            _extract_acreage_details=MagicMock(),
            _extract_farm_details=MagicMock(),
            _extract_property_features=MagicMock(),
            _extract_dates=MagicMock()
        ):
            neff_extractor.extract_additional_data()

            # Verify that NEFF-specific methods were called
            neff_extractor._extract_basic_details.assert_called_once()
            neff_extractor._extract_acreage_details.assert_called_once()
            neff_extractor._extract_farm_details.assert_called_once()
            neff_extractor._extract_property_features.assert_called_once()
            neff_extractor._extract_dates.assert_called_once()


class TestMainExtraction:
    @pytest.fixture
    def mft_extractor(self):
        return FarmlandExtractor("https://mainefarmlandtrust.org/example")

    @patch.object(FarmlandExtractor, "_verify_page_content", return_value=True)
    @patch.object(FarmlandExtractor, "extract_listing_name", return_value="Beautiful Farm")
    @patch.object(FarmlandExtractor, "extract_location", return_value="Knox County, ME")
    @patch.object(FarmlandExtractor, "extract_price", return_value=("$650,000", "$600K - $900K"))
    @patch.object(FarmlandExtractor, "extract_acreage_info", return_value=("75.0 acres", "Very Large (50-100 acres)"))
    @patch.object(FarmlandExtractor, "extract_additional_data")
    def test_extract_successful(self, mock_additional, mock_acreage, mock_price,
                                mock_location, mock_name, mock_verify, mft_extractor):
        """Test successful extraction."""
        # Create sample soup
        soup = BeautifulSoup("<html><body>Test</body></html>", 'html.parser')

        # Test
        result = mft_extractor.extract(soup)

        # Verify results
        assert result["listing_name"] == "Beautiful Farm"
        assert result["location"] == "Knox County, ME"
        assert result["price"] == "$650,000"
        assert result["price_bucket"] == "$600K - $900K"
        assert result["acreage"] == "75.0 acres"
        assert result["acreage_bucket"] == "Very Large (50-100 acres)"

        # Verify extraction status
        assert mft_extractor.raw_data["extraction_status"] == "success"

        # Verify mocks were called
        mock_verify.assert_called_once()
        mock_name.assert_called_once()
        mock_location.assert_called_once()
        mock_price.assert_called_once()
        mock_acreage.assert_called_once()
        mock_additional.assert_called_once()

    @patch.object(FarmlandExtractor, "_verify_page_content", return_value=False)
    def test_extract_verification_failed(self, mock_verify, mft_extractor):
        """Test handling failed page verification."""
        # Create sample soup
        soup = BeautifulSoup(
            "<html><body>Failed verification</body></html>", 'html.parser')

        # Mock URL data
        mft_extractor.url_data = {
            "listing_name": "URL Farm Name",
            "location": "URL Location, ME",
            "acreage": "20 acres",
            "acreage_bucket": "Medium (5-20 acres)"
        }

        # Mock extract methods to ensure they're still called
        with patch.multiple(
            mft_extractor,
            extract_listing_name=MagicMock(return_value="URL Farm Name"),
            extract_location=MagicMock(return_value="URL Location, ME"),
            extract_price=MagicMock(return_value=("Contact for Price", "N/A")),
            extract_acreage_info=MagicMock(
                return_value=("20 acres", "Medium (5-20 acres)")),
            extract_additional_data=MagicMock()
        ):
            # Test
            result = mft_extractor.extract(soup)

            # Verify results still include basic data
            assert result["listing_name"] == "URL Farm Name"
            assert result["location"] == "URL Location, ME"

            # Verify extraction status
            assert mft_extractor.raw_data["extraction_status"] == "failed"

    def test_extract_with_error(self, mft_extractor):
        """Test handling errors during extraction."""
        # Create sample soup
        soup = BeautifulSoup("<html><body>Test</body></html>", 'html.parser')

        # Mock _verify_page_content to raise exception
        with patch.object(mft_extractor, '_verify_page_content', side_effect=Exception("Test error")):
            # Test - should not raise exception
            result = mft_extractor.extract(soup)

            # Error should be recorded and extraction marked as failed
            assert mft_extractor.raw_data["extraction_status"] == "failed"
            assert "extraction_error" in mft_extractor.raw_data
