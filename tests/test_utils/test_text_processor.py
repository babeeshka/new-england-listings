# tests/test_utils/test_text_processor.py
import pytest
from bs4 import BeautifulSoup
from new_england_listings.utils.text import TextProcessor


class TestCleanHtmlText:
    def test_clean_html_basic(self):
        """Test basic HTML text cleaning."""
        assert TextProcessor.clean_html_text(
            "  Hello  World  ") == "Hello World"

    def test_clean_html_special_chars(self):
        """Test cleaning of HTML special characters."""
        assert TextProcessor.clean_html_text(
            "Hello&nbsp;World") == "Hello World"
        assert TextProcessor.clean_html_text(
            "This &amp; That") == "This & That"

    def test_clean_html_newlines(self):
        """Test cleaning of newlines and tabs."""
        assert TextProcessor.clean_html_text(
            "Hello\nWorld\tTest") == "Hello World Test"

    def test_clean_html_empty(self):
        """Test cleaning of empty or None input."""
        assert TextProcessor.clean_html_text("") == ""
        assert TextProcessor.clean_html_text(None) == ""


class TestExtractTextAfterLabel:
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

    def test_extract_text_not_found(self):
        """Test when label is not found."""
        text = "Price: $500,000"
        assert TextProcessor.extract_text_after_label(text, "Location") is None

    def test_extract_text_empty(self):
        """Test with empty or None input."""
        assert TextProcessor.extract_text_after_label("", "Label") is None
        assert TextProcessor.extract_text_after_label(None, "Label") is None


class TestExtractNumericValue:
    def test_extract_numeric_basic(self):
        """Test basic numeric extraction."""
        assert TextProcessor.extract_numeric_value(
            "Price: $500,000") == 500  # Extracts first group of digits
        assert TextProcessor.extract_numeric_value(
            "5.5 acres") == 5.5  # Extracts decimal correctly

    def test_extract_numeric_first_only(self):
        """Test that only the first numeric value is extracted."""
        assert TextProcessor.extract_numeric_value("3 bed, 2 bath") == 3

    def test_extract_numeric_default(self):
        """Test default value when no numeric value is found."""
        assert TextProcessor.extract_numeric_value(
            "No numbers here", default=0) == 0

    def test_extract_numeric_empty(self):
        """Test with empty or None input."""
        assert TextProcessor.extract_numeric_value("") is None
        assert TextProcessor.extract_numeric_value(None) is None


class TestStandardizePrice:
    def test_standardize_price_basic(self):
        """Test basic price standardization."""
        assert TextProcessor.standardize_price(
            "$500,000") == ("$500,000", "$300K - $600K")

    def test_standardize_price_millions(self):
        """Test prices in millions."""
        assert TextProcessor.standardize_price(
            "$1,500,000") == ("$1.5M", "$1.5M - $2M")
        assert TextProcessor.standardize_price("$2,000,000") == ("$2M", "$2M+")

    def test_standardize_price_non_standard_formats(self):
        """Test non-standard price formats."""
        assert TextProcessor.standardize_price(
            "Price: 500000") == ("$500,000", "$300K - $600K")

    def test_standardize_price_contact(self):
        """Test 'contact for price' cases."""
        assert TextProcessor.standardize_price(
            "Contact for price") == ("Contact for Price", "N/A")
        assert TextProcessor.standardize_price(
            "") == ("Contact for Price", "N/A")
        assert TextProcessor.standardize_price(
            None) == ("Contact for Price", "N/A")


class TestStandardizeAcreage:
    def test_standardize_acreage_basic(self):
        """Test basic acreage standardization."""
        assert TextProcessor.standardize_acreage(
            "10 acres") == ("10.0 acres", "Medium (5-20 acres)")

    def test_standardize_acreage_decimal(self):
        """Test decimal acreage."""
        assert TextProcessor.standardize_acreage(
            "2.5 acres") == ("2.5 acres", "Small (1-5 acres)")

    def test_standardize_acreage_variations(self):
        """Test variations in acreage text."""
        assert TextProcessor.standardize_acreage(
            "Approximately 15 acres") == ("15.0 acres", "Medium (5-20 acres)")
        assert TextProcessor.standardize_acreage(
            "Property on 20 acre lot") == ("20.0 acres", "Large (20-50 acres)")

    def test_standardize_acreage_not_specified(self):
        """Test when acreage is not specified."""
        assert TextProcessor.standardize_acreage(
            "") == ("Not specified", "Unknown")
        assert TextProcessor.standardize_acreage(
            None) == ("Not specified", "Unknown")
        assert TextProcessor.standardize_acreage(
            "No acreage listed") == ("Not specified", "Unknown")


class TestExtractPropertyType:
    def test_extract_property_type_basic(self):
        """Test basic property type extraction."""
        assert TextProcessor.extract_property_type(
            "Single Family Home") == "Single Family"
        assert TextProcessor.extract_property_type(
            "Farm land for sale") == "Farm"
        assert TextProcessor.extract_property_type(
            "Commercial property") == "Commercial"

    def test_extract_property_type_variations(self):
        """Test variations in property descriptions."""
        assert TextProcessor.extract_property_type(
            "This house has 3 bedrooms") == "Single Family"
        assert TextProcessor.extract_property_type(
            "Agricultural property with barn") == "Farm"
        assert TextProcessor.extract_property_type(
            "Retail space available") == "Commercial"

    def test_extract_property_type_unknown(self):
        """Test unknown property types."""
        assert TextProcessor.extract_property_type(
            "Generic property") == "Unknown"
        assert TextProcessor.extract_property_type("") == "Unknown"


class TestExtractBedBathCount:
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

    def test_extract_bed_bath_none(self):
        """Test when no bed/bath information is available."""
        text = "Beautiful property"
        result = TextProcessor.extract_bed_bath_count(text)
        assert result['beds'] is None
        assert result['baths'] is None


class TestExtractKeywords:
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
    def test_extract_from_soup_basic(self):
        """Test basic extraction from BeautifulSoup."""
        html = "<div class='price'>$500,000</div>"
        soup = BeautifulSoup(html, 'html.parser')
        selectors = [{"class_": "price"}]
        assert TextProcessor.extract_from_soup(soup, selectors) == "$500,000"

    def test_extract_from_soup_multiple_selectors(self):
        """Test multiple selectors until one succeeds."""
        html = "<div class='price'>$500,000</div>"
        soup = BeautifulSoup(html, 'html.parser')
        selectors = [{"class_": "wrong-class"}, {"class_": "price"}]
        assert TextProcessor.extract_from_soup(soup, selectors) == "$500,000"

    def test_extract_from_soup_id(self):
        """Test extraction using ID selector."""
        html = "<div id='price'>$500,000</div>"
        soup = BeautifulSoup(html, 'html.parser')
        selectors = [{"id": "price"}]
        assert TextProcessor.extract_from_soup(soup, selectors) == "$500,000"

    def test_extract_from_soup_tag_attrs(self):
        """Test extraction using tag and attributes."""
        html = "<div data-test='price'>$500,000</div>"
        soup = BeautifulSoup(html, 'html.parser')
        selectors = [{"tag": "div", "attrs": {"data-test": "price"}}]
        assert TextProcessor.extract_from_soup(soup, selectors) == "$500,000"

    def test_extract_from_soup_not_found(self):
        """Test when no selector matches."""
        html = "<div class='price'>$500,000</div>"
        soup = BeautifulSoup(html, 'html.parser')
        selectors = [{"class_": "wrong-class"}]
        assert TextProcessor.extract_from_soup(soup, selectors) is None
