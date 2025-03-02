# tests/test_utils/test_dates.py
import pytest
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from new_england_listings.utils.dates import (
    DateExtractor, extract_listing_date, parse_date_string, is_recent_listing
)


class TestDateExtractor:
    """Tests for the DateExtractor class which handles date extraction and parsing."""

    class TestParseDateString:
        """Tests for the parse_date_string method."""

        def test_parse_date_string_month_day_year(self):
            """Test parsing Month Day, Year format."""
            date = DateExtractor.parse_date_string("January 15, 2023")
            assert date == "2023-01-15"

            date = DateExtractor.parse_date_string("Feb 28, 2023")
            assert date == "2023-02-28"

        def test_parse_date_string_numeric_formats(self):
            """Test parsing numeric date formats."""
            date = DateExtractor.parse_date_string("01/15/2023")
            assert date == "2023-01-15"

            date = DateExtractor.parse_date_string("2023-01-15")
            assert date == "2023-01-15"

            date = DateExtractor.parse_date_string("01-15-2023")
            assert date == "2023-01-15"

        def test_parse_date_string_with_text(self):
            """Test parsing dates embedded in text."""
            date = DateExtractor.parse_date_string(
                "Listed on January 15, 2023")
            assert date == "2023-01-15"

            date = DateExtractor.parse_date_string("Date Listed: 01/15/2023")
            assert date == "2023-01-15"

        def test_parse_date_string_invalid(self):
            """Test handling invalid date strings."""
            assert DateExtractor.parse_date_string("") is None
            assert DateExtractor.parse_date_string("Not a date") is None
            assert DateExtractor.parse_date_string(
                "13/45/2023") is None  # Invalid date

        def test_parse_date_string_special_cases(self):
            """Test special date parsing cases."""
            # September abbreviated as both Sep and Sept
            date = DateExtractor.parse_date_string("Sept 15, 2023")
            assert date == "2023-09-15"

            date = DateExtractor.parse_date_string("Sep 15, 2023")
            assert date == "2023-09-15"

    class TestExtractListingDate:
        """Tests for the extract_listing_date method."""

        @pytest.fixture
        def sample_soup(self):
            html = """
            <html>
                <div class="listing-date">January 15, 2023</div>
                <span class="date">02/20/2023</span>
                <time datetime="2023-03-25">March 25, 2023</time>
                <div class="post-date">Posted on: April 30, 2023</div>
            </html>
            """
            return BeautifulSoup(html, 'html.parser')

        def test_extract_listing_date_realtor(self, sample_soup):
            """Test extracting date from Realtor.com format."""
            date = DateExtractor.extract_listing_date(
                sample_soup, "Realtor.com")
            assert date == "2023-01-15"  # Uses first date found

        def test_extract_listing_date_land_and_farm(self, sample_soup):
            """Test extracting date from Land and Farm format."""
            date = DateExtractor.extract_listing_date(
                sample_soup, "Land and Farm")
            assert date == "2023-01-15"  # Uses first date found

        def test_extract_listing_date_no_date(self):
            """Test handling when no date is found."""
            soup = BeautifulSoup(
                "<html><div>No date here</div></html>", 'html.parser')
            date = DateExtractor.extract_listing_date(soup, "Any Platform")
            today = datetime.now().strftime('%Y-%m-%d')
            assert date == today  # Returns current date if no date found

        def test_extract_listing_date_with_time_element(self, sample_soup):
            """Test extracting date from time element."""
            # Modify soup to make time element the most likely to be found
            for tag in sample_soup.find_all(["div", "span"]):
                tag.decompose()
            date = DateExtractor.extract_listing_date(
                sample_soup, "Any Platform")
            assert date == "2023-03-25"

    class TestIsRecentListing:
        """Tests for the is_recent_listing method."""

        def test_is_recent_listing_recent(self):
            """Test identifying recent listings."""
            today = datetime.now().strftime('%Y-%m-%d')
            assert DateExtractor.is_recent_listing(today) is True

            # Testing a date 15 days ago (should be recent with default 30 days)
            fifteen_days_ago = (
                datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d')
            assert DateExtractor.is_recent_listing(fifteen_days_ago) is True

        def test_is_recent_listing_old(self):
            """Test identifying old listings."""
            # Testing a date 45 days ago (should not be recent with default 30 days)
            forty_five_days_ago = (
                datetime.now() - timedelta(days=45)).strftime('%Y-%m-%d')
            assert DateExtractor.is_recent_listing(
                forty_five_days_ago) is False

        def test_is_recent_listing_custom_days(self):
            """Test with custom days threshold."""
            # 10 days ago with 15-day threshold (should be recent)
            ten_days_ago = (datetime.now() - timedelta(days=10)
                            ).strftime('%Y-%m-%d')
            assert DateExtractor.is_recent_listing(
                ten_days_ago, days=15) is True

            # 20 days ago with 15-day threshold (should not be recent)
            twenty_days_ago = (
                datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
            assert DateExtractor.is_recent_listing(
                twenty_days_ago, days=15) is False

        def test_is_recent_listing_invalid(self):
            """Test handling invalid date strings."""
            assert DateExtractor.is_recent_listing("Not a date") is False
            assert DateExtractor.is_recent_listing("") is False

    class TestExtractDateFromText:
        """Tests for the extract_date_from_text method."""

        def test_extract_date_from_text_basic(self):
            """Test basic date extraction from text."""
            text = "This property was listed on January 15, 2023."
            date = DateExtractor.extract_date_from_text(text)
            assert date == "2023-01-15"

        def test_extract_date_from_text_multiple_dates(self):
            """Test extracting the first date when multiple dates are present."""
            text = "Listed on 01/15/2023. Updated on 02/20/2023."
            date = DateExtractor.extract_date_from_text(text)
            assert date == "2023-01-15"  # Should extract the first date

        def test_extract_date_from_text_various_formats(self):
            """Test extracting dates in various formats."""
            formats = [
                "01/15/2023",
                "2023-01-15",
                "January 15, 2023",
                "Jan 15, 2023",
                "15-01-2023"  # DD-MM-YYYY format
            ]

            for format_str in formats:
                date = DateExtractor.extract_date_from_text(
                    f"Date: {format_str}")
                assert date is not None

        def test_extract_date_from_text_no_date(self):
            """Test when no date is present."""
            text = "This text has no date information."
            date = DateExtractor.extract_date_from_text(text)
            assert date is None

        def test_extract_date_from_text_empty(self):
            """Test with empty or None input."""
            assert DateExtractor.extract_date_from_text("") is None
            assert DateExtractor.extract_date_from_text(None) is None

    class TestParseWithDateutil:
        """Tests for the parse_with_dateutil method."""

        @pytest.mark.parametrize("date_string, expected", [
            ("Jan 1, 2023", "2023-01-01"),
            ("2023-01-01", "2023-01-01"),
            ("01/01/2023", "2023-01-01"),
            ("January 1st, 2023", "2023-01-01"),
            ("1st Jan 2023", "2023-01-01"),
            ("2023.01.01", "2023-01-01"),
            ("Sunday, January 1, 2023", "2023-01-01"),
        ])
        def test_parse_with_dateutil_various_formats(self, date_string, expected):
            """Test parsing various date formats with dateutil."""
            try:
                result = DateExtractor.parse_with_dateutil(date_string)
                assert result == expected
            except ImportError:
                pytest.skip("dateutil not installed, skipping test")

        def test_parse_with_dateutil_invalid(self):
            """Test handling invalid date strings."""
            try:
                assert DateExtractor.parse_with_dateutil("Not a date") is None
                assert DateExtractor.parse_with_dateutil("") is None
                assert DateExtractor.parse_with_dateutil(None) is None
            except ImportError:
                pytest.skip("dateutil not installed, skipping test")


class TestBackwardsCompatibility:
    """Tests for the backwards compatibility functions."""

    def test_extract_listing_date_function(self):
        """Test that the standalone function works."""
        soup = BeautifulSoup(
            "<div class='listing-date'>January 15, 2023</div>", 'html.parser')
        date = extract_listing_date(soup, "Any Platform")
        assert date == "2023-01-15"

    def test_parse_date_string_function(self):
        """Test that the standalone function works."""
        date = parse_date_string("January 15, 2023")
        assert date == "2023-01-15"

    def test_is_recent_listing_function(self):
        """Test that the standalone function works."""
        today = datetime.now().strftime('%Y-%m-%d')
        assert is_recent_listing(today) is True
