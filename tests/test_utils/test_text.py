# tests/test_utils/test_text.py
import pytest
from new_england_listings.utils.text import (
    clean_price,
    extract_acreage,
    clean_html_text,
    extract_property_type
)


class TestPriceCleaning:
    def test_clean_price_basic(self):
        """Test basic price cleaning."""
        assert clean_price("$500,000") == ("$500,000", "$300K - $600K")

    def test_clean_price_contact(self):
        """Test 'contact for price' cases."""
        assert clean_price("Contact agent") == ("Contact for Price", "N/A")

    def test_clean_price_million(self):
        """Test prices over a million."""
        assert clean_price("$1,500,000") == ("$1.5M", "1.5M - $2M")

    def test_clean_price_invalid(self):
        """Test invalid price formats."""
        assert clean_price("invalid") == ("Contact for Price", "N/A")
        assert clean_price("") == ("Contact for Price", "N/A")
        assert clean_price(None) == ("Contact for Price", "N/A")


class TestAcreageExtraction:
    def test_extract_acreage_basic(self):
        """Test basic acreage extraction."""
        assert extract_acreage("10 acres") == ("10.0 acres", "Medium (5-20 acres)")

    def test_extract_acreage_decimal(self):
        """Test decimal acreage values."""
        assert extract_acreage("2.5 acres") == (
            "2.5 acres", "Small (1-5 acres)")

    def test_extract_acreage_text_variants(self):
        """Test different text patterns for acreage."""
        assert extract_acreage("Approximately 15 acres") == (
            "15.0 acres", "Medium (5-20 acres)")
        assert extract_acreage("20 acre parcel") == (
            "20.0 acres", "Large (20-50 acres)")

    def test_extract_acreage_invalid(self):
        """Test invalid acreage formats."""
        assert extract_acreage("No acreage listed") == (
            "Not specified", "Unknown")
        assert extract_acreage("") == ("Not specified", "Unknown")


class TestHTMLCleaning:
    def test_clean_html_basic(self):
        """Test basic HTML text cleaning."""
        assert clean_html_text("  Hello  World  ") == "Hello World"

    def test_clean_html_special_chars(self):
        """Test cleaning of HTML special characters."""
        assert clean_html_text("Hello&nbsp;World") == "Hello World"
        assert clean_html_text("This &amp; That") == "This & That"

    def test_clean_html_newlines(self):
        """Test cleaning of newlines and tabs."""
        assert clean_html_text("Hello\nWorld\tTest") == "Hello World Test"


class TestPropertyTypeExtraction:
    def test_extract_property_type_basic(self):
        """Test basic property type extraction."""
        assert extract_property_type("Single Family Home") == "Single Family"
        assert extract_property_type("Multi-Family Property") == "Multi Family"
        assert extract_property_type("Farm Land") == "Farm"

    def test_extract_property_type_variants(self):
        """Test variations in property type descriptions."""
        assert extract_property_type("residential home") == "Single Family"
        assert extract_property_type("duplex building") == "Multi Family"
        assert extract_property_type("agricultural land") == "Farm"

    def test_extract_property_type_unknown(self):
        """Test unknown property types."""
        assert extract_property_type("unknown type") == "Other"
        assert extract_property_type("") == "Other"
