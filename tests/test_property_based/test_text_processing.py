# tests/test_property_based/test_text_processing.py
import pytest
from hypothesis import given, settings, strategies as st, assume
import re
from datetime import datetime, timedelta

from new_england_listings.utils.text import TextProcessor
from new_england_listings.utils.dates import DateExtractor
from new_england_listings.config.constants import (
    PRICE_BUCKETS, ACREAGE_BUCKETS, DISTANCE_BUCKETS
)


# ------------------- Custom Strategies -------------------

@st.composite
def price_texts(draw):
    """Generate realistic price text variations."""
    # Different price formats
    price_value = draw(st.integers(min_value=1000, max_value=10000000))

    # Different formats
    formats = [
        # Standard formats
        "${:,}",
        "${:,}.00",
        "${:.2f}",
        "${:.1f}K" if price_value < 1000000 else "${:.1f}M",

        # With text
        "Price: ${:,}",
        "Listed for ${:,}",
        "Asking price ${:,}",

        # Various currency formats
        "USD {:,}",
        "US${:,}",

        # Without symbols
        "{:,}",
        "{:,} dollars",
        "{:,} USD",
    ]

    format_str = draw(st.sampled_from(formats))

    # Format the price
    if "K" in format_str:
        price_text = format_str.format(price_value / 1000)
    elif "M" in format_str:
        price_text = format_str.format(price_value / 1000000)
    elif ".1f" in format_str or ".2f" in format_str:
        price_text = format_str.format(float(price_value))
    else:
        price_text = format_str.format(price_value)

    return price_text


@st.composite
def acreage_texts(draw):
    """Generate realistic acreage text variations."""
    # Different acreage values
    acreage_value = draw(st.floats(min_value=0.1, max_value=1000.0))

    # Different formats
    formats = [
        # Standard formats
        "{:.1f} acres",
        "{:.2f} acres",
        "{} acre" if acreage_value == 1 else "{} acres",
        "approximately {:.1f} acres",
        "about {:.1f} acres",
        "{:.1f} acre lot",
        "{:.1f} acre parcel",

        # With text
        "Land size: {:.1f} acres",
        "Property on {:.1f} acres",
        "Lot size: {:.1f} acres",

        # Square feet conversion (43,560 sq ft = 1 acre)
        "{} sq ft" if acreage_value < 5 else "{:.1f} acres",
    ]

    format_str = draw(st.sampled_from(formats))

    # Format the acreage
    if "sq ft" in format_str:
        # Convert acres to square feet
        sq_ft = int(acreage_value * 43560)
        acreage_text = format_str.format(sq_ft)
    elif ".1f" in format_str or ".2f" in format_str:
        acreage_text = format_str.format(acreage_value)
    else:
        acreage_text = format_str.format(int(acreage_value))

    return acreage_text


@st.composite
def date_texts(draw):
    """Generate realistic date text variations."""
    # Generate a random date within the last few years
    # Up to 3 years ago
    days_ago = draw(st.integers(min_value=0, max_value=1095))
    date_value = datetime.now() - timedelta(days=days_ago)

    # Different formats
    formats = [
        # Standard formats
        "{:%B %d, %Y}",  # January 15, 2023
        "{:%b %d, %Y}",  # Jan 15, 2023
        "{:%m/%d/%Y}",   # 01/15/2023
        "{:%Y-%m-%d}",   # 2023-01-15
        "{:%d-%m-%Y}",   # 15-01-2023
        "{:%d.%m.%Y}",   # 15.01.2023

        # With text
        "Listed on {:%B %d, %Y}",
        "Date Listed: {:%m/%d/%Y}",
        "Posted on {:%Y-%m-%d}",
        "Published: {:%b %d, %Y}",

        # Relative dates
        "{} days ago" if days_ago < 60 else "{:%B %d, %Y}",
        "{} weeks ago" if days_ago < 60 else "{:%B %d, %Y}",
    ]

    format_str = draw(st.sampled_from(formats))

    # Format the date
    if "days ago" in format_str:
        date_text = format_str.format(days_ago)
    elif "weeks ago" in format_str:
        date_text = format_str.format(days_ago // 7)
    else:
        date_text = format_str.format(date_value)

    return date_text


@st.composite
def html_texts(draw):
    """Generate HTML text with various elements and entities."""
    # Base text
    base_text = draw(st.text(min_size=1, max_size=100))

    # HTML entity options
    entities = [
        "&nbsp;", "&amp;", "&lt;", "&gt;", "&quot;", "&#39;",
        "&#x27;", "&#x2F;", "&copy;", "&reg;"
    ]

    # Random whitespace
    whitespaces = [" ", "  ", "\t", "\n", "\r\n"]

    # Insert random entities and whitespace
    entity_count = draw(st.integers(min_value=0, max_value=5))
    whitespace_count = draw(st.integers(min_value=0, max_value=5))

    modified_text = base_text

    for _ in range(entity_count):
        entity = draw(st.sampled_from(entities))
        insert_position = draw(st.integers(
            min_value=0, max_value=len(modified_text)))
        modified_text = modified_text[:insert_position] + \
            entity + modified_text[insert_position:]

    for _ in range(whitespace_count):
        whitespace = draw(st.sampled_from(whitespaces))
        insert_position = draw(st.integers(
            min_value=0, max_value=len(modified_text)))
        modified_text = modified_text[:insert_position] + \
            whitespace + modified_text[insert_position:]

    return modified_text


# ------------------- Property-Based Tests -------------------

class TestTextProcessorProperties:
    """Property-based tests for TextProcessor."""

    @given(text=html_texts())
    def test_clean_html_text_properties(self, text):
        """Test properties of the clean_html_text method."""
        cleaned = TextProcessor.clean_html_text(text)

        # No HTML entities should remain
        assert "&nbsp;" not in cleaned
        assert "&amp;" not in cleaned
        assert "&lt;" not in cleaned
        assert "&gt;" not in cleaned

        # No consecutive whitespace
        assert "  " not in cleaned
        assert "\t" not in cleaned
        assert "\n" not in cleaned

        # Cleaned text should be stripped
        assert not (cleaned and (
            cleaned.startswith(" ") or cleaned.endswith(" ")))

        # Special case: empty input
        if not text or text.isspace():
            assert cleaned == ""

    @given(price_text=price_texts())
    def test_standardize_price_properties(self, price_text):
        """Test properties of standardize_price method."""
        # Skip "Contact for price" variations
        assume("contact" not in price_text.lower())
        assume("call" not in price_text.lower())
        assume("inquire" not in price_text.lower())

        price, bucket = TextProcessor.standardize_price(price_text)

        # Formatted price should start with $
        assert price.startswith("$"), f"Price '{price}' should start with $"

        # Bucket should be one of the defined buckets
        assert bucket in PRICE_BUCKETS.values(
        ), f"Bucket '{bucket}' should be in predefined buckets"

        # If price contains a number, the extracted value should be related
        if re.search(r'\d', price_text):
            # Extract numeric part of the result
            result_value = re.sub(r'[^\d.]', '', price)

            # $X.YM format handling
            if "M" in price:
                result_value = float(result_value) * 1000000
            # $X.YK format handling
            elif "K" in price:
                result_value = float(result_value) * 1000
            else:
                result_value = float(
                    result_value) if "." in result_value else int(result_value)

            # Extract numeric part of the input
            input_value = "".join(re.findall(r'\d', price_text))

            # Can't do exact comparison due to formatting differences
            # But should be in same order of magnitude
            if input_value and result_value > 0:
                input_magnitude = len(input_value)
                result_magnitude = len(str(int(result_value)))

                # Check magnitude is similar (allowing for K/M conversion)
                magnitude_diff = abs(input_magnitude - result_magnitude)
                assert magnitude_diff <= 3, f"Magnitude difference too large: {input_magnitude} vs {result_magnitude}"

    @given(acreage_text=acreage_texts())
    def test_standardize_acreage_properties(self, acreage_text):
        """Test properties of standardize_acreage method."""
        acreage, bucket = TextProcessor.standardize_acreage(acreage_text)

        # Result should contain 'acres' or be 'Not specified'
        assert "acres" in acreage or acreage == "Not specified"

        # Bucket should be one of the defined buckets or 'Unknown'
        assert bucket in ACREAGE_BUCKETS.values() or bucket == "Unknown"

        # If input has a number, result should have a number
        if re.search(r'\d', acreage_text):
            assert re.search(r'\d', acreage)

        # If input contains 'sq ft', result should be in acres
        if "sq ft" in acreage_text:
            assert "acres" in acreage

    @given(input_text=st.text(), label=st.text(min_size=1), max_words=st.integers(min_value=1, max_value=20))
    def test_extract_text_after_label_properties(self, input_text, label, max_words):
        """Test properties of extract_text_after_label method."""
        assume(label in input_text)

        result = TextProcessor.extract_text_after_label(
            input_text, label, max_words)

        # If label exists in input, result should not be None
        if label and label in input_text and input_text.index(label) < len(input_text) - len(label):
            assert result is not None

        # If result exists, it should not be longer than max_words
        if result:
            word_count = len(result.split())
            assert word_count <= max_words

    @settings(deadline=None)  # Disable deadline for potentially slow tests
    @given(text=st.text(min_size=5), min_word_length=st.integers(min_value=2, max_value=8))
    def test_extract_keywords_properties(self, text, min_word_length):
        """Test properties of extract_keywords method."""
        keywords = TextProcessor.extract_keywords(
            text, min_word_length=min_word_length)

        # All keywords should be in the original text
        for keyword in keywords:
            assert keyword.lower() in text.lower()

        # All keywords should meet minimum length
        for keyword in keywords:
            assert len(keyword) >= min_word_length

        # Keywords should not be duplicated
        assert len(keywords) == len(set(keywords))


class TestDateExtractorProperties:
    """Property-based tests for DateExtractor."""

    @given(date_text=date_texts())
    def test_parse_date_string_properties(self, date_text):
        """Test properties of parse_date_string method."""
        result = DateExtractor.parse_date_string(date_text)

        # If input contains digits, result should not be None
        # (except for relative dates like "3 days ago" which require special handling)
        if re.search(r'\d', date_text) and not any(x in date_text.lower() for x in ["days ago", "weeks ago", "months ago"]):
            assert result is not None

        # Result should be in YYYY-MM-DD format if not None
        if result:
            assert re.match(r'^\d{4}-\d{2}-\d{2}$', result)

            # Parsed date should be a valid date
            try:
                datetime.strptime(result, "%Y-%m-%d")
            except ValueError:
                pytest.fail(f"Parsed date is not valid: {result}")

    @given(date_str=st.dates())
    def test_format_date_for_display_properties(self, date_str):
        """Test properties of format_date_for_display method."""
        date_str_iso = date_str.isoformat()
        result = DateExtractor.format_date_for_display(date_str_iso)

        # Result should not be empty
        assert result

        # Result should include the year
        assert str(date_str.year) in result

        # Result should be properly formatted
        assert re.search(r'[A-Za-z]{3}\s+\d{1,2},\s+\d{4}', result)

    @given(days=st.integers(min_value=0, max_value=365))
    def test_is_recent_listing_properties(self, days):
        """Test properties of is_recent_listing method."""
        date_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # With default 30 days
        is_recent_default = DateExtractor.is_recent_listing(date_str)
        assert is_recent_default == (days <= 30)

        # With custom threshold
        threshold = 60
        is_recent_custom = DateExtractor.is_recent_listing(
            date_str, days=threshold)
        assert is_recent_custom == (days <= threshold)


# Use this conditional to enable running the tests directly
if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
