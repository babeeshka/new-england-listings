# tests/test_utils/test_browser.py
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException
from new_england_listings.utils.browser import (
    get_page_content, needs_selenium, get_stealth_driver, get_random_user_agent
)


@pytest.fixture
def mock_response():
    """Mock requests.Response object."""
    mock = MagicMock()
    mock.text = "<html><body><h1>Test Page</h1></body></html>"
    mock.raise_for_status = MagicMock()
    return mock


@pytest.fixture
def mock_driver():
    """Mock Selenium WebDriver."""
    mock = MagicMock()
    mock.page_source = "<html><body><h1>Test Page Selenium</h1></body></html>"
    return mock


class TestBrowserUtils:

    def test_get_random_user_agent(self):
        """Test that get_random_user_agent returns a non-empty string."""
        agent = get_random_user_agent()
        assert isinstance(agent, str)
        assert len(agent) > 0
        assert "Mozilla" in agent  # Most user agents contain Mozilla

    def test_needs_selenium(self):
        """Test the determination of when Selenium is needed."""
        # Test URLs that should use Selenium
        assert needs_selenium("https://www.realtor.com/example") is True
        assert needs_selenium("https://zillow.com/homes/for_sale") is True
        assert needs_selenium("https://www.landsearch.com/properties") is True

        # Test URLs that don't need Selenium
        assert needs_selenium("https://example.com") is False
        assert needs_selenium("https://google.com") is False

    @patch('requests.get')
    def test_get_page_content_requests(self, mock_get, mock_response):
        """Test getting page content with requests."""
        mock_get.return_value = mock_response

        soup = get_page_content("https://example.com", use_selenium=False)

        # Verify requests.get was called
        mock_get.assert_called_once()

        # Verify BS4 object was returned with expected content
        assert isinstance(soup, BeautifulSoup)
        assert "Test Page" in str(soup)

    @patch('new_england_listings.utils.browser.get_stealth_driver')
    def test_get_page_content_selenium(self, mock_stealth_driver, mock_driver):
        """Test getting page content with Selenium."""
        mock_stealth_driver.return_value = mock_driver

        soup = get_page_content(
            "https://realtor.com/example", use_selenium=True)

        # Verify driver was created and used
        mock_stealth_driver.assert_called_once()
        mock_driver.get.assert_called_once_with("https://realtor.com/example")

        # Verify BS4 object was returned with expected content
        assert isinstance(soup, BeautifulSoup)
        assert "Test Page Selenium" in str(soup)

    @patch('new_england_listings.utils.browser.get_stealth_driver')
    def test_selenium_timeout_retry(self, mock_stealth_driver, mock_driver):
        """Test retry mechanism when Selenium times out."""
        # Set up driver to fail on first attempt but succeed on second
        mock_driver.get.side_effect = [TimeoutException(), None]
        mock_stealth_driver.return_value = mock_driver

        # Should succeed with retry
        soup = get_page_content(
            "https://realtor.com/example", use_selenium=True, max_retries=2)

        # Verify driver.get was called twice
        assert mock_driver.get.call_count == 2

        # Verify BS4 object was returned
        assert isinstance(soup, BeautifulSoup)

    @patch('new_england_listings.utils.browser.get_stealth_driver')
    def test_retry_exhaustion(self, mock_stealth_driver, mock_driver):
        """Test exception when retries are exhausted."""
        # Set up driver to always fail
        mock_driver.get.side_effect = TimeoutException("Timeout")
        mock_stealth_driver.return_value = mock_driver

        # Should raise exception after retries exhausted
        with pytest.raises(Exception):
            get_page_content("https://realtor.com/example",
                             use_selenium=True, max_retries=2)

        # Verify driver.get was called exactly twice (initial + 1 retry)
        assert mock_driver.get.call_count == 2
