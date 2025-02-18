# src/new_england_listings/extractors/landsearch.py
from typing import Dict, Any, Tuple
import re
import logging
from bs4 import BeautifulSoup
from .base import BaseExtractor
from ..utils.text import clean_price, clean_html_text, extract_acreage
from ..utils.dates import extract_listing_date
from ..utils.geocoding import get_comprehensive_location_info
from ..config.constants import ACREAGE_BUCKETS

logger = logging.getLogger(__name__)

LANDSEARCH_SELECTORS = {
    "price": {
        "main": {"class_": "property-price"},
        "detail": {"class_": "price-detail"},
    },
    "details": {
        "container": {"class_": "property-details"},
        "acreage": {"class_": "property-acreage"},
        "features": {"class_": "property-features"},
        "description": {"class_": "property-description"},
    },
    "location": {
        "address": {"class_": "property-address"},
        "city": {"class_": "property-city"},
        "state": {"class_": "property-state"}
    }
}


class LandSearchExtractor(BaseExtractor):
    """Extractor for LandSearch.com listings."""

    def __init__(self, url: str):
        super().__init__(url)
        self.data = {
            "platform": "LandSearch",
            "url": url
        }

    @property
    def platform_name(self) -> str:
        return "LandSearch"

    def _verify_page_content(self) -> bool:
        """Verify the page content was properly loaded."""
        logger.debug("Verifying page content...")

        # Debug content
        logger.debug("Found elements:")
        for section, selectors in LANDSEARCH_SELECTORS.items():
            for name, selector in selectors.items():
                elem = self.soup.find(**selector)
                logger.debug(f"{section}.{name}: {elem is not None}")

        # Check for essential elements
        essential_elements = [
            self.soup.find(**LANDSEARCH_SELECTORS["price"]["main"]),
            self.soup.find(**LANDSEARCH_SELECTORS["details"]["container"]),
            self.soup.find(**LANDSEARCH_SELECTORS["location"]["address"])
        ]

        return any(essential_elements)

    def extract_listing_name(self) -> str:
        """Extract listing name/title."""
        # Try to construct from address
        address = self.soup.find(**LANDSEARCH_SELECTORS["location"]["address"])
        if address:
            return clean_html_text(address.text)

        # Fallback to URL-based name
        location = self.extract_location()
        if location != "Location Unknown":
            return f"Property at {location}"

        return "Untitled Listing"

    def extract_price(self) -> Tuple[str, str]:
        """Extract price and determine price bucket."""
        for selector in LANDSEARCH_SELECTORS["price"].values():
            price_elem = self.soup.find(**selector)
            if price_elem:
                price_text = clean_html_text(price_elem.text)
                if '$' in price_text:
                    return clean_price(price_text)

        return "Contact for Price", "N/A"

    def extract_location(self) -> str:
        """Extract property location."""
        # Try to combine address components
        address_parts = []

        for key in ["address", "city", "state"]:
            elem = self.soup.find(**LANDSEARCH_SELECTORS["location"][key])
            if elem:
                address_parts.append(clean_html_text(elem.text))

        if address_parts:
            return ", ".join(address_parts)

        return "Location Unknown"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information."""
        # Look for acreage in property details
        acreage_elem = self.soup.find(
            **LANDSEARCH_SELECTORS["details"]["acreage"])
        if acreage_elem:
            return extract_acreage(acreage_elem.text)

        # Try finding in description
        description = self.soup.find(
            **LANDSEARCH_SELECTORS["details"]["description"])
        if description:
            text = clean_html_text(description.text)
            if 'acre' in text.lower():
                return extract_acreage(text)

        return "Not specified", "Unknown"

    def extract_additional_data(self):
        """Extract additional property data."""
        try:
            # Extract property features
            features = []
            features_elem = self.soup.find(
                **LANDSEARCH_SELECTORS["details"]["features"])
            if features_elem:
                for item in features_elem.find_all(['li', 'div']):
                    feature_text = clean_html_text(item.text)
                    if feature_text:
                        features.append(feature_text)

            if features:
                self.data["other_amenities"] = " | ".join(features[:5])

            # Extract property type (if mentions land/farm/etc)
            description = self.soup.find(
                **LANDSEARCH_SELECTORS["details"]["description"])
            if description:
                text = clean_html_text(description.text).lower()
                if any(word in text for word in ['farm', 'ranch', 'agricultural']):
                    self.data["property_type"] = "Farm"
                elif any(word in text for word in ['land', 'lot', 'acreage']):
                    self.data["property_type"] = "Land"
                elif "residential" in text:
                    self.data["property_type"] = "Residential"

            # Get location-based information
            if self.data.get("location") != "Location Unknown":
                location_info = get_comprehensive_location_info(
                    self.data["location"])
                self.data.update(location_info)

            # Extract listing date
            listing_date = extract_listing_date(self.soup, self.platform_name)
            if listing_date:
                self.data["listing_date"] = listing_date

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")
