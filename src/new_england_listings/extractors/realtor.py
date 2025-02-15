# src/new_england_listings/extractors/realtor.py
from typing import Dict, Any, Tuple, Optional
import re
import time
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from .base import BaseExtractor
from ..utils.text import clean_price, extract_acreage, clean_html_text
from ..utils.dates import extract_listing_date
from ..utils.geocoding import get_location_coordinates, get_distance, get_bucket
from ..config.constants import PRICE_BUCKETS, ACREAGE_BUCKETS, DISTANCE_BUCKETS, MAJOR_CITIES

logger = logging.getLogger(__name__)

# Updated selectors based on current realtor.com HTML structure
REALTOR_SELECTORS = {
    "price": {
        "main": {"data-testid": "price"},
        "formatted": {"data-testid": "list-price"},
        "fallback": {"class_": "Price__Component"}
    },
    "details": {
        "beds": {"data-testid": "property-meta-beds"},
        "baths": {"data-testid": "property-meta-baths"},
        "sqft": {"data-testid": "property-meta-sqft"},
        "lot": {"data-testid": "property-meta-lot-size"},
        "type": {"data-testid": "property-type"},
        "features": {"data-testid": "property-features"}
    },
    "location": {
        "address": {"data-testid": "address"},
        "city_state": {"data-testid": "city-state"}
    },
    "description": {
        "main": {"data-testid": "property-description"},
        "features": {"data-testid": "features"}
    }
}


class RealtorExtractor(BaseExtractor):
    """Extractor for Realtor.com listings."""

    def __init__(self, url: str):
        super().__init__(url)
        self.data = {
            "platform": "Realtor.com",
            "url": url
        }

    @property
    def platform_name(self) -> str:
        return "Realtor.com"

    def _verify_page_content(self) -> bool:
        """Verify the page content was properly loaded."""
        if not self.soup:
            logger.error("No page content found")
            return False

        # Check for essential elements
        checks = {
            "Price element": bool(self.soup.find(attrs=REALTOR_SELECTORS["price"]["main"]) or
                                  self.soup.find(attrs=REALTOR_SELECTORS["price"]["formatted"])),
            "Location element": bool(self.soup.find(attrs=REALTOR_SELECTORS["location"]["address"])),
            "Property details": bool(self.soup.find(attrs=REALTOR_SELECTORS["details"]["beds"]))
        }

        for element, found in checks.items():
            logger.debug(f"{element} found: {found}")

        return any(checks.values())

    def extract_price(self) -> Tuple[str, str]:
        """Extract price and determine price bucket."""
        logger.debug("Extracting price")

        # Try different price selectors
        for selector_key, selector in REALTOR_SELECTORS["price"].items():
            price_elem = self.soup.find(attrs=selector)
            if price_elem:
                price_text = clean_html_text(price_elem.text)
                if '$' in price_text:
                    logger.debug(
                        f"Found price in {selector_key}: {price_text}")
                    return clean_price(price_text)

        # Try backup method - look for any price pattern
        for text in self.soup.stripped_strings:
            if '$' in text and re.search(r'\$[\d,]+', text):
                logger.debug(f"Found price in text: {text}")
                return clean_price(text)

        return "Contact for Price", "N/A"

    def extract_location(self) -> str:
        """Extract property location."""
        logger.debug("Extracting location")

        # Try address elements
        for key in ["address", "city_state"]:
            elem = self.soup.find(attrs=REALTOR_SELECTORS["location"][key])
            if elem:
                location = clean_html_text(elem.text)
                if location and any(state in location for state in ["ME", "NH", "VT", "MA", "CT", "RI"]):
                    logger.debug(f"Found location: {location}")
                    return location

        # Try URL parsing
        try:
            parts = self.url.split('/')[-1].split('_')
            if len(parts) >= 3:
                city = parts[-3].replace('-', ' ').title()
                state = parts[-2].upper()
                return f"{city}, {state}"
        except Exception as e:
            logger.warning(f"Failed to parse location from URL: {str(e)}")

        return "Location Unknown"

    def extract_listing_name(self) -> str:
        """Extract listing name/title."""
        location = self.extract_location()
        if location != "Location Unknown":
            return f"Property at {location}"
        return "Untitled Listing"

    def _extract_property_details(self):
        """Extract property details including beds, baths, sqft."""
        details = []

        # Extract basic details
        for key in ["beds", "baths", "sqft"]:
            elem = self.soup.find(attrs=REALTOR_SELECTORS["details"][key])
            if elem:
                value = clean_html_text(elem.text)
                if value:
                    details.append(value)

        if details:
            self.data["house_details"] = " | ".join(details)

        # Extract property type
        type_elem = self.soup.find(attrs=REALTOR_SELECTORS["details"]["type"])
        if type_elem:
            self.data["property_type"] = clean_html_text(type_elem.text)

        # Extract lot size/acreage
        lot_elem = self.soup.find(attrs=REALTOR_SELECTORS["details"]["lot"])
        if lot_elem:
            lot_text = clean_html_text(lot_elem.text)
            acres = extract_acreage(lot_text)
            if acres:
                self.data.update({
                    "acreage": f"{acres:.2f} acres",
                    "acreage_bucket": get_bucket(acres, ACREAGE_BUCKETS)
                })

    def _extract_amenities(self):
        """Extract property amenities and features."""
        amenities = []
        features_elem = self.soup.find(
            attrs=REALTOR_SELECTORS["description"]["features"])

        if features_elem:
            for item in features_elem.find_all("li"):
                amenities.append(clean_html_text(item.text))

        if amenities:
            self.data["other_amenities"] = " | ".join(
                amenities[:5])  # Limit to top 5

    def extract_additional_data(self):
        """Extract all additional property data."""
        try:
            self._extract_property_details()
            self._extract_amenities()

            # Calculate distance to Portland
            location = self.data.get("location")
            if location and location != "Location Unknown":
                coords = get_location_coordinates(location)
                if coords:
                    portland_coords = MAJOR_CITIES["Portland, ME"]["coordinates"]
                    distance = get_distance(coords, portland_coords)
                    self.data.update({
                        "distance_to_portland": f"{distance:.1f}",
                        "portland_distance_bucket": get_bucket(distance, DISTANCE_BUCKETS)
                    })

            # Extract listing date
            listing_date = extract_listing_date(self.soup, self.platform_name)
            if listing_date:
                self.data["listing_date"] = listing_date

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")

        return self.data
