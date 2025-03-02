# tests/test_utils/test_text_processor.py
import pytest
from bs4 import BeautifulSoup
from new_england_listings.utils.text import (
    TextProcessor,
    # Backward compatibility functions
    clean_html_text,
    extract_property_type,
    clean_price,
    extract_acreage
)


class TestTextProcessor:
    """Tests for the TextProcessor class which handles text processing and extraction."""

    class TestCleanHtmlText:
        """Tests for the clean_html_text method."""

        @pytest.mark.parametrize("input_text, expected", [
            ("  Hello  World  ", "Hello World"),
            ("Hello&nbsp;World", "Hello World"),
            ("This &amp; That", "This & That"),
            ("Hello\nWorld\tTest", "Hello World Test"),
            ("", ""),
            (None, "")
        ])
        def test_clean_html_text(self, input_text, expected):
            """Test HTML text cleaning with various inputs."""
            assert TextProcessor.clean_html_text(input_text) == expected

    class TestExtractTextAfterLabel:
        """Tests for the extract_text_after_label method."""

        def test_extract_text_basic(self):
            """Test basic text extraction after a label."""
            text = "Price: $500,000. Location: Portland, ME."
            assert TextProcessor.extract_text_after_label(
                text, "Price") == "$500,000"
            assert TextProcessor.extract_text_after_label(
                text, "Location") == "Portland, ME"

        def test_extract_text_max_words(self):
            """Test limiting extracted text to max_words."""
            text = "Description: This is a beautiful property with mountain views."
            assert TextProcessor.extract_text_after_label(
                text, "Description", max_words=3) == "This is a"
            assert TextProcessor.extract_text_after_label(
                text, "Description", max_words=5) == "This is a beautiful property"

        def test_extract_text_not_found(self):
            """Test when label is not found."""
            text = "Price: $500,000"
            assert TextProcessor.extract_text_after_label(
                text, "Location") is None

        def test_extract_text_empty(self):
            """Test with empty or None input."""
            assert TextProcessor.extract_text_after_label("", "Label") is None
            assert TextProcessor.extract_text_after_label(
                None, "Label") is None

        def test_extract_text_multiple_patterns(self):
            """Test with multiple possible label patterns."""
            text = "Property Description: Beautiful home with views."
            assert TextProcessor.extract_text_after_label(
                text, ["Description:", "Property Description:"]) == "Beautiful home with views."

    class TestExtractNumericValue:
        """Tests for the extract_numeric_value method."""

        @pytest.mark.parametrize("input_text, expected", [
            ("Price: $500,000", 500),
            ("5.5 acres", 5.5),
            ("3 bed, 2 bath", 3),
            ("No numbers here", None),
            ("", None),
            (None, None)
        ])
        def test_extract_numeric_value(self, input_text, expected):
            """Test numeric value extraction with various inputs."""
            assert TextProcessor.extract_numeric_value(input_text) == expected

        def test_extract_numeric_value_with_default(self):
            """Test using default value when no numeric value is found."""
            assert TextProcessor.extract_numeric_value(
                "No numbers", default=0) == 0
            assert TextProcessor.extract_numeric_value("", default=10) == 10

    class TestStandardizePrice:
        """Tests for the standardize_price method."""

        @pytest.mark.parametrize("price_text, expected_price, expected_bucket", [
            ("$500,000", "$500,000", "$300K - $600K"),
            ("$1,500,000", "$1.5M", "$1.5M - $2M"),
            ("$299,000", "$299,000", "Under $300K"),
            ("$2,000,000", "$2M", "$2M+"),
            ("Price: 500000", "$500,000", "$300K - $600K"),
            ("Contact for price", "Contact for Price", "N/A"),
            ("", "Contact for Price", "N/A"),
            (None, "Contact for Price", "N/A")
        ])
        def test_standardize_price(self, price_text, expected_price, expected_bucket):
            """Test price standardization with various inputs."""
            price, bucket = TextProcessor.standardize_price(price_text)
            assert price == expected_price
            assert bucket == expected_bucket

    class TestStandardizeAcreage:
        """Tests for the standardize_acreage method."""

        @pytest.mark.parametrize("acreage_text, expected_acreage, expected_bucket", [
            ("10 acres", "10.0 acres", "Medium (5-20 acres)"),
            ("2.5 acres", "2.5 acres", "Small (1-5 acres)"),
            ("0.5 acres", "0.5 acres", "Tiny (Under 1 acre)"),
            ("150 acres", "150.0 acres", "Extensive (100+ acres)"),
            ("Approximately 15 acres", "15.0 acres", "Medium (5-20 acres)"),
            ("Property on 20 acre lot", "20.0 acres", "Large (20-50 acres)"),
            ("", "Not specified", "Unknown"),
            (None, "Not specified", "Unknown"),
            ("No acreage listed", "Not specified", "Unknown")
        ])
        def test_standardize_acreage(self, acreage_text, expected_acreage, expected_bucket):
            """Test acreage standardization with various inputs."""
            acreage, bucket = TextProcessor.standardize_acreage(acreage_text)
            assert acreage == expected_acreage
            assert bucket == expected_bucket

    class TestExtractPropertyType:
        """Tests for the extract_property_type method."""

        @pytest.mark.parametrize("description, expected_type", [
            ("Single Family Home", "Single Family"),
            ("This house has 3 bedrooms", "Single Family"),
            ("4 bed single-story home", "Single Family"),
            ("Multi-Family Property", "Multi Family"),
            ("Duplex for sale", "Multi Family"),
            ("Farm land for sale", "Farm"),
            ("Agricultural property with barn", "Farm"),
            ("Pasture land available", "Farm"),
            ("Vacant lot for sale", "Land"),
            ("Undeveloped land with trees", "Land"),
            ("Commercial property", "Commercial"),
            ("Retail space available", "Commercial"),
            ("Generic property", "Unknown"),
            ("", "Unknown")
        ])
        def test_extract_property_type(self, description, expected_type):
            """Test property type extraction with various descriptions."""
            assert TextProcessor.extract_property_type(
                description) == expected_type

    class TestExtractBedBathCount:
        """Tests for the extract_bed_bath_count method."""

        def test_extract_bed_bath_basic(self):
            """Test basic bed/bath extraction."""
            text = "3 bedroom, 2 bathroom house"
            result = TextProcessor.extract_bed_bath_count(text)
            assert result['beds'] == "3"
            assert result['baths'] == "2"

        def test_extract_bed_bath_variations(self):
            """Test variations in bed/bath descriptions."""
            text = "Property with 4 beds and 2.5 baths"
            result = TextProcessor.extract_bed_bath_count(text)
            assert result['beds'] == "4"
            assert result['baths'] == "2.5"

            text = "3BR/2BA home"
            result = TextProcessor.extract_bed_bath_count(text)
            assert result['beds'] == "3"
            assert result['baths'] == "2"

        def test_extract_bed_bath_partial(self):
            """Test when only some information is available."""
            text = "3 bedroom house"
            result = TextProcessor.extract_bed_bath_count(text)
            assert result['beds'] == "3"
            assert result['baths'] is None

            text = "Home with 2 bathrooms"
            result = TextProcessor.extract_bed_bath_count(text)
            assert result['beds'] is None
            assert result['baths'] == "2"

        def test_extract_bed_bath_none(self):
            """Test when no bed/bath information is available."""
            text = "Beautiful property"
            result = TextProcessor.extract_bed_bath_count(text)
            assert result['beds'] is None
            assert result['baths'] is None

            result = TextProcessor.extract_bed_bath_count("")
            assert result['beds'] is None
            assert result['baths'] is None

    class TestExtractKeywords:
        """Tests for the extract_keywords method."""

        def test_extract_keywords_basic(self):
            """Test basic keyword extraction."""
            text = "Beautiful farmland with mountain views and a renovated barn"
            keywords = TextProcessor.extract_keywords(text)
            assert "beautiful" in keywords
            assert "farmland" in keywords
            assert "mountain" in keywords
            assert "renovated" in keywords

        def test_extract_keywords_min_length(self):
            """Test minimum word length for keywords."""
            text = "The big red farm is old but charming"
            keywords = TextProcessor.extract_keywords(text, min_word_length=5)
            assert "farm" not in keywords  # 'farm' is only 4 letters
            assert "charming" in keywords

        def test_extract_keywords_max_count(self):
            """Test maximum number of keywords."""
            text = "This is a long text with many words that could be considered keywords"
            keywords = TextProcessor.extract_keywords(text, max_keywords=3)
            assert len(keywords) <= 3

        def test_extract_keywords_empty(self):
            """Test with empty input."""
            assert TextProcessor.extract_keywords("") == []
            assert TextProcessor.extract_keywords(None) == []

    class TestSummarizeText:
        """Tests for the summarize_text method."""

        def test_summarize_text_basic(self):
            """Test basic text summarization."""
            text = "This is the first sentence. This is the second sentence. This is the third sentence."
            summary = TextProcessor.summarize_text(text, max_length=30)
            assert summary.startswith("This is the first sentence")
            assert len(summary) <= 30

        def test_summarize_text_short(self):
            """Test summarizing text that's already shorter than max_length."""
            text = "Short text."
            assert TextProcessor.summarize_text(
                text, max_length=50) == "Short text."

        def test_summarize_text_ellipsis(self):
            """Test that ellipsis is added when text is truncated."""
            text = "First sentence. Second sentence. Third sentence."
            summary = TextProcessor.summarize_text(text, max_length=20)
            assert summary.endswith("...")

        def test_summarize_text_empty(self):
            """Test with empty input."""
            assert TextProcessor.summarize_text("") == ""
            assert TextProcessor.summarize_text(None) == ""

    class TestExtractFromSoup:
        """Tests for the extract_from_soup method."""

        def test_extract_from_soup_basic(self):
            """Test basic extraction from BeautifulSoup."""
            html = "<div class='price'>$500,000</div>"
            soup = BeautifulSoup(html, 'html.parser')
            selectors = [{"class_": "price"}]
            assert TextProcessor.extract_from_soup(
                soup, selectors) == "$500,000"

        def test_extract_from_soup_multiple_selectors(self):
            """Test multiple selectors until one succeeds."""
            html = "<div class='price'>$500,000</div>"
            soup = BeautifulSoup(html, 'html.parser')
            selectors = [{"class_": "wrong-class"}, {"class_": "price"}]
            assert TextProcessor.extract_from_soup(
                soup, selectors) == "$500,000"

        def test_extract_from_soup_id(self):
            """Test extraction using ID selector."""
            html = "<div id='price'>$500,000</div>"
            soup = BeautifulSoup(html, 'html.parser')
            selectors = [{"id": "price"}]
            assert TextProcessor.extract_from_soup(
                soup, selectors) == "$500,000"

        def test_extract_from_soup_tag_attrs(self):
            """Test extraction using tag and attributes."""
            html = "<div data-test='price'>$500,000</div>"
            soup = BeautifulSoup(html, 'html.parser')
            selectors = [{"tag": "div", "attrs": {"data-test": "price"}}]
            assert TextProcessor.extract_from_soup(
                soup, selectors) == "$500,000"

        def test_extract_from_soup_not_found(self):
            """Test when no selector matches."""
            html = "<div class='price'>$500,000</div>"
            soup = BeautifulSoup(html, 'html.parser')
            selectors = [{"class_": "wrong-class"}]
            assert TextProcessor.extract_from_soup(soup, selectors) is None

        def test_extract_from_soup_error_handling(self):
            """Test error handling during extraction."""
            html = "<div class='price'>$500,000</div>"
            soup = BeautifulSoup(html, 'html.parser')
            # Invalid selector type should be skipped without error
            selectors = [{"invalid_selector": "value"}, {"class_": "price"}]
            assert TextProcessor.extract_from_soup(
                soup, selectors) == "$500,000"


class TestBackwardCompatibility:
    """Tests for backward compatibility functions."""

    def test_clean_html_text_function(self):
        """Test the standalone clean_html_text function."""
        assert clean_html_text("  Hello  World  ") == "Hello World"
        assert clean_html_text("Hello&nbsp;World") == "Hello World"
        assert clean_html_text("") == ""

    def test_extract_property_type_function(self):
        """Test the standalone extract_property_type function."""
        assert extract_property_type("Single Family Home") == "Single Family"
        assert extract_property_type("Farm land") == "Farm"
        assert extract_property_type("") == "Unknown"

    def test_clean_price_function(self):
        """Test the standalone clean_price function."""
        price, bucket = clean_price("$500,000")
        assert price == "$500,000"
        assert bucket == "$300K - $600K"

        price, bucket = clean_price("Contact for price")
        assert price == "Contact for Price"
        assert bucket == "N/A"

    def test_extract_acreage_function(self):
        """Test the standalone extract_acreage function."""
        acreage, bucket = extract_acreage("10 acres")
        assert acreage == "10.0 acres"
        assert bucket == "Medium (5-20 acres)"

        acreage, bucket = extract_acreage("")
        assert acreage == "Not specified"
        assert bucket == "Unknown"
