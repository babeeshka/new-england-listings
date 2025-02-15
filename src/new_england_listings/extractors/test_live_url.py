#!/usr/bin/env python3
# test_live_url.py

from new_england_listings.extractors import FarmlandExtractor, RealtorExtractor, LandandFarmExtractor
from new_england_listings.scraper import Scraper
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_live_url(url: str):
    """Test scraping a live URL using the project's scraper."""
    try:
        # Create a scraper instance
        scraper = Scraper()
        
        # Scrape the URL
        logger.info(f"Scraping URL: {url}")
        result = scraper.scrape_listing(url)
        
        # Print results
        logger.info("\nExtracted Data:")
        for key, value in result.items():
            logger.info(f"{key}: {value}")
            
        return result
    
    except Exception as e:
        logger.error(f"Error processing URL: {str(e)}", exc_info=True)
        return None

if __name__ == "__main__":
    # You can modify this URL to test different listings
    test_url = input("Enter the URL to test: ")
    test_live_url(test_url)