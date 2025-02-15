# tests/test_extractors/test_farmland.py
import pytest
from new_england_listings.extractors import FarmlandExtractor
from bs4 import BeautifulSoup


@pytest.fixture
def farmland_extractor():
    return FarmlandExtractor("https://farmlink.mainefarmlandtrust.org/example")


@pytest.fixture
def sample_html():
    return """
    <html>
        <h1 class="entry-title">Beautiful Farm Property</h1>
        <div class="farm-details">
            <p>75 acres of prime farmland</p>
            <p>Located in Brunswick, ME</p>
            <p>Infrastructure includes: barn, greenhouse</p>
        </div>
        <div class="price">Contact for Price</div>
    </html>
    """


def test_listing_name_extraction(farmland_extractor, sample_html):
    soup = BeautifulSoup(sample_html, 'html.parser')
    data = farmland_extractor.extract(soup)
    assert data["listing_name"] == "Beautiful Farm Property"


def test_acreage_extraction(farmland_extractor, sample_html):
    soup = BeautifulSoup(sample_html, 'html.parser')
    data = farmland_extractor.extract(soup)
    assert data["acreage"] == "75.0 acres"
    assert data["acreage_bucket"] == "Very Large"


def test_location_extraction(farmland_extractor, sample_html):
    soup = BeautifulSoup(sample_html, 'html.parser')
    data = farmland_extractor.extract(soup)
    assert "Brunswick" in data["location"]
    assert "ME" in data["location"]


def test_farm_details_extraction(farmland_extractor, sample_html):
    soup = BeautifulSoup(sample_html, 'html.parser')
    data = farmland_extractor.extract(soup)
    assert "barn" in data.get("farm_details", "").lower()
    assert "greenhouse" in data.get("farm_details", "").lower()
