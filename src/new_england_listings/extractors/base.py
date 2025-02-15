# src/new_england_listings/extractors/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Base class for all property listing extractors."""

    def __init__(self, url: str):
        self.url = url
        self.soup = None
        self.data = {}

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
    def extract_price(self) -> tuple[str, str]:
        """Extract price and determine price bucket."""
        pass

    @abstractmethod
    def extract_location(self) -> str:
        """Extract the property location."""
        pass


    def extract(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Main extraction method."""
        logger.debug(f"Starting extraction for {self.platform_name}")
        self.soup = soup

        # Print the first part of the HTML to verify content
        logger.debug(f"HTML Content (first 500 chars): {soup.prettify()[:500]}")
        self.data = {
            "url": self.url,
            "platform": self.platform_name,
            "listing_name": "Untitled Listing",
            "location": "Location Unknown",
            "price": "Contact for Price",
            "price_bucket": "N/A",
            "property_type": "Unknown",
            "acreage": "Not specified",
            "acreage_bucket": "Unknown",
            "listing_date": None
        }

        try:
            self.data["listing_name"] = self.extract_listing_name()
        except Exception as e:
            logger.warning(f"Error extracting listing name: {str(e)}")

        try:
            price, price_bucket = self.extract_price()
            self.data["price"] = price
            self.data["price_bucket"] = price_bucket
        except Exception as e:
            logger.warning(f"Error extracting price: {str(e)}")

        try:
            self.data["location"] = self.extract_location()
        except Exception as e:
            logger.warning(f"Error extracting location: {str(e)}")

        try:
            acreage, acreage_bucket = self.extract_acreage_info()
            self.data["acreage"] = acreage
            self.data["acreage_bucket"] = acreage_bucket
        except Exception as e:
            logger.warning(f"Error extracting acreage: {str(e)}")

        self.extract_additional_data()
        return self.data

    def extract_additional_data(self):
        """Hook for extractors to add platform-specific data."""
        pass
