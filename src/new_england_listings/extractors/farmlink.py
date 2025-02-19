# src/new_england_listings/extractors/farmlink.py
from typing import Dict, Any, Tuple, Optional, Union, List
import re
import logging
from bs4 import BeautifulSoup
from .base import BaseExtractor
from ..utils.text import clean_price, clean_html_text, extract_acreage
from ..utils.dates import extract_listing_date
from ..utils.geocoding import get_comprehensive_location_info

logger = logging.getLogger(__name__)

FARMLINK_SELECTORS = {
    "farm_details": {
        "container": {"class_": "info-right_property-description"},
        "field_label": {"class_": ["text-color-primary", "text-weight-bold"]},
        "field_value": {"class_": ["text-color-primary", "display-inline"]}
    },
    "property_description": {
        "container": {"class_": "info-right_property-description"},
        "content": {"class_": ["text-color-primary", "w-richtext"]}
    },
    "labels": {
        "county": "ME County:",
        "farm_house": "Farm House:",
        "total_acres": "Total Acres:",
        "entry_date": "Entry Date:",
        "price": "Price:",
        "property_type": "Property Type:"
    }
}


class FarmLinkExtractor(BaseExtractor):
    """Extractor for Maine FarmLink listings."""

    @property
    def platform_name(self) -> str:
        return "Maine FarmLink"

    def __init__(self, url: str):
        super().__init__(url)
        self.data = {
            "platform": "Maine FarmLink",
            "url": url,
            "property_type": "Farm"
        }
    
    def _find_field_value(self, label: str) -> Optional[str]:
        """Find value for a given field label."""
        logger.debug(f"Searching for field: {label}")

        try:
            # First try finding the label element
            field_elem = self.soup.find(
                string=lambda x: x and label.strip() in str(x).strip(),
                class_=FARMLINK_SELECTORS["farm_details"]["field_label"]["class_"]
            )

            if field_elem:
                logger.debug(f"Found field element with label: {label}")

                # Try multiple approaches to find the value
                # 1. Look for next sibling with value class
                value_elem = field_elem.find_next_sibling(
                    class_=FARMLINK_SELECTORS["farm_details"]["field_value"]["class_"]
                )

                # 2. Look for parent's next sibling
                if not value_elem:
                    value_elem = field_elem.parent.find_next_sibling(
                        class_=FARMLINK_SELECTORS["farm_details"]["field_value"]["class_"]
                    )

                # 3. Look within the same container div
                if not value_elem:
                    container = field_elem.find_parent(
                        class_=FARMLINK_SELECTORS["farm_details"]["container"])
                    if container:
                        value_elem = container.find(
                            class_=FARMLINK_SELECTORS["farm_details"]["field_value"]["class_"]
                        )

                if value_elem:
                    value = clean_html_text(value_elem.text)
                    logger.debug(f"Found value: {value}")
                    return value

                # If we found the label but no value element, try getting the next text
                next_text = field_elem.find_next(string=True)
                if next_text:
                    value = clean_html_text(next_text)
                    logger.debug(f"Found value from next text: {value}")
                    return value

        except Exception as e:
            logger.error(f"Error finding field value for {label}: {str(e)}")

        return None

    def extract_location(self) -> str:
        """Extract location information."""
        logger.debug("Extracting location...")

        # Try to find county in farm details
        county_value = self._find_field_value(
            FARMLINK_SELECTORS["labels"]["county"])
        if county_value:
            # Clean up the value to just get the county name
            county = clean_html_text(
                county_value.replace("ME County:", "").strip())
            if county:
                logger.debug(f"Found county: {county}")
                # Validate that it's a Maine county
                maine_counties = [
                    "Androscoggin", "Aroostook", "Cumberland", "Franklin",
                    "Hancock", "Kennebec", "Knox", "Lincoln", "Oxford",
                    "Penobscot", "Piscataquis", "Sagadahoc", "Somerset",
                    "Waldo", "Washington", "York"
                ]
                if county in maine_counties:
                    return f"{county} County, ME"

        # If we can't find or validate the county, try finding location in description
        desc = self.soup.find(
            **FARMLINK_SELECTORS["property_description"]["container"])
        if desc:
            content = desc.find(
                **FARMLINK_SELECTORS["property_description"]["content"])
            if content:
                text = content.get_text()
                # Look for location patterns in description
                location_patterns = [
                    r'located in (\w+) County',
                    r'property in (\w+) County',
                    r'farm in (\w+) County',
                    r'(\w+) County, Maine'
                ]
                for pattern in location_patterns:
                    match = re.search(pattern, text, re.I)
                    if match:
                        county = match.group(1).strip()
                        logger.debug(f"Found county in description: {county}")
                        return f"{county} County, ME"

        return "Location Unknown"

    def extract_price(self) -> Tuple[str, str]:
        """Extract price information."""
        logger.debug("Extracting price...")

        # First try getting direct price field
        price_value = self._find_field_value(FARMLINK_SELECTORS["labels"]["price"])
        if price_value:
            return clean_price(price_value)

        # Try finding in description with more specific patterns
        desc = self.soup.find(
            **FARMLINK_SELECTORS["property_description"]["container"])
        if desc:
            content = desc.find(
                **FARMLINK_SELECTORS["property_description"]["content"])
            if content:
                text = content.get_text()
                price_patterns = [
                    r'(?:asking|listing|sale)\s+price(?:\s+is)?\s*(?:of)?\s*\$?([\d,.]+)',
                    r'priced\s+at\s*\$?([\d,.]+)',
                    r'(\$[\d,.]+)(?:\s+(?:for|asking|price))',
                    r'property\s+is\s+(?:listed\s+)?(?:for|at)\s*\$?([\d,.]+)'
                ]

                for pattern in price_patterns:
                    match = re.search(pattern, text, re.I)
                    if match:
                        price_str = match.group(1).replace('$', '').strip()
                        return clean_price(price_str)

        return "Contact for Price", "N/A"

    def extract_listing_date(self) -> str:
        """Extract listing date information."""
        logger.debug("Extracting listing date...")

        # Try getting direct entry date field
        entry_date_value = self._find_field_value(FARMLINK_SELECTORS["labels"]["entry_date"])
        if entry_date_value:
            return extract_listing_date(entry_date_value)

        # If not found, return a default value
        return "Unknown"

    def extract_listing_name(self) -> str:
        """Extract listing name from URL or page content."""
        # First check if there's a page title
        if self.soup.title:
            title = clean_html_text(self.soup.title.string)
            if title and "Farm ID" in title:
                return title.strip()

        # Fallback to extracting from URL
        farm_id_match = re.search(r'farm-id-(\d+)', self.url)
        if farm_id_match:
            return f"Farm ID {farm_id_match.group(1)}"

        return "Untitled Farm Property"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information and bucket."""
        logger.debug("Extracting acreage...")

        # Try getting direct acreage field
        acreage_value = self._find_field_value(
            FARMLINK_SELECTORS["labels"]["total_acres"])
        if acreage_value:
            logger.debug(f"Found acreage in fields: {acreage_value}")
            return extract_acreage(f"{acreage_value} acres")

        # Try finding in description
        desc = self.soup.find(
            **FARMLINK_SELECTORS["property_description"]["container"])
        if desc:
            content = desc.find(
                **FARMLINK_SELECTORS["property_description"]["content"])
            if content:
                text = content.get_text()
                acreage_patterns = [
                    r'(\d+(?:\.\d+)?)\s*acres?',
                    r'property\s+(?:is|of)\s*(\d+(?:\.\d+)?)\s*acres?',
                    r'(?:approximately|about)\s*(\d+(?:\.\d+)?)\s*acres?',
                    r'(?:total|farm)(?:\s+of)?\s*(\d+(?:\.\d+)?)\s*acres?'
                ]

                for pattern in acreage_patterns:
                    match = re.search(pattern, text, re.I)
                    if match:
                        acres = match.group(1)
                        logger.debug(f"Found acreage in description: {acres}")
                        return extract_acreage(f"{acres} acres")

        return "Not specified", "Unknown"

    def extract(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Main extraction method."""
        logger.debug(f"Starting extraction for {self.platform_name}")
        self.soup = soup

        # Initialize data with required fields
        self.data = self.required_fields.copy()

        # Extract basic information
        self.data["listing_name"] = self.extract_listing_name()
        self.data["location"] = self.extract_location()
        self.data["price"], self.data["price_bucket"] = self.extract_price()
        self.data["acreage"], self.data["acreage_bucket"] = self.extract_acreage_info()

        # Extract additional data
        self.extract_additional_data()

        # If we have a valid location, get comprehensive location info
        if self.data["location"] != "Location Unknown":
            location_info = get_comprehensive_location_info(self.data["location"])
            self.data.update(location_info)

        return self.data

    def extract_additional_data(self):
        """Extract additional property details."""
        try:
            # Extract house information
            house_status = self._find_field_value(
                FARMLINK_SELECTORS["labels"]["farm_house"])
            if house_status:
                self.data["house_details"] = f"Farm House: {house_status}"

            # Extract description for notes
            desc = self.soup.find(
                **FARMLINK_SELECTORS["property_description"]["container"])
            if desc:
                content = desc.find(
                    **FARMLINK_SELECTORS["property_description"]["content"])
                if content:
                    self.data["notes"] = clean_html_text(
                        content.get_text())[:500] + "..."

            # Extract listing date
            entry_date = self._find_field_value(
                FARMLINK_SELECTORS["labels"]["entry_date"])
            if entry_date:
                self.data["listing_date"] = entry_date

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")
