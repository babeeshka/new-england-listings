# src/new_england_listings/utils/browser.py
import asyncio
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

def generate_mouse_tracks(start_x, start_y, end_x, end_y, points=10):
    """Generate natural-looking mouse movement tracks."""
    points = []
    for i in range(points):
        # Use bezier curve to create natural movement
        t = i / (points - 1)
        x = start_x + (end_x - start_x) * t + random.randint(-10, 10)
        y = start_y + (end_y - start_y) * t + random.randint(-10, 10)
        points.append((int(x), int(y)))
    return points

def get_stealth_driver() -> webdriver.Chrome:
    """Get a ChromeDriver instance with enhanced stealth for LandAndFarm."""
    options = Options()

    # Basic settings
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    # Additional stealth settings
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument("--disable-notifications")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")

    # Enhanced headers
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_argument("--disable-site-isolation-trials")

    # Random viewport size
    width = random.randint(1200, 1600)
    height = random.randint(800, 1000)
    options.add_argument(f"--window-size={width},{height}")

    # Random user agent from recent browser list
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
    ]
    user_agent = random.choice(user_agents)
    options.add_argument(f'user-agent={user_agent}')

    # Enhanced preferences
    prefs = {
        'profile.default_content_setting_values': {
            'notifications': 2,
            'images': 1,
            'javascript': 1,
            'cookies': 1,
            'plugins': 1,
            'popups': 2,
            'geolocation': 2,
            'auto_select_certificate': 2,
            'mouselock': 2,
            'mixed_script': 1,
            'media_stream': 2,
            'media_stream_mic': 2,
            'media_stream_camera': 2,
            'protocol_handlers': 2,
            'ppapi_broker': 2,
            'automatic_downloads': 2,
            'midi_sysex': 2,
            'push_messaging': 2,
            'ssl_cert_decisions': 2,
            'metro_switch_to_desktop': 2,
            'protected_media_identifier': 2,
            'app_banner': 2,
            'site_engagement': 2,
            'durable_storage': 2
        },
        'profile.managed_default_content_settings': {
            'images': 1,
            'javascript': 1
        }
    }
    options.add_experimental_option('prefs', prefs)
    options.add_experimental_option(
        'excludeSwitches', ['enable-automation', 'enable-logging'])
    options.add_experimental_option('useAutomationExtension', False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Set longer timeouts
    driver.set_page_load_timeout(90)
    driver.set_script_timeout(90)

    # Set CDP commands for additional stealth
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": user_agent,
        "platform": "Windows",
        "acceptLanguage": "en-US,en;q=0.9",
        "userAgentMetadata": {
            "brands": [
                {"brand": "Google Chrome", "version": "122"},
                {"brand": "Chromium", "version": "122"}
            ],
            "fullVersion": "122.0.0.0",
            "platform": "Windows",
            "platformVersion": "10.0.0",
            "architecture": "x86",
            "model": "",
            "mobile": False
        }
    })

    return driver

async def get_page_content_async(url: str, use_selenium: bool = False, max_retries: int = 3, timeout: int = 30) -> BeautifulSoup:
    """
    Asynchronous wrapper for get_page_content.
    Runs the synchronous function in a thread pool to make it compatible with async/await.
    
    Args:
        url: URL to fetch
        use_selenium: Whether to use Selenium for rendering JavaScript
        max_retries: Maximum number of retry attempts
        timeout: Request timeout in seconds
        
    Returns:
        BeautifulSoup object of the page content
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,  # Uses the default executor
        lambda: get_page_content(url, use_selenium, max_retries, timeout)
    )

def get_page_content(url: str, use_selenium: bool = False, max_retries: int = 3, timeout: int = 30) -> BeautifulSoup:
    """Get page content with enhanced stealth and retry logic."""
    logger.info(f"Starting page fetch for {url}")

    # Special handling for Zillow
    is_zillow = "zillow.com" in url.lower()
    if is_zillow:
        logger.info("Using enhanced Zillow-specific browser configuration")
        return get_zillow_content(url, timeout)

    retry_count = 0
    blocking_detected = False

    while retry_count < max_retries:
        try:
            if use_selenium:
                logger.info("Using Selenium for dynamic content...")
                # Use the driver manager instead of creating a new driver each time
                driver = driver_manager.get_driver()

                try:
                    # Initial delay
                    # Reduced delay when reusing driver
                    time.sleep(random.uniform(1, 2))

                    # Navigate with referrer
                    logger.info("Navigating to page...")
                    driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
                        'headers': {
                            'Referer': 'https://www.google.com/',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.9',
                            'Accept-Encoding': 'gzip, deflate, br',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                            'Sec-Fetch-Dest': 'document',
                            'Sec-Fetch-Mode': 'navigate',
                            'Sec-Fetch-Site': 'cross-site',
                            'Sec-Fetch-User': '?1',
                            'DNT': '1'
                        }
                    })

                    driver.get(url)
                    # Wait longer after initial load
                    time.sleep(random.uniform(2, 3))  # Reduced delay

                    # Check if we got a valid page
                    if "This site can't be reached" in driver.title:
                        logger.error("Got error page, retrying...")
                        retry_count += 1
                        time.sleep(random.uniform(5, 10) * retry_count)
                        continue

                    # Check for common blocking messages but don't fail immediately
                    page_source = driver.page_source.lower()
                    if any(text in page_source for text in ['captcha', 'security check', 'please verify', 'pardon our interruption']):
                        logger.warning(
                            "Detected possible blocking content, but continuing with extraction")
                        blocking_detected = True
                        # No return here, we'll continue with what we have

                    # Get page source
                    html = driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')

                    # For Realtor.com, try to extract location from URL even if blocked
                    if "realtor.com" in url and blocking_detected:
                        # Add a marker that can be detected by the extractor
                        meta_tag = soup.new_tag("meta")
                        meta_tag["name"] = "extraction-status"
                        meta_tag["content"] = "blocked-but-attempting"
                        if soup.head:
                            soup.head.append(meta_tag)
                        else:
                            head = soup.new_tag("head")
                            soup.insert(0, head)
                            soup.head.append(meta_tag)

                        # Try to extract from URL
                        parts = url.split('_')
                        if len(parts) >= 3:
                            location_meta = soup.new_tag("meta")
                            location_meta["name"] = "url-extracted-location"
                            location_meta["content"] = f"{parts[-3].replace('-', ' ').title()}, {parts[-2].upper()}"
                            soup.head.append(location_meta)

                    return soup

                except Exception as e:
                    logger.error(f"Error with Selenium: {str(e)}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise
                    continue

            else:
                # Regular requests with enhanced headers
                headers = {
                    'User-Agent': get_random_user_agent(),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'max-age=0',
                    'TE': 'Trailers',
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
            time.sleep(random.uniform(5, 10) * retry_count)

    raise Exception(f"Failed to fetch page after {max_retries} attempts")

def get_zillow_content(url: str, timeout: int = 60) -> BeautifulSoup:
    """Get Zillow content with enhanced anti-detection measures."""
    driver = None
    try:
        options = Options()

        # These settings help avoid detection
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Add realistic window size and user agent
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")

        # Use a very realistic user agent
        user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        options.add_argument(f'user-agent={user_agent}')

        # We need JS and images for Zillow to work correctly
        prefs = {
            'profile.default_content_setting_values': {
                'images': 1,
                'javascript': 1,
                'cookies': 1,
            }
        }
        options.add_experimental_option('prefs', prefs)

        # Zillow works better with visible browser for testing
        # Comment this for production use
        # options.add_argument('--headless=new')

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(timeout)

        # Set CDP commands for additional stealth
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": user_agent,
            "platform": "macOS",
            "acceptLanguage": "en-US,en;q=0.9",
        })

        # Important: Add special script to avoid detection
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            """
        })

        # Visit a normal site first, then go to Zillow
        driver.get("https://www.google.com")
        time.sleep(2)

        # Now navigate to the actual Zillow page
        logger.info(f"Navigating to Zillow page: {url}")
        driver.get(url)

        # Wait for critical elements to load
        logger.info("Waiting for page to fully load...")

        # Wait longer for Zillow's complex JS to execute
        time.sleep(5)

        # Try to find price element - this is key for Zillow pages
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-testid='price']"))
            )
            logger.info("Price element found - page loaded successfully")
        except:
            logger.warning("Price element not found - page may be incomplete")

        # Extract the page source
        html = driver.page_source

        # Check for blocking content
        if "captcha" in html.lower() or "security check" in html.lower():
            logger.warning(
                "Detected CAPTCHA or security check - Zillow is blocking the request")

            # Optionally, save a screenshot for debugging
            try:
                driver.save_screenshot("zillow_blocked.png")
                logger.info("Saved screenshot to zillow_blocked.png")
            except:
                pass

        # Return the soup object
        return BeautifulSoup(html, 'html.parser')

    except Exception as e:
        logger.error(f"Error getting Zillow content: {str(e)}")
        # If we have a driver but failed, try to get whatever HTML we have
        if driver:
            try:
                return BeautifulSoup(driver.page_source, 'html.parser')
            except:
                pass
        return BeautifulSoup("<html><body>Failed to load</body></html>", 'html.parser')

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def wait_for_load(driver: webdriver.Chrome, timeout: int = 90) -> bool:
    """Wait for page to load with enhanced checks."""
    logger.debug("Waiting for page load...")

    try:
        # Wait for initial page load
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script(
                'return document.readyState') == 'complete'
        )

        # Random delay
        time.sleep(random.uniform(2, 4))

        # Check for common elements
        selectors = [
            "body",
            ".property-details",
            ".listing-details",
            "#property-info",
            ".property-meta"
        ]

        found = False
        for selector in selectors:
            try:
                element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                found = True
                logger.debug(f"Found element: {selector}")
                break
            except TimeoutException:
                continue

        if not found:
            logger.warning("No key elements found after page load")
            return False

        # Additional random delay
        time.sleep(random.uniform(1, 2))

        # Scroll simulation
        scroll_height = driver.execute_script(
            "return document.body.scrollHeight")
        if scroll_height > 200:
            viewport_height = driver.execute_script(
                "return window.innerHeight")
            scroll_positions = list(
                range(0, scroll_height, min(500, viewport_height)))
            random.shuffle(scroll_positions)  # Randomize scroll order

            # Only scroll 3 random positions
            for position in scroll_positions[:3]:
                driver.execute_script(f"window.scrollTo(0, {position});")
                time.sleep(random.uniform(0.5, 1.5))

        return True

    except Exception as e:
        logger.error(f"Error during page load: {str(e)}")
        return False

def get_page_with_retry(url: str, max_retries: int = 3) -> Optional[str]:
    """Get page content with enhanced retry logic."""
    logger.debug(f"Attempting to fetch {url}")

    delays = [5, 10, 15]  # Progressive delays between retries

    for attempt in range(max_retries):
        try:
            driver = get_stealth_driver()
            logger.debug(f"Attempt {attempt + 1}: Loading page...")

            driver.get(url)
            if wait_for_load(driver):
                html = driver.page_source
                if "captcha" not in html.lower() and "security check" not in html.lower():
                    logger.debug("Successfully retrieved page content")
                    return html

            logger.warning(
                f"Attempt {attempt + 1} failed, waiting before retry")
            time.sleep(delays[attempt])

        except Exception as e:
            logger.error(f"Error during attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(delays[attempt])
        finally:
            try:
                driver.quit()
            except:
                pass

    return None

def get_random_user_agent() -> str:
    """Get a random user agent string."""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
    ]
    return random.choice(user_agents)

get_selenium_driver = get_stealth_driver

class DriverManager:
    """Singleton manager for Chrome WebDriver instances."""

    _instance = None
    _driver = None
    _last_used = 0
    _max_idle_time = 300  # 5 minutes

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DriverManager, cls).__new__(cls)
        return cls._instance

    def get_driver(self):
        """Get an existing driver or create a new one if needed."""
        current_time = time.time()

        # Check if we have an existing driver that hasn't timed out
        if self._driver is not None:
            # If driver is idle for too long, quit and create a new one
            if current_time - self._last_used > self._max_idle_time:
                logger.info("Driver idle timeout reached, creating new driver")
                self.quit_driver()
            else:
                logger.debug("Reusing existing WebDriver instance")
                self._last_used = current_time
                return self._driver

        # Create a new driver
        logger.info("Creating new WebDriver instance")
        self._driver = get_stealth_driver()
        self._last_used = current_time
        return self._driver

    def quit_driver(self):
        """Quit the current driver if it exists."""
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception as e:
                logger.warning(f"Error quitting driver: {str(e)}")
            finally:
                self._driver = None


# Create a singleton instance
driver_manager = DriverManager()

# When application is shutting down, make sure to quit the driver


def cleanup_driver():
    """Cleanup the WebDriver when application is shutting down."""
    driver_manager.quit_driver()
