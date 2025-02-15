# tests/test_extractors/test_landandfarm.py
import pytest
from new_england_listings.extractors import LandAndFarmExtractor
from bs4 import BeautifulSoup


def test_landandfarm_price_extraction():
    html = """
    <div class="price">$499,000</div>
    """
    soup = BeautifulSoup(html, 'html.parser')
    extractor = LandAndFarmExtractor("test_url")
    data = extractor.extract(soup)
    assert data["price"] == "$499,000"
    assert data["price_bucket"] == "$300K - $600K"


def test_landandfarm_acreage_extraction():
    html = """
    <div class="property-details">10.5 acres</div>
    """
    soup = BeautifulSoup(html, 'html.parser')
    extractor = LandAndFarmExtractor("test_url")
    data = extractor.extract(soup)
    assert data["acreage"] == "10.5 acres"
    assert data["acreage_bucket"] == "Medium"
