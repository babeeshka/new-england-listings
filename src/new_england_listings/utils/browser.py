# src/new_england_listings/utils/browser.py
from typing import Optional, Dict
from bs4 import BeautifulSoup
import requests
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import time

logger = logging.getLogger(__name__)

# Default headers for requests
HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "DNT": "1"
}


def get_selenium_driver(use_proxy: bool = False, proxy_url: Optional[str] = None) -> webdriver.Chrome:
    """Configure and return a Selenium WebDriver instance with anti-detection measures."""
    try:
        options = Options()
        options.add_argument("--headless=new")  # Updated headless mode
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f'user-agent={HEADERS["User-Agent"]}')

        # Avoid detection
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        if use_proxy and proxy_url:
            options.add_argument(f'--proxy-server={proxy_url}')

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        # Modify navigator.webdriver flag
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": HEADERS["User-Agent"]
        })
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        return driver
    except Exception as e:
        logger.error(f"Failed to initialize Selenium driver: {str(e)}")
        raise


def get_page_content(url: str, use_selenium: bool = False, max_retries: int = 3, timeout: int = 30) -> BeautifulSoup:
    """Get page content using either requests or Selenium."""
    logger = logging.getLogger(__name__)

    if "realtor.com" in url:
        use_selenium = True

    logger.info(f"Starting page fetch for {url}")
    logger.info(f"Using {'Selenium' if use_selenium else 'requests'}")

    retry_count = 0
    while retry_count < max_retries:
        try:
            if use_selenium:
                try:
                    logger.info("Setting up Selenium...")
                    driver = get_selenium_driver()
                    driver.set_page_load_timeout(timeout)
                    driver.set_script_timeout(timeout)

                    logger.info("Navigating to page...")
                    driver.get(url)

                    # Wait for any content to load
                    logger.info("Waiting for page content...")
                    wait = WebDriverWait(driver, timeout)
                    try:
                        # Wait for basic page elements
                        wait.until(EC.presence_of_element_located(
                            (By.TAG_NAME, "body")))
                        wait.until(EC.presence_of_element_located(
                            (By.TAG_NAME, "h1")))
                        logger.info("Basic page elements found")
                    except TimeoutException:
                        logger.warning(
                            "Timeout waiting for basic page elements")

                    # Get page source
                    html = driver.page_source
                    content_length = len(html)
                    logger.info(
                        f"Retrieved page content (length: {content_length})")

                    if content_length < 1000:
                        logger.warning("Page content seems too small")

                    return BeautifulSoup(html, 'html.parser')

                except Exception as e:
                    logger.error(f"Selenium error: {str(e)}", exc_info=True)
                    raise
                finally:
                    if 'driver' in locals():
                        logger.info("Closing Selenium driver")
                        driver.quit()
            else:
                logger.info("Using requests to fetch page")
                response = requests.get(url, timeout=timeout)
                response.raise_for_status()
                return BeautifulSoup(response.text, 'html.parser')

        except Exception as e:
            retry_count += 1
            logger.error(
                f"Attempt {retry_count}/{max_retries} failed: {str(e)}")
            if retry_count == max_retries:
                raise
            time.sleep(2 * retry_count)

    raise Exception(f"Failed to fetch page after {max_retries} attempts")

def verify_page_content(soup: BeautifulSoup) -> bool:
    """Verify that the page content was properly loaded."""
    content_checks = [
        soup.find("div", class_="field-group--columns"),
        soup.find("h1", class_="page-title"),
        soup.find(string=lambda x: x and "Total number of acres" in str(x)),
        soup.find("article", class_="node--type-farmland")
    ]

    return any(content_checks)
