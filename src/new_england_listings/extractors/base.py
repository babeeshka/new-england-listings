# src/new_england_listings/extractors/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
from bs4 import BeautifulSoup
import logging
import random
import time
from datetime import datetime
from pydantic import ValidationError

from ..models.base import PropertyListing, PropertyType, PriceBucket, AcreageBucket
from ..utils.text import clean_price, extract_acreage
from ..utils.geocoding import get_comprehensive_location_info

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Base class for extraction errors"""
    pass


class ValidationError(ExtractionError):
    """Raised when extracted data fails validation"""
    pass


class BaseExtractor(ABC):
    """Base class for all property listing extractors with data validation."""

    def __init__(self, url: str):
        self.url = url
        self.soup = None
        self.raw_data = {}

        # Initialize empty data with required fields
        self.data = {
            "url": url,
            "platform": self.platform_name,
            "listing_name": "Untitled Listing",
            "location": "Location Unknown",
            "price": "Contact for Price",
            "price_bucket": PriceBucket.NA,
            "property_type": PropertyType.UNKNOWN,
            "acreage": "Not specified",
            "acreage_bucket": AcreageBucket.UNKNOWN
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
    def extract_price(self) -> Tuple[str, PriceBucket]:
        """Extract price and determine price bucket."""
        pass

    @abstractmethod
    def extract_location(self) -> str:
        """Extract the property location."""
        pass

    @abstractmethod
    def extract_acreage_info(self) -> Tuple[str, AcreageBucket]:
        """Extract acreage information and determine bucket."""
        pass

    def _validate_data(self, data: Dict[str, Any]) -> PropertyListing:
        """Validate extracted data against the model."""
        try:
            return PropertyListing(**data)
        except ValidationError as e:
            logger.error(f"Data validation failed: {str(e)}")
            raise ValidationError(
                f"Failed to validate extracted data: {str(e)}")

    def _log_diagnostic_info(self):
        """Log diagnostic information about the page content."""
        logger.debug("=== DIAGNOSTIC INFORMATION ===")
        logger.debug(f"Platform: {self.platform_name}")
        logger.debug(f"URL: {self.url}")

        if self.soup:
            if self.soup.title:
                logger.debug(f"Page Title: {self.soup.title.string}")

            # Check for common blocking patterns
            block_patterns = [
                "captcha",
                "security check",
                "please verify",
                "access denied"
            ]

            page_text = self.soup.get_text().lower()
            for pattern in block_patterns:
                if pattern in page_text:
                    logger.warning(f"Potential blocking detected: '{pattern}'")

        logger.debug("=== END DIAGNOSTIC INFO ===")

    def _process_location_info(self, location_info: Dict[str, Any]):
        """Process location information with LandSearch specific logic."""
        # Process standard fields directly instead of calling super()
        try:
            # Distance metrics
            if 'distance_to_portland' in location_info:
                self.data["distance_to_portland"] = float(
                    location_info["distance_to_portland"])
                self.data["portland_distance_bucket"] = self._get_distance_bucket(
                    float(location_info["distance_to_portland"]))

            # Population metrics
            if 'town_population' in location_info:
                self.data["town_population"] = int(
                    location_info["town_population"])
                self.data["town_pop_bucket"] = self._get_population_bucket(
                    int(location_info["town_population"]))

            # School metrics
            if 'school_rating' in location_info:
                self.data["school_rating"] = float(
                    location_info["school_rating"])
                self.data["school_rating_cat"] = self._get_school_rating_category(
                    float(location_info["school_rating"]))

            # Hospital metrics
            if 'hospital_distance' in location_info:
                self.data["hospital_distance"] = float(
                    location_info["hospital_distance"])
                self.data["hospital_distance_bucket"] = self._get_distance_bucket(
                    float(location_info["hospital_distance"]))

            # LandSearch specific processing
            # Handle recreation information
            if 'recreation_areas_nearby' in location_info:
                self.data["recreation_areas_nearby"] = location_info["recreation_areas_nearby"]

            # Process hunting/fishing data
            if 'hunting_zone' in location_info:
                self.data["hunting_zone"] = location_info["hunting_zone"]

            # Add specific zoning information
            if 'zoning_details' in location_info:
                self.data["zoning_details"] = location_info["zoning_details"]

        except Exception as e:
            logger.error(
                f"Error processing location info: {str(e)}")

    def extract(self, soup: BeautifulSoup) -> PropertyListing:
        """Main extraction method with validation."""
        logger.debug(f"Starting extraction for {self.platform_name}")
        self.soup = soup
        self.raw_data = {}

        try:
            # Add random delay between 2-5 seconds
            delay = random.uniform(2, 5)
            logger.debug(f"Adding delay of {delay:.2f} seconds")
            time.sleep(delay)

            # Extract core data with error handling
            extraction_methods = {
                "listing_name": self.extract_listing_name,
                "price": self.extract_price,
                "location": self.extract_location,
                "acreage": self.extract_acreage_info
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
                    # Keep default values for failed extractions

            # Extract additional platform-specific data
            try:
                self.extract_additional_data()
            except Exception as e:
                logger.error(f"Error in additional data extraction: {str(e)}")

            # Get location-based information if location is valid
            if self.data["location"] != "Location Unknown":
                try:
                    location_info = get_comprehensive_location_info(
                        self.data["location"])
                    if location_info:
                        self.data.update(location_info)
                except Exception as e:
                    logger.error(f"Error getting location info: {str(e)}")

            # Store raw data for debugging
            self.data["raw_data"] = self.raw_data

            # Validate and return data
            validated_data = self._validate_data(self.data)
            logger.info(f"Successfully extracted and validated listing data")
            return validated_data

        except Exception as e:
            logger.error(f"Error in extraction: {str(e)}", exc_info=True)
            raise ExtractionError(f"Failed to extract listing data: {str(e)}")

    def extract_additional_data(self):
        """Hook for extractors to add platform-specific data."""
        pass
