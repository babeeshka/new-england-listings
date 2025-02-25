# src/new_england_listings/main.py
from typing import Dict, Any
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import logging
import random
import time
from .extractors.landandfarm import LandAndFarmExtractor
from .extractors.realtor import RealtorExtractor
from .extractors.farmland import FarmlandExtractor
from .extractors.farmlink import FarmLinkExtractor
from .extractors.landsearch import LandSearchExtractor
from .utils.browser import get_page_content
from .utils.notion.client import create_notion_entry

logger = logging.getLogger(__name__)


def get_extractor(url: str):
    """Get the appropriate extractor for the URL."""
    domain = urlparse(url).netloc.lower()

    logger.debug(f"Getting extractor for domain: {domain}")

    if "landsearch.com" in domain:
        return LandSearchExtractor(url)
    elif "landandfarm.com" in domain:
        return LandAndFarmExtractor(url)
    elif "farmlink.mainefarmlandtrust.org" in domain:
        return FarmLinkExtractor(url)
    elif "realtor.com" in domain:
        return RealtorExtractor(url)
    elif any(x in domain for x in ["mainefarmlandtrust.org", "newenglandfarmlandfinder.org"]):
        return FarmlandExtractor(url)
    else:
        raise ValueError(f"No extractor available for domain: {domain}")

def needs_selenium(url: str) -> bool:
    """Determine if a URL needs Selenium for proper extraction."""
    selenium_domains = [
        "realtor.com",
        "newenglandfarmlandfinder.org",
        "landsearch.com",
        "landandfarm.com",
        "zillow.com",
        "farmlink.mainefarmlandtrust.org"
    ]
    return any(domain in url.lower() for domain in selenium_domains)

async def process_listing(url: str, use_notion: bool = True, max_retries: int = 3) -> Dict[str, Any]:
    """Process a single listing URL with retries."""
    logger.info(f"Processing listing: {url}")

    # Special case for Realtor.com
    if "realtor.com" in url:
        try:
            # Get the extractor directly
            extractor = RealtorExtractor(url)

            # Try to get content but don't fail on blocking
            try:
                logger.info("Using Selenium for dynamic content")
                soup = get_page_content(url, use_selenium=True)

                # Mark page as blocked if needed (for debugging purposes)
                text = soup.get_text().lower()
                if any(x in text for x in ['captcha', 'pardon our interruption', 'please verify']):
                    logger.warning(
                        "Detected blocking content but continuing with extraction")
                    # Add a marker to the soup
                    meta_tag = soup.new_tag("meta")
                    meta_tag["name"] = "extraction-status"
                    meta_tag["content"] = "blocked-but-attempting"
                    if not soup.head:
                        head_tag = soup.new_tag("head")
                        soup.insert(0, head_tag)
                    soup.head.append(meta_tag)
            except Exception as e:
                # If we can't get content, create a minimal soup
                logger.warning(f"Error getting page content: {str(e)}")
                soup = BeautifulSoup(
                    "<html><head></head><body></body></html>", 'html.parser')
                meta_tag = soup.new_tag("meta")
                meta_tag["name"] = "extraction-status"
                meta_tag["content"] = "blocked-but-attempting"
                soup.head.append(meta_tag)

            # Extract data regardless of blocking
            logger.info("Extracting data...")
            data = extractor.extract(soup)

            # Create Notion entry if requested
            if use_notion:
                logger.info("Creating Notion entry...")
                create_notion_entry(data)
                logger.info("Notion entry created successfully")

            return data
        except Exception as e:
            logger.error(f"Error processing Realtor.com listing: {str(e)}")
            raise

    # Normal flow for non-Realtor sites
    retry_count = 0
    while retry_count < max_retries:
        try:
            # Get the appropriate extractor
            extractor = get_extractor(url)
            if not extractor:
                raise ValueError(f"No extractor available for URL: {url}")

            logger.info(f"Using extractor: {extractor.__class__.__name__}")

            # Get the page content
            logger.info("Fetching page content...")
            use_selenium = needs_selenium(url)
            if use_selenium:
                logger.info("Using Selenium for dynamic content")

            # Add delay between retries
            if retry_count > 0:
                delay = (2 ** retry_count) + \
                    random.uniform(1, 5)  # Exponential backoff
                logger.info(
                    f"Retry {retry_count + 1}/{max_retries}, waiting {delay:.1f}s")
                time.sleep(delay)

            soup = get_page_content(url, use_selenium=use_selenium)

            # Check for blocking content
            text = soup.get_text().lower()
            if any(x in text for x in ['captcha', 'pardon our interruption', 'please verify']):
                raise ValueError("Detected blocking content")

            # Extract the data
            logger.info("Extracting data...")
            data = extractor.extract(soup)

            # Create Notion entry if requested
            if use_notion:
                logger.info("Creating Notion entry...")
                create_notion_entry(data)
                logger.info("Notion entry created successfully")

            return data

        except Exception as e:
            retry_count += 1
            if retry_count == max_retries:
                logger.error(f"Error processing listing: {str(e)}")
                raise
            logger.warning(f"Attempt {retry_count} failed: {str(e)}")
            continue

    raise Exception(f"Failed to process listing after {max_retries} attempts")

if __name__ == "__main__":
    import sys
    import json

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Get URL from user
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Enter listing URL: ")

    try:
        # Process the listing
        data = process_listing(url)

        # Print results
        print("\nExtracted Data:")
        print(json.dumps(data, indent=2))
    except Exception as e:
        logger.error(f"Error processing listing: {str(e)}")
        sys.exit(1)
