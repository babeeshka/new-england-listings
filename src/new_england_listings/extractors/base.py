# src/new_england_listings/extractors/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple
from bs4 import BeautifulSoup
import logging
import random
import time

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Base class for all property listing extractors."""

    def __init__(self, url: str):
        self.url = url
        self.soup = None
        self.data = {}

        # Required fields for Notion database
        self.required_fields = {
            "url": url,
            "platform": self.platform_name,
            "listing_name": "Untitled Listing",
            "location": "Location Unknown",
            "price": "Contact for Price",
            "price_bucket": "N/A",
            "property_type": "Unknown",
            "acreage": "Not specified",
            "acreage_bucket": "Unknown",
            "listing_date": None,
            "distance_to_portland": None,
            "portland_distance_bucket": None,
            "town_population": None,
            "town_pop_bucket": None,
            "school_rating": None,
            "school_rating_cat": None,
            "hospital_distance": None,
            "hospital_distance_bucket": None,
            "notes": None,
            "other_amenities": None,
            "restaurants_nearby": None,
            "grocery_stores_nearby": None,
            "house_details": None
        }

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the name of the platform this extractor handles."""
        pass

    @abstractmethod
    def extract_listing_name(self) -> str:
        """Extract the listing name/title."""
        pass

    @abstractmethod
    def extract_price(self) -> Tuple[str, str]:
        """Extract price and determine price bucket."""
        pass

    @abstractmethod
    def extract_location(self) -> str:
        """Extract the property location."""
        pass

    @abstractmethod
    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information and determine bucket."""
        pass

    def _log_diagnostic_info(self):
        """Log diagnostic information about the page content."""
        logger.debug("=== DIAGNOSTIC INFORMATION ===")
        logger.debug(f"Platform: {self.platform_name}")
        logger.debug(f"URL: {self.url}")

        if self.soup:
            # Log title and meta tags
            if self.soup.title:
                logger.debug(f"Page Title: {self.soup.title.string}")

            # Check for common blocking patterns
            block_patterns = [
                "captcha",
                "security check",
                "please verify",
                "access denied",
                "pardon our interruption"
            ]

            page_text = self.soup.get_text().lower()
            for pattern in block_patterns:
                if pattern in page_text:
                    logger.warning(f"Potential blocking detected: '{pattern}'")

        logger.debug("=== END DIAGNOSTIC INFO ===")

    def extract(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Main extraction method."""
        logger.debug(f"Starting extraction for {self.platform_name}")
        self.soup = soup

        # Add random delay between 2-5 seconds
        delay = random.uniform(2, 5)
        logger.debug(f"Adding delay of {delay:.2f} seconds")
        time.sleep(delay)

        # Initialize data with required fields
        self.data = self.required_fields.copy()

        # Log diagnostic information
        self._log_diagnostic_info()

        # Sample of HTML content for debugging
        logger.debug(
            f"HTML Content (first 500 chars): {soup.prettify()[:500]}")

        # Extract core data with error handling
        extraction_methods = {
            "listing_name": self.extract_listing_name,
            "price": lambda: self.extract_price(),
            "location": self.extract_location,
            "acreage": lambda: self.extract_acreage_info()
        }

        for field, method in extraction_methods.items():
            try:
                if field == "price":
                    price, price_bucket = method()
                    self.data["price"] = price
                    self.data["price_bucket"] = price_bucket
                elif field == "acreage":
                    acreage, acreage_bucket = method()
                    self.data["acreage"] = acreage
                    self.data["acreage_bucket"] = acreage_bucket
                else:
                    self.data[field] = method()
            except Exception as e:
                logger.warning(f"Error extracting {field}: {str(e)}")

        # Extract additional platform-specific data
        try:
            self.extract_additional_data()
        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")

        # Ensure all required fields are present
        self._validate_data()

        return self.data

    def _validate_data(self):
        """Validate that all required fields are present in the data."""
        missing_fields = [
            field for field in self.required_fields if field not in self.data]
        if missing_fields:
            logger.warning(f"Missing required fields: {missing_fields}")
            # Add missing fields with default values
            for field in missing_fields:
                self.data[field] = self.required_fields[field]

    def extract_additional_data(self):
        """Hook for extractors to add platform-specific data."""
        pass
