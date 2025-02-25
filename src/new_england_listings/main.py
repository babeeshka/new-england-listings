"""
Main execution module for the New England Listings project.
Handles orchestration of extraction process and output to Notion.
"""

import asyncio
import json
import logging
import random
import sys
import time
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import traceback

from .extractors import get_extractor_for_url
from .utils.browser import get_page_content
from .utils.notion.client import create_notion_entry
from .utils.rate_limiting import rate_limiter, RateLimitExceeded

logger = logging.getLogger(__name__)

# Set up global configuration
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30
RETRY_DELAY_FACTOR = 2  # Base for exponential backoff


def needs_selenium(url: str) -> bool:
    """
    Determine if a URL needs Selenium for proper extraction.
    
    Args:
        url: Listing URL
    
    Returns:
        Boolean indicating whether Selenium is needed
    """
    selenium_domains = [
        "realtor.com",
        "newenglandfarmlandfinder.org",
        "landsearch.com",
        "landandfarm.com",
        "zillow.com",
        "farmlink.mainefarmlandtrust.org"
    ]
    return any(domain in url.lower() for domain in selenium_domains)


async def process_listing(url: str, use_notion: bool = True, max_retries: int = MAX_RETRIES,
                          timeout: int = DEFAULT_TIMEOUT, respect_rate_limits: bool = True) -> Dict[str, Any]:
    """
    Process a single listing URL with retries.
    
    Args:
        url: Listing URL
        use_notion: Whether to create a Notion entry for the result
        max_retries: Maximum number of retry attempts
        timeout: Request timeout in seconds
        respect_rate_limits: Whether to respect rate limits
    
    Returns:
        Dictionary with extracted listing data
    
    Raises:
        Exception: If processing fails after all retries
    """
    logger.info(f"Processing listing: {url}")

    # Special case for Realtor.com (known for blocking scrapers)
    if "realtor.com" in url:
        try:
            # Get the extractor directly
            extractor = get_extractor_for_url(url)
            if not extractor:
                raise ValueError(f"No extractor available for URL: {url}")

            # Wait for rate limits if needed
            if respect_rate_limits:
                await rate_limiter.async_wait_if_needed(url)

            # Try to get content but don't fail on blocking
            try:
                logger.info("Using Selenium for dynamic content")
                soup = await get_page_content(url, use_selenium=True, timeout=timeout)

                # Record that a request was made for rate limiting purposes
                if respect_rate_limits:
                    rate_limiter.record_request(url)

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
                await create_notion_entry(data)
                logger.info("Notion entry created successfully")

            return data
        except Exception as e:
            logger.error(f"Error processing Realtor.com listing: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    # Normal flow for non-Realtor sites
    retry_count = 0
    last_error = None

    while retry_count < max_retries:
        try:
            # Get the appropriate extractor
            extractor = get_extractor_for_url(url)
            if not extractor:
                raise ValueError(f"No extractor available for URL: {url}")

            logger.info(f"Using extractor: {extractor.__class__.__name__}")

            # Get the page content
            logger.info("Fetching page content...")
            use_selenium = needs_selenium(url)
            if use_selenium:
                logger.info("Using Selenium for dynamic content")

            # Add delay between retries with exponential backoff
            if retry_count > 0:
                delay = (RETRY_DELAY_FACTOR ** retry_count) + \
                    random.uniform(1, 5)
                logger.info(
                    f"Retry {retry_count + 1}/{max_retries}, waiting {delay:.1f}s")
                await asyncio.sleep(delay)

            # Wait for rate limits if needed
            if respect_rate_limits:
                await rate_limiter.async_wait_if_needed(url)

            soup = await get_page_content(url, use_selenium=use_selenium, timeout=timeout)

            # Record that a request was made for rate limiting purposes
            if respect_rate_limits:
                rate_limiter.record_request(url)

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
                await create_notion_entry(data)
                logger.info("Notion entry created successfully")

            # Log success with key data points
            logger.info(f"Successfully processed {url}")
            logger.info(f"Data: {json.dumps({
                'listing_name': data.get('listing_name'),
                'platform': data.get('platform'),
                'location': data.get('location'),
                'price': data.get('price'),
                'acreage': data.get('acreage'),
                'property_type': data.get('property_type')
            }, indent=2)}")

            return data

        except RateLimitExceeded as rle:
            # Special handling for rate limit exceeded - always retry
            retry_count += 1
            last_error = rle
            logger.warning(
                f"Rate limit exceeded on attempt {retry_count}: {str(rle)}")

            # Calculate wait time with jitter
            wait_time = 60 + random.uniform(1, 30)  # At least 60s plus jitter
            logger.info(f"Waiting {wait_time:.1f}s before retry...")
            await asyncio.sleep(wait_time)
            continue

        except Exception as e:
            retry_count += 1
            last_error = e

            if retry_count < max_retries:
                logger.warning(f"Attempt {retry_count} failed: {str(e)}")
                continue
            else:
                logger.error(
                    f"Error processing listing after {max_retries} attempts: {str(e)}")
                logger.error(traceback.format_exc())
                raise Exception(
                    f"Failed to process listing after {max_retries} attempts: {str(e)}") from e

    # This should never be reached due to the raise in the loop, but just in case
    raise Exception(f"Failed to process listing: {last_error}")


async def process_listings(urls: List[str], use_notion: bool = True,
                           max_retries: int = MAX_RETRIES,
                           concurrency: int = 3,  # Reduced concurrency to avoid rate limiting
                           respect_rate_limits: bool = True) -> List[Dict[str, Any]]:
    """
    Process multiple listings concurrently.
    
    Args:
        urls: List of listing URLs
        use_notion: Whether to create Notion entries
        max_retries: Maximum number of retry attempts per URL
        concurrency: Maximum number of concurrent requests
        respect_rate_limits: Whether to respect rate limits
    
    Returns:
        List of dictionaries with extracted listing data
    """
    logger.info(
        f"Processing {len(urls)} listings with concurrency {concurrency}")

    # Process in batches to control concurrency
    results = []
    semaphore = asyncio.Semaphore(concurrency)

    async def process_with_semaphore(url):
        async with semaphore:
            try:
                return await process_listing(
                    url,
                    use_notion=use_notion,
                    max_retries=max_retries,
                    respect_rate_limits=respect_rate_limits
                )
            except Exception as e:
                logger.error(f"Failed to process {url}: {str(e)}")
                return {"url": url, "error": str(e), "extraction_status": "failed"}

    # Create tasks for all URLs
    tasks = [process_with_semaphore(url) for url in urls]

    # Process all tasks and collect results
    for future in asyncio.as_completed(tasks):
        try:
            result = await future
            results.append(result)
        except Exception as e:
            logger.error(f"Unexpected error in processing task: {str(e)}")

    return results


def setup_logging(level=logging.INFO, log_file=None):
    """Set up logging configuration."""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Configure root logger
    logging.basicConfig(level=level, format=log_format)

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(file_handler)

    # Set more verbose logging for specific modules
    logging.getLogger('new_england_listings.extractors').setLevel(level)
    logging.getLogger('new_england_listings.utils').setLevel(level)

    # Set less verbose logging for noisy libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)


async def main(urls=None):
    """
    Main entry point for command-line execution.
    
    Args:
        urls: Optional list of URLs to process
    """
    # Configure logging
    setup_logging(level=logging.INFO, log_file='listings.log')

    # Get URLs from command line or input
    if not urls:
        if len(sys.argv) > 1:
            urls = sys.argv[1:]
        else:
            url = input(
                "Enter listing URL (or comma-separated list of URLs): ")
            urls = [u.strip() for u in url.split(',')]

    try:
        # Process listings
        results = await process_listings(urls)

        # Print summary
        print("\nProcessing Summary:")
        for result in results:
            status = result.get('extraction_status', 'unknown')
            if status == 'failed':
                print(
                    f"❌ {result.get('url')}: {result.get('error', 'Unknown error')}")
            else:
                print(
                    f"✅ {result.get('listing_name', 'Unnamed listing')} - {result.get('price', 'No price')} - {result.get('location', 'No location')}")

        print(f"\nProcessed {len(results)} listings.")

        # Print rate limiting stats
        stats = rate_limiter.get_stats()
        print("\nRate Limiting Statistics:")
        print(f"Total requests: {stats['total_requests']}")
        print(f"Rate limited requests: {stats['rate_limited_requests']}")

        # Print per-domain stats
        print("\nPer-domain statistics:")
        for domain, domain_stats in stats['domains'].items():
            print(f"  {domain}:")
            print(f"    Requests: {domain_stats['requests']}")
            print(f"    Rate limited: {domain_stats['rate_limited']}")
            print(f"    RPM limit: {domain_stats['rpm_limit']}")
            print(
                f"    Current requests in last minute: {domain_stats['requests_last_minute']}")

    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
