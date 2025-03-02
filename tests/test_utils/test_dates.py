# tests/test_utils/test_dates.py
import pytest
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from new_england_listings.utils.dates import (
    DateExtractor, extract_listing_date, parse_date_string, is_recent_listing
)


class TestDateExtractor:
    def test_parse_date_string(self):
        """Test parsing of various date formats."""
        # Test standard formats
        assert DateExtractor.parse_date_string(
            "January 15, 2023") == "2023-01-15"
        assert DateExtractor.parse_date_string("01/15/2023") == "2023-01-15"
        assert DateExtractor.parse_date_string("2023-01-15") == "2023-01-15"

        # Test abbreviated month names
        assert DateExtractor.parse_date_string("Jan 15, 2023") == "2023-01-15"

        # Test invalid formats
        assert DateExtractor.parse_date_string("Invalid date") is None
        assert DateExtractor.parse_date_string("") is None
        assert DateExtractor.parse_date_string(None) is None

    def test_extract_listing_date(self):
        """Test extraction of listing dates from HTML."""
        # Test with various HTML structures
        html = """
        <div class="listing-date">January 15, 2023</div>
        """
        soup = BeautifulSoup(html, 'html.parser')
        result = DateExtractor.extract_listing_date(soup, "Test Platform")
        assert result == "2023-01-15"

        # Test with date in different format
        html = """
        <span class="date">01/15/2023</span>
        """
        soup = BeautifulSoup(html, 'html.parser')
        result = DateExtractor.extract_listing_date(soup, "Test Platform")
        assert result == "2023-01-15"

        # Test with missing date (should return current date)
        html = "<div>No date here</div>"
        soup = BeautifulSoup(html, 'html.parser')
        result = DateExtractor.extract_listing_date(soup, "Test Platform")
        # Should be today's date
        assert result == datetime.now().strftime('%Y-%m-%d')

    def test_is_recent_listing(self):
        """Test determination of recent listings."""
        # Create a date 10 days ago
        ten_days_ago = (datetime.now() - timedelta(days=10)
                        ).strftime('%Y-%m-%d')
        # Create a date 40 days ago
        forty_days_ago = (datetime.now() - timedelta(days=40)
                          ).strftime('%Y-%m-%d')

        # Test with default 30 days threshold
        assert is_recent_listing(ten_days_ago) is True
        assert is_recent_listing(forty_days_ago) is False

        # Test with custom threshold
        assert is_recent_listing(ten_days_ago, days=5) is False
        assert is_recent_listing(ten_days_ago, days=15) is True

        # Test with invalid date
        assert is_recent_listing("invalid date") is False

    def test_extract_date_from_text(self):
        """Test extraction of dates from general text."""
        # Test various text snippets with dates
        assert DateExtractor.extract_date_from_text(
            "Listed on January 15, 2023") == "2023-01-15"
        assert DateExtractor.extract_date_from_text(
            "Property added 01/15/2023") == "2023-01-15"
        assert DateExtractor.extract_date_from_text("No date here") is None

    def test_backward_compatibility(self):
        """Test that old function names still work."""
        # Test that old function names redirect to new static methods
        assert parse_date_string("January 15, 2023") == "2023-01-15"

        html = """
        <div class="listing-date">January 15, 2023</div>
        """
        soup = BeautifulSoup(html, 'html.parser')
        assert extract_listing_date(soup, "Test Platform") == "2023-01-15"
