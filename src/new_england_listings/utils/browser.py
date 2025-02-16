# src/new_england_listings/utils/browser.py
from typing import Optional, Dict
from bs4 import BeautifulSoup
import requests
import logging
import random
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


def generate_windows_properties():
    """Generate random but realistic window properties."""
    return {
        "width": random.randint(1200, 1600),
        "height": random.randint(800, 1000),
        "deviceScaleFactor": random.choice([1, 1.25, 1.5, 2]),
        "mobile": False
    }

# src/new_england_listings/utils/browser.py
# (previous imports remain the same)


def get_stealth_driver() -> webdriver.Chrome:
    """Get a ChromeDriver instance configured for maximum stealth."""
    options = Options()

    # Basic settings
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')

    # Random window size
    window_props = generate_windows_properties()
    options.add_argument(
        f'--window-size={window_props["width"]},{window_props["height"]}')

    # Enhanced stealth settings
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--disable-web-security')

    # Privacy settings
    options.add_argument('--enable-privacy')
    options.add_argument('--disable-site-isolation-trials')

    # Random user agent
    user_agents = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    user_agent = random.choice(user_agents)
    options.add_argument(f'user-agent={user_agent}')

    # Additional experimental options
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    # Add preferences
    prefs = {
        'profile.default_content_setting_values': {
            'notifications': 2,
            'geolocation': 2
        },
        'profile.managed_default_content_settings': {
            'images': 1,
            'javascript': 1
        },
        'profile.managed_default_content_setting_values': {
            'plugins': 1
        }
    }
    options.add_experimental_option('prefs', prefs)

    # Create driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Set CDP commands for additional stealth
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": user_agent,
        "platform": "Windows",
        "acceptLanguage": "en-US,en;q=0.9"
    })

    # Simpler stealth script that won't conflict with Chrome properties
    stealth_js = """
    // Overwrite the navigator.webdriver flag
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
    
    // Add language preferences
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en']
    });
    """
    driver.execute_script(stealth_js)

    return driver


def get_page_content(url: str, use_selenium: bool = False, max_retries: int = 3, timeout: int = 30) -> BeautifulSoup:
    """Get page content with enhanced stealth measures."""
    logger.info(f"Starting page fetch for {url}")

    retry_count = 0
    while retry_count < max_retries:
        try:
            if use_selenium:
                logger.info("Using stealth Selenium...")
                driver = get_stealth_driver()

                try:
                    # Random initial delay
                    time.sleep(random.uniform(2, 4))

                    # Set page load timeout
                    driver.set_page_load_timeout(timeout)
                    driver.set_script_timeout(timeout)

                    # Load the page
                    logger.info("Navigating to page...")
                    driver.get(url)

                    # Initial wait
                    time.sleep(random.uniform(1, 2))

                    # Simulate human-like scrolling
                    scroll_height = driver.execute_script(
                        "return document.body.scrollHeight")
                    for i in range(3):
                        scroll_y = random.randint(100, scroll_height // 3)
                        driver.execute_script(
                            f"window.scrollBy(0, {scroll_y})")
                        time.sleep(random.uniform(0.5, 1))

                    # Wait for key elements with extended timeout
                    logger.info("Waiting for page content...")
                    wait = WebDriverWait(driver, timeout)

                    # Try multiple selectors for key elements
                    selectors = [
                        "[data-testid='property-meta']",
                        "[data-testid='list-price']",
                        "[data-testid='address']",
                        ".property-meta",
                        ".price",
                        ".address"
                    ]

                    found_elements = 0
                    for selector in selectors:
                        try:
                            wait.until(EC.presence_of_element_located(
                                (By.CSS_SELECTOR, selector)))
                            found_elements += 1
                            time.sleep(random.uniform(0.2, 0.5))
                        except TimeoutException:
                            continue

                    if found_elements == 0:
                        logger.warning("No key elements found on page")

                    # Get page source
                    html = driver.page_source
                    content_length = len(html)

                    # Check for blocking
                    if "pardon our interruption" in html.lower():
                        logger.warning("Detected blocking page, retrying...")
                        retry_count += 1
                        time.sleep(random.uniform(3, 6) * retry_count)
                        continue

                    logger.info(
                        f"Retrieved page content (length: {content_length})")
                    return BeautifulSoup(html, 'html.parser')

                finally:
                    driver.quit()
            else:
                # Regular requests approach
                headers = {
                    'User-Agent': random.choice(user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'DNT': '1'
                }

                response = requests.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()
                return BeautifulSoup(response.text, 'html.parser')

        except Exception as e:
            retry_count += 1
            logger.error(
                f"Attempt {retry_count}/{max_retries} failed: {str(e)}")
            if retry_count == max_retries:
                raise
            time.sleep(random.uniform(3, 6) * retry_count)

    raise Exception(f"Failed to fetch page after {max_retries} attempts")


# Create alias for backward compatibility
get_selenium_driver = get_stealth_driver
