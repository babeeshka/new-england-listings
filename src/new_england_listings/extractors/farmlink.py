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
        "field_label": {"class_": ["text-color-primary", "text-size-regular", "text-weight-bold"]},
        "field_value": {"class_": ["text-color-primary", "display-inline"]}
    },
    "property_description": {
        "container": {"class_": "info-right_property-description"},
        "content": {"class_": ["text-color-primary", "w-richtext"]}
    },
    "patterns": {
        "price": [
            r"priced at\s*\$?([\d,]+)",
            r"price[d]?:?\s*\$?([\d,]+)",
            r"house.*?-\s*(?:priced at)?\s*\$?([\d,]+)",
            r"business.*?-\s*(?:priced at)?\s*\$?([\d,]+)",
            r"\$\s*([\d,]+)"
        ],
        "acreage": [
            r"(\d+(?:\.\d+)?)\s*acres?",
            r"property\s+(?:is|of)\s*(\d+(?:\.\d+)?)\s*acres?",
            r"(?:approximately|about)\s*(\d+(?:\.\d+)?)\s*acres?"
        ],
        "date": [
            r"Entry\s*Date:\s*(\d{1,2}/\d{1,2}/\d{4})",
            r"Entry\s*Date:\s*(\d{4}-\d{2}-\d{2})"
        ]
    },
    "labels": {
        "county": "ME County:",
        "farm_house": "Farm House:",
        "total_acres": "Total Acres:",
        "entry_date": "Entry Date:"
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

        for section in self.soup.find_all(**FARMLINK_SELECTORS["farm_details"]["container"]):
            # Try finding by label text
            field_elem = section.find(
                string=lambda x: x and label in str(x),
                class_=FARMLINK_SELECTORS["farm_details"]["field_label"]["class_"]
            )
            if field_elem:
                logger.debug(f"Found field element with label: {label}")
                # Try to find value in parent's next sibling
                value_elem = field_elem.find_parent().find_next(
                    class_=FARMLINK_SELECTORS["farm_details"]["field_value"]["class_"])
                if value_elem:
                    value = clean_html_text(value_elem.text)
                    logger.debug(f"Found value: {value}")
                    return value

                # Try finding value in same container
                value_elem = field_elem.find_next(
                    class_=FARMLINK_SELECTORS["farm_details"]["field_value"]["class_"])
                if value_elem:
                    value = clean_html_text(value_elem.text)
                    logger.debug(f"Found value: {value}")
                    return value
        return None

    def extract_listing_name(self) -> str:
        """Extract listing name from URL or page content."""
        farm_id_match = re.search(r'farm-id-(\d+)', self.url)
        if farm_id_match:
            return f"Farm ID {farm_id_match.group(1)}"
        return "Untitled Farm Property"

    def extract_price(self) -> Tuple[str, str]:
        """Extract price information."""
        logger.debug("Extracting price...")

        # Search in property description
        desc = self.soup.find(
            **FARMLINK_SELECTORS["property_description"]["container"])
        if desc:
            content = desc.find(
                **FARMLINK_SELECTORS["property_description"]["content"])
            if content:
                text = content.get_text()
                prices = []

                # Updated price patterns to better match common formats
                price_patterns = [
                    r"priced at\s*\$?([\d,]+)",
                    r"price[d]?:?\s*\$?([\d,]+)",
                    r"(?:house|business|property).*?-.*?\$?([\d,]+)",
                    r"(?:house and business together).*?\$?([\d,]+)",
                    r"\$\s*([\d,]+)"
                ]

                for pattern in price_patterns:
                    matches = re.finditer(pattern, text, re.I)
                    for match in matches:
                        try:
                            price_str = match.group(1).replace(',', '')
                            price_val = float(price_str)
                            if 100000 <= price_val <= 10000000:
                                logger.debug(
                                    f"Found valid price: ${price_val:,.2f}")
                                prices.append(price_val)
                        except (ValueError, IndexError) as e:
                            logger.debug(f"Error parsing price: {e}")
                            continue

                if prices:
                    highest_price = max(prices)
                    price_str = f"${highest_price:,.0f}"
                    price_val = float(str(highest_price).replace(',', ''))
                    if price_val < 300000:
                        bucket = "Under $300K"
                    elif price_val < 600000:
                        bucket = "$300K - $600K"
                    elif price_val < 900000:
                        bucket = "$600K - $900K"
                    elif price_val < 1200000:
                        bucket = "$900K - $1.2M"
                    elif price_val < 1500000:
                        bucket = "$1.2M - $1.5M"
                    elif price_val < 2000000:
                        bucket = "$1.5M - $2M"
                    else:
                        bucket = "$2M+"
                    return price_str, bucket

        return "Contact for Price", "N/A"

    def extract_location(self) -> str:
        """Extract location information."""
        logger.debug("Extracting location...")

        # Try to find county in farm details
        county = self._find_field_value(FARMLINK_SELECTORS["labels"]["county"])
        if county:
            # Clean up the value to just get the county name
            county = clean_html_text(county.replace("ME County:", "").strip())
            logger.debug(f"Found county: {county}")
            return f"{county} County, ME"

        # Try finding in description
        desc = self.soup.find(
            **FARMLINK_SELECTORS["property_description"]["container"])
        if desc:
            content = desc.find(
                **FARMLINK_SELECTORS["property_description"]["content"])
            if content:
                text = content.get_text()
                county_match = re.search(
                    r'(?:in|of)\s+(\w+)\s+county', text, re.I)
                if county_match:
                    county = county_match.group(1)
                    logger.debug(f"Found county in description: {county}")
                    return f"{county} County, ME"

        return "Location Unknown"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information."""
        logger.debug("Extracting acreage...")

        # Try finding in form fields
        acres = self._find_field_value(
            FARMLINK_SELECTORS["labels"]["total_acres"])
        if acres:
            logger.debug(f"Found acreage in fields: {acres}")
            return extract_acreage(f"{acres} acres")

        # Try finding in description
        desc = self.soup.find(
            **FARMLINK_SELECTORS["property_description"]["container"])
        if desc:
            content = desc.find(
                **FARMLINK_SELECTORS["property_description"]["content"])
            if content:
                text = content.get_text()
                # Updated acreage patterns to better match common formats
                acreage_patterns = [
                    r"(?:got|have|contains?)\s*(\d+(?:\.\d+)?)\s*acres?",
                    r"(\d+(?:\.\d+)?)\s*acres?\s*(?:along|all along|of|in|total)",
                    r"property\s+(?:is|of)\s*(\d+(?:\.\d+)?)\s*acres?",
                    r"(?:we'?ve?\s+got)\s*(\d+(?:\.\d+)?)\s*acres?",
                    # Try finding at start of sentences
                    r"^.*?(\d+(?:\.\d+)?)\s*acres?"
                ]

                for pattern in acreage_patterns:
                    match = re.search(pattern, text, re.I)
                    if match:
                        acres = match.group(1)
                        logger.debug(f"Found acreage in description: {acres}")
                        return extract_acreage(f"{acres} acres")

        return "Not specified", "Unknown"

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

            # Get location-based information if location is known
            if self.data.get("location") != "Location Unknown":
                location_info = get_comprehensive_location_info(
                    self.data["location"])
                self.data.update(location_info)

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")
