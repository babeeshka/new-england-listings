# tests/test_extractors/test_realtor.py
import pytest
from new_england_listings.extractors import RealtorExtractor
from bs4 import BeautifulSoup


@pytest.fixture
def realtor_extractor():
    return RealtorExtractor("https://www.realtor.com/realestateandhomes-detail/example")


@pytest.fixture
def sample_html():
    return """
    <html>
        <h1 data-testid="listing-title">Sample Property</h1>
        <div data-testid="price">$500,000</div>
        <div data-testid="address">123 Main St, Portland, ME</div>
        <div data-testid="property-details">
            3 bed | 2 bath | 2,000 sqft
        </div>
    </html>
    """


def test_listing_name_extraction(realtor_extractor, sample_html):
    soup = BeautifulSoup(sample_html, 'html.parser')
    data = realtor_extractor.extract(soup)
    assert data["listing_name"] == "Sample Property"


def test_price_extraction(realtor_extractor, sample_html):
    soup = BeautifulSoup(sample_html, 'html.parser')
    data = realtor_extractor.extract(soup)
    assert data["price"] == "$500,000"
    assert data["price_bucket"] == "$300K - $600K"


def test_location_extraction(realtor_extractor, sample_html):
    soup = BeautifulSoup(sample_html, 'html.parser')
    data = realtor_extractor.extract(soup)
    assert "Portland" in data["location"]
    assert "ME" in data["location"]


def test_details_extraction(realtor_extractor, sample_html):
    soup = BeautifulSoup(sample_html, 'html.parser')
    data = realtor_extractor.extract(soup)
    assert "3 bed" in data.get("house_details", "")
    assert "2 bath" in data.get("house_details", "")
