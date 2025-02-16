# src/new_england_listings/extractors/realtor.py
from typing import Dict, Any, Tuple, Optional
import re
import logging
from bs4 import BeautifulSoup
from .base import BaseExtractor
from ..utils.text import clean_price, clean_html_text, get_range_bucket
from ..utils.dates import extract_listing_date
from ..utils.geocoding import get_location_coordinates, get_distance, get_bucket
from ..config.constants import PRICE_BUCKETS, ACREAGE_BUCKETS, DISTANCE_BUCKETS

logger = logging.getLogger(__name__)

REALTOR_SELECTORS = {
    "price": {
        "main": {"data-testid": "list-price"},
        "formatted": {"data-testid": "price"},
        "container": {"class_": lambda x: x and "Price__Component" in x}
    },
    "details": {
        "container": {"data-testid": "property-meta"},
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

    def _log_diagnostic_info(self):
        """Log diagnostic information about the page content."""
        logger = logging.getLogger(__name__)

        # Log basic page info
        logger.debug("=== DIAGNOSTIC INFORMATION ===")

        # Check for main content containers
        selectors_found = {
            "Price Container": bool(self.soup.find(attrs=REALTOR_SELECTORS["price"]["main"])),
            "Property Details": bool(self.soup.find(attrs=REALTOR_SELECTORS["details"]["container"])),
            "Location Info": bool(self.soup.find(attrs=REALTOR_SELECTORS["location"]["address"]))
        }

        logger.debug("Main selectors found:")
        for name, found in selectors_found.items():
            logger.debug(f"  {name}: {found}")

        # Log specific content snippets
        logger.debug("\nContent samples:")
        for selector_type, selectors in REALTOR_SELECTORS.items():
            for key, selector in selectors.items():
                elem = self.soup.find(attrs=selector)
                if elem:
                    logger.debug(
                        f"  {selector_type}.{key}: {elem.get_text().strip()[:100]}")

        # Check for potential CAPTCHA/blocking
        potential_blocks = [
            "captcha",
            "security check",
            "please verify",
            "access denied",
            "pardon our interruption"
        ]

        page_text = self.soup.get_text().lower()
        for block in potential_blocks:
            if block in page_text:
                logger.warning(
                    f"Potential blocking detected: '{block}' found in page")

        logger.debug("=== END DIAGNOSTIC INFO ===")

    def extract_price(self) -> Tuple[str, str]:
        """Extract price and determine price bucket."""
        logger.debug("Extracting price")

        for selector_key, selector in REALTOR_SELECTORS["price"].items():
            price_elem = self.soup.find(attrs=selector)
            if price_elem:
                price_text = clean_html_text(price_elem.text)
                if '$' in price_text:
                    logger.debug(
                        f"Found price in {selector_key}: {price_text}")
                    return clean_price(price_text)

        return "Contact for Price", "N/A"

    def extract_location(self) -> str:
        """Extract property location."""
        logger.debug("Extracting location")

        # Try each location selector
        for key in ["address", "city_state"]:
            elem = self.soup.find(attrs=REALTOR_SELECTORS["location"][key])
            if elem:
                location = clean_html_text(elem.text)
                # Check if we have a state code
                state_match = re.search(r'([A-Z]{2})', location)
                if state_match:
                    logger.debug(f"Found location: {location}")
                    return location

        # Try to extract from URL
        parts = self.url.split('_')
        if len(parts) >= 3:
            city = parts[-3].replace('-', ' ').title()
            state = parts[-2].upper()
            return f"{city}, {state}"

        # If we only have zip code, use that with state
        zip_match = re.search(r'_(\d{5})_', self.url)
        if zip_match:
            # Assuming NH based on URL pattern
            return f"NH, {zip_match.group(1)}"

        return "Location Unknown"

    def extract_listing_name(self) -> str:
        """Extract listing name/title."""
        address_elem = self.soup.find(
            attrs=REALTOR_SELECTORS["location"]["address"])
        if address_elem:
            return clean_html_text(address_elem.text)

        location = self.extract_location()
        if location != "Location Unknown":
            return f"Property at {location}"

        return "Untitled Listing"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information and determine bucket."""
        logger.debug("Extracting acreage info")

        # Try to find lot size in property details
        lot_elem = self.soup.find(attrs=REALTOR_SELECTORS["details"]["lot"])
        if lot_elem:
            lot_text = clean_html_text(lot_elem.text)
            logger.debug(f"Found lot text: {lot_text}")

            # Convert different formats to acres
            try:
                # Handle acres format
                acre_match = re.search(r'([\d,.]+)\s*acres?', lot_text, re.I)
                if acre_match:
                    acres = float(acre_match.group(1).replace(',', ''))
                    return f"{acres:.2f} acres", get_range_bucket(acres, ACREAGE_BUCKETS)

                # Handle square feet format
                sqft_match = re.search(
                    r'([\d,.]+)\s*sq\s*\.?\s*ft', lot_text, re.I)
                if sqft_match:
                    sqft = float(sqft_match.group(1).replace(',', ''))
                    acres = sqft / 43560  # Convert sqft to acres
                    return f"{acres:.2f} acres", get_range_bucket(acres, ACREAGE_BUCKETS)

                # Handle square meters format
                sqm_match = re.search(r'([\d,.]+)\s*m²', lot_text)
                if sqm_match:
                    sqm = float(sqm_match.group(1).replace(',', ''))
                    acres = sqm * 0.000247105  # Convert square meters to acres
                    return f"{acres:.2f} acres", get_range_bucket(acres, ACREAGE_BUCKETS)

            except (ValueError, TypeError) as e:
                logger.warning(f"Error converting lot size: {str(e)}")

        return "Not specified", "Unknown"

    def _clean_house_details(self, text: str) -> str:
        """Clean and format house details text."""
        # Remove duplicate square footage
        text = re.sub(r'(\d+,\d+)\s*square feet.*$', r'\1sqft', text)
        # Clean up separators
        text = re.sub(r'\s*\|\s*', ' | ', text)
        return text.strip()

    def _extract_property_details(self):
        """Extract property details."""
        details = []

        # Extract basic details (beds, baths, sqft)
        for key in ["beds", "baths", "sqft"]:
            elem = self.soup.find(attrs=REALTOR_SELECTORS["details"][key])
            if elem:
                value = clean_html_text(elem.text)
                if value:
                    details.append(value)

        if details:
            self.data["house_details"] = self._clean_house_details(
                " | ".join(details))

        # Extract property type
        type_elem = self.soup.find(attrs=REALTOR_SELECTORS["details"]["type"])
        if type_elem:
            self.data["property_type"] = clean_html_text(type_elem.text)

    def extract_additional_data(self):
        """Extract all additional property data."""
        try:
            self._extract_property_details()

            # Calculate distance to Portland if we have a valid location
            location = self.data.get("location")
            if location and location != "Location Unknown":
                coords = get_location_coordinates(location)
                if coords:
                    # Portland, ME coordinates
                    portland_coords = (43.6591, -70.2568)
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
