# src/new_england_listings/utils/browser_auth.py

from urllib.parse import quote
import requests
from typing import Dict, Any, Optional, Tuple
import re
import os
import json
import time
import logging
import platform
from pathlib import Path
from typing import Optional, Dict, Any
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Path for storing cookies
APP_DIR = Path(os.path.expanduser("~/.new_england_listings"))
COOKIES_FILE = APP_DIR / "zillow_cookies.json"


def setup_auth_directory():
    """Create directory for storing authentication data if it doesn't exist."""
    if not APP_DIR.exists():
        APP_DIR.mkdir(parents=True)
        logger.info(f"Created application directory at {APP_DIR}")

def get_zillow_with_user_consent(url: str, non_interactive: bool = False) -> Optional[BeautifulSoup]:
    """
    Get Zillow content with user consent to solve CAPTCHAs if needed.
    
    This approach is legally compliant because:
    1. It requires explicit user consent and action
    2. The user solves any CAPTCHAs manually
    3. It's intended for personal, low-volume use
    
    Args:
        url: The Zillow URL to access
        non_interactive: If True, will only use existing cookies and won't prompt user
        
    Returns:
        BeautifulSoup object of the page or None if access not possible
    """
    setup_auth_directory()

    options = Options()
    if non_interactive:
        # Only run headless if we're not expecting user interaction
        options.add_argument('--headless=new')

    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--start-maximized')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # Load cookies if available
        cookies_loaded = False
        if COOKIES_FILE.exists():
            try:
                # First visit zillow.com to set the domain
                driver.get("https://www.zillow.com")
                time.sleep(2)

                # Load saved cookies
                with open(COOKIES_FILE, 'r') as f:
                    cookies = json.load(f)
                    for cookie in cookies:
                        # Handle cookie expiry
                        if 'expiry' in cookie:
                            cookie['expiry'] = int(cookie['expiry'])
                        try:
                            driver.add_cookie(cookie)
                        except Exception as e:
                            logger.debug(f"Error adding cookie: {e}")

                cookies_loaded = True
                logger.info("Loaded saved authentication cookies")
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")

        # Navigate to the target URL
        logger.info(f"Navigating to {url}")
        driver.get(url)
        time.sleep(3)  # Let the page load

        # Check if we're blocked or need CAPTCHA
        page_source = driver.page_source.lower()
        captcha_indicators = ["captcha", "press and hold",
                              "security check", "please verify"]
        need_captcha = any(
            indicator in page_source for indicator in captcha_indicators)

        if need_captcha and not non_interactive:
            # We need user interaction to solve the CAPTCHA
            logger.info("CAPTCHA detected - waiting for user to solve")

            # Prepare user instructions
            if platform.system() == "Darwin":  # macOS
                os.system(
                    "osascript -e 'display notification \"Please solve the CAPTCHA in the browser window\" with title \"Action Required\"'")

            print("\n" + "="*70)
            print("⚠️  CAPTCHA DETECTED - USER ACTION REQUIRED")
            print("="*70)
            print("\n1. Please solve the CAPTCHA in the browser window that opened")
            print("2. Browse around if needed to establish a valid session")
            print("3. Return to the specific property page")
            print("4. Press Enter here when you're viewing the property details\n")

            input("Press Enter when you're viewing the property details...\n")

            # Now we need to get the current URL, which may have changed
            current_url = driver.current_url
            if "homedetails" not in current_url:
                print(
                    "\n⚠️  Warning: You don't appear to be on a property details page.")
                print("    Current URL:", current_url)
                proceed = input("Continue anyway? (y/n): ").lower() == 'y'
                if not proceed:
                    return None

            # Save the new cookies for future use
            cookies = driver.get_cookies()
            with open(COOKIES_FILE, 'w') as f:
                json.dump(cookies, f)
            logger.info("Saved new authentication cookies")

            # Get the new page source
            page_source = driver.page_source

        elif need_captcha and non_interactive:
            logger.warning(
                "CAPTCHA detected but running in non-interactive mode - cannot proceed")
            return None

        # Return BeautifulSoup of the final page
        return BeautifulSoup(page_source, 'html.parser')

    except Exception as e:
        logger.error(f"Error in authenticated browser session: {e}")
        return None

    finally:
        if driver:
            driver.quit()