# tests/test_extractors.py
import pytest
from new_england_listings.models.base import PropertyListing
from new_england_listings.extractors.landsearch import LandSearchExtractor


def test_landsearch_extraction():
    extractor = LandSearchExtractor("https://example.com")
    result = extractor.extract(mock_soup)  # Mock your BeautifulSoup object

    assert isinstance(result, PropertyListing)
    assert result.property_type in PropertyType
    assert result.price_bucket in PriceBucket
    assert result.acreage_bucket in AcreageBucket
