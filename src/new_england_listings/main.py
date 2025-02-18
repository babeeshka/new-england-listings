# src/new_england_listings/main.py
from typing import Dict, Any
from urllib.parse import urlparse
import logging
from .extractors.landandfarm import LandAndFarmExtractor
from .extractors.realtor import RealtorExtractor
from .extractors.farmland import FarmlandExtractor
from .extractors.farmlink import FarmLinkExtractor
from .utils.browser import get_page_content
from .utils.notion.client import create_notion_entry  # Fixed import path

logger = logging.getLogger(__name__)


# In main.py
def get_extractor(url: str):
    """Get the appropriate extractor for the URL."""
    domain = urlparse(url).netloc.lower()

    logger.debug(f"Getting extractor for domain: {domain}")

    # Check for FarmLink first
    if "farmlink.mainefarmlandtrust.org" in domain:
        return FarmLinkExtractor(url)
    elif "landandfarm.com" in domain:
        return LandAndFarmExtractor(url)
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
        "zillow.com",
        "farmlink.mainefarmlandtrust.org"
    ]
    return any(domain in url.lower() for domain in selenium_domains)



def process_listing(url: str, use_notion: bool = True) -> Dict[str, Any]:
    """Process a single listing URL."""
    logger.info(f"Processing listing: {url}")

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

        soup = get_page_content(url, use_selenium=use_selenium)

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
        logger.error(f"Error processing listing: {str(e)}", exc_info=True)
        raise


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
