"""
Shared pytest fixtures for New England Listings tests.
"""
import os
import json
import pytest
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from unittest.mock import MagicMock

# Define test data directory
TEST_DATA_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def test_data_dir():
    """Get the test data directory path."""
    return TEST_DATA_DIR


@pytest.fixture
def html_samples_dir(test_data_dir):
    """Get the HTML samples directory path."""
    html_dir = test_data_dir / "html_samples"
    html_dir.mkdir(exist_ok=True, parents=True)
    return html_dir


@pytest.fixture
def responses_dir(test_data_dir):
    """Get the recorded responses directory path."""
    responses_dir = test_data_dir / "responses"
    responses_dir.mkdir(exist_ok=True, parents=True)
    return responses_dir


@pytest.fixture
def sample_html(html_samples_dir):
    """
    Load HTML sample files for different platforms.
    
    Returns:
        dict: Dictionary mapping platform names to BeautifulSoup objects
    """
    samples = {}

    # Find and load all HTML files
    for html_file in html_samples_dir.glob("*.html"):
        platform_name = html_file.stem
        with open(html_file, "r", encoding="utf-8") as f:
            html_content = f.read()
            samples[platform_name] = BeautifulSoup(html_content, "html.parser")

    return samples


@pytest.fixture
def mock_selenium_driver():
    """Mock Selenium WebDriver to avoid browser dependencies in tests."""
    mock_driver = MagicMock()

    # Set up common method returns
    mock_driver.page_source = "<html><body>Mock Selenium Content</body></html>"
    mock_driver.get.return_value = None
    mock_driver.find_element.return_value = MagicMock()
    mock_driver.find_elements.return_value = []

    return mock_driver


@pytest.fixture
def mock_notion_client():
    """Mock Notion client for testing Notion integration."""
    mock_client = MagicMock()

    # Set up responses for common operations
    mock_client.databases.query.return_value = {"results": []}
    mock_client.pages.create.return_value = {"id": "test-page-id"}
    mock_client.pages.update.return_value = {"id": "test-page-id"}

    return mock_client


@pytest.fixture
def sample_property_data():
    """Provide sample property data for testing."""
    return {
        "url": "https://www.realtor.com/test-property",
        "platform": "Realtor.com",
        "listing_name": "Beautiful Farmhouse in Maine",
        "location": "Portland, ME",
        "price": "$450,000",
        "price_bucket": "$300K - $600K",
        "property_type": "Farm",
        "acreage": "5.2 acres",
        "acreage_bucket": "Medium (5-20 acres)",
        "listing_date": "2023-10-15",
    }


@pytest.fixture
def location_test_data():
    """Provide test data for location services."""
    return {
        "simple_location": "Portland, ME",
        "complex_location": "123 Main St, Augusta, ME 04330",
        "county_location": "Oxford County, ME",
        "unknown_location": "Location Unknown",
        "coordinates": {
            "Portland, ME": (43.6591, -70.2568),
            "Augusta, ME": (44.3107, -69.7795),
            "Bangor, ME": (44.8016, -68.7712)
        }
    }


@pytest.fixture
def mock_requests(monkeypatch):
    """Mock requests module to avoid real HTTP requests in tests."""
    class MockResponse:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code
            self.content = text.encode('utf-8')

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP Error: {self.status_code}")

    class MockRequests:
        @staticmethod
        def get(url, *args, **kwargs):
            # Determine response based on URL
            domain = urlparse(url).netloc

            if "realtor.com" in domain:
                with open(TEST_DATA_DIR / "html_samples" / "realtor.html", "r") as f:
                    return MockResponse(f.read())
            elif "zillow.com" in domain:
                with open(TEST_DATA_DIR / "html_samples" / "zillow.html", "r") as f:
                    return MockResponse(f.read())
            elif "landandfarm.com" in domain:
                with open(TEST_DATA_DIR / "html_samples" / "landandfarm.html", "r") as f:
                    return MockResponse(f.read())
            else:
                return MockResponse("<html><body>Generic mock response</body></html>")

    monkeypatch.setattr("requests.get", MockRequests.get)
    return MockRequests


@pytest.fixture
def mock_geolocation():
    """Mock geolocation services."""
    class MockGeocoder:
        def geocode(self, query, **kwargs):
            # Return fixed coordinates for test locations
            test_coordinates = {
                "Portland, ME": (43.6591, -70.2568),
                "Augusta, ME": (44.3107, -69.7795),
                "Bangor, ME": (44.8016, -68.7712),
                "Lewiston, ME": (44.1003, -70.2147),
                "Oxford County, ME": (44.3662, -70.6715),
            }

            # Parse the location from query
            location_key = None
            for key in test_coordinates:
                if key.lower() in query.lower():
                    location_key = key
                    break

            if location_key:
                class MockLocation:
                    latitude = test_coordinates[location_key][0]
                    longitude = test_coordinates[location_key][1]
                    address = location_key
                return MockLocation()

            return None  # Location not found

    return MockGeocoder()


@pytest.fixture
def mock_datetime(monkeypatch):
    """Mock datetime to provide consistent timestamps in tests."""
    class MockDatetime:
        @classmethod
        def now(cls):
            # Return a fixed datetime for testing
            import datetime
            return datetime.datetime(2023, 10, 15, 12, 0, 0)

        @classmethod
        def strptime(cls, date_string, format):
            # Pass through to real strptime
            import datetime
            return datetime.datetime.strptime(date_string, format)

        @classmethod
        def strftime(cls, format):
            # Return a fixed formatted date string
            return "2023-10-15"

    monkeypatch.setattr("datetime.datetime", MockDatetime)
    return MockDatetime
