# src/new_england_listings/extractors/farmlink.py
from typing import Dict, Any, Tuple, Optional, Union, List
import re
import logging
import random
import time
from datetime import datetime
from bs4 import BeautifulSoup
from .base import BaseExtractor
from ..models.base import PropertyType, PriceBucket, AcreageBucket
from ..utils.text import clean_price, clean_html_text, extract_acreage
from ..utils.dates import extract_listing_date, parse_date_string
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
        self.data["platform"] = "Maine FarmLink"
        self.data["property_type"] = PropertyType.FARM

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

        # Try extracting from URL
        farm_id = re.search(r'farm-id-(\d+)', self.url)
        if farm_id:
            # Some heuristic mapping of farm IDs to counties if known
            farm_id_map = {
                # Example mapping - fill in with known values if available
                "3741": "Aroostook County, ME",
                "3742": "Cumberland County, ME"
            }
            farm_id_str = farm_id.group(1)
            if farm_id_str in farm_id_map:
                return farm_id_map[farm_id_str]

        return "Location Unknown"

    def extract_price(self) -> Tuple[str, PriceBucket]:
        """Extract price information from property description."""
        logger.debug("Extracting price...")

        # Try getting price directly from field
        price_value = self._find_field_value(
            FARMLINK_SELECTORS["labels"]["price"])
        if price_value:
            logger.debug(f"Found price in fields: {price_value}")
            # Extract numeric value from price field
            price_match = re.search(r'\$?([\d,]+)', price_value)
            if price_match:
                return clean_price(price_match.group(1))

        # Find the property description container
        desc = self.soup.find(
            **FARMLINK_SELECTORS["property_description"]["container"])
        if desc:
            content = desc.find(
                **FARMLINK_SELECTORS["property_description"]["content"])
            if content:
                text = content.get_text()

                # Store all found prices
                prices = []

                # Look for specific price patterns
                price_patterns = [
                    # Combined property pattern
                    r'(?:house\s+and\s+business\s+together|property\s+and\s+business)\s*-?\s*(?:priced\s+at)?\s*\$?([\d,]+)',
                    # House only pattern
                    r'house\s+only\s*-?\s*(?:priced\s+at)?\s*\$?([\d,]+)',
                    # Business only pattern
                    r'business\s+only\s*-?\s*(?:priced\s+at)?\s*\$?([\d,]+)',
                    # General price patterns
                    r'priced\s+at\s*\$?([\d,]+)',
                    r'price(?:d)?:?\s*\$?([\d,]+)',
                    r'asking\s*\$?([\d,]+)',
                    r'\$\s*([\d,]+)(?:\s+(?:for|asking|price))?'
                ]

                for pattern in price_patterns:
                    matches = re.finditer(pattern, text, re.I)
                    for match in matches:
                        try:
                            price_str = match.group(1).replace(',', '')
                            price_val = float(price_str)
                            if 100000 <= price_val <= 10000000:  # Reasonable range for farm properties
                                logger.debug(f"Found price: ${price_val:,.2f}")
                                prices.append(price_val)
                        except (ValueError, IndexError) as e:
                            logger.debug(f"Error parsing price: {e}")
                            continue

                if prices:
                    # Get the highest price if multiple are found
                    # This assumes the combined property price would be highest
                    highest_price = max(prices)
                    price_str = f"${highest_price:,.0f}"

                    # Set price bucket based on the highest price
                    if highest_price < 300000:
                        bucket = PriceBucket.UNDER_300K
                    elif highest_price < 600000:
                        bucket = PriceBucket.TO_600K
                    elif highest_price < 900000:
                        bucket = PriceBucket.TO_900K
                    elif highest_price < 1200000:
                        bucket = PriceBucket.TO_1_2M
                    elif highest_price < 1500000:
                        bucket = PriceBucket.TO_1_5M
                    elif highest_price < 2000000:
                        bucket = PriceBucket.TO_2M
                    else:
                        bucket = PriceBucket.OVER_2M

                    # Add note about multiple prices if found
                    if len(prices) > 1:
                        price_details = []
                        if re.search(r'business\s+only.*?\$[\d,]+', text, re.I):
                            price_details.append(
                                f"Business Only: ${min(prices):,.0f}")
                        if re.search(r'house\s+only.*?\$[\d,]+', text, re.I):
                            # Find the middle price if there are 3 prices
                            house_price = sorted(prices)[1] if len(
                                prices) == 3 else min(prices)
                            price_details.append(
                                f"House Only: ${house_price:,.0f}")

                        if price_details:
                            self.data["notes"] = f"Multiple pricing options available: {', '.join(price_details)}. " + (
                                self.data.get("notes", "") or "")

                    return price_str, bucket

        return "Contact for Price", PriceBucket.NA

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

    def extract_acreage_info(self) -> Tuple[str, AcreageBucket]:
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

        return "Not specified", AcreageBucket.UNKNOWN

    def extract_amenities(self) -> List[str]:
        """Extract farm amenities from description."""
        amenities = []

        # Amenity keywords to look for
        farm_amenities = {
            "pasture": "Pasture land",
            "cropland": "Cropland",
            "forest": "Forested land",
            "barn": "Barn",
            "outbuilding": "Outbuildings",
            "greenhouse": "Greenhouse",
            "irrigation": "Irrigation system",
            "well": "Well water",
            "solar": "Solar power",
            "equipment": "Farm equipment",
            "fenced": "Fenced areas",
            "pond": "Pond",
            "stream": "Stream or creek",
            "orchard": "Orchard"
        }

        # Look in description
        desc = self.soup.find(
            **FARMLINK_SELECTORS["property_description"]["container"])
        if desc:
            content = desc.find(
                **FARMLINK_SELECTORS["property_description"]["content"])
            if content:
                text = content.get_text().lower()

                # Check for each amenity
                for keyword, amenity in farm_amenities.items():
                    if keyword in text:
                        amenities.append(amenity)

        return amenities

    def extract(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Main extraction method."""
        logger.debug(f"Starting extraction for {self.platform_name}")
        self.soup = soup
        self.raw_data = {}

        # Extract basic information
        self.data["listing_name"] = self.extract_listing_name()
        self.data["location"] = self.extract_location()
        self.data["price"], self.data["price_bucket"] = self.extract_price()
        self.data["acreage"], self.data["acreage_bucket"] = self.extract_acreage_info()

        # Extract additional data
        self.extract_additional_data()

        # Extract amenities
        amenities = self.extract_amenities()
        if amenities:
            self.data["other_amenities"] = " | ".join(amenities)

        # If we have a valid location, get comprehensive location info
        if self.data["location"] != "Location Unknown":
            try:
                location_info = get_comprehensive_location_info(
                    self.data["location"])
                if location_info:
                    # Process location info
                    for key, value in location_info.items():
                        # Handle special case for school_rating (convert "X/10" to float)
                        if key == "school_rating" and isinstance(value, str) and "/" in value:
                            try:
                                self.data[key] = float(value.split("/")[0])
                            except ValueError:
                                logger.warning(
                                    f"Could not convert school_rating: {value}")
                        else:
                            self.data[key] = value
            except Exception as e:
                logger.error(f"Error getting location info: {str(e)}")

        # Store raw data for debugging
        self.data["raw_data"] = self.raw_data

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
                    full_text = clean_html_text(content.get_text())
                    # Keep full description but limit for preview
                    if len(full_text) > 500:
                        self.data["notes"] = full_text[:497] + "..."
                    else:
                        self.data["notes"] = full_text

            # Extract listing date
            entry_date = self._find_field_value(
                FARMLINK_SELECTORS["labels"]["entry_date"])
            if entry_date:
                try:
                    date_str = parse_date_string(entry_date)
                    if date_str:
                        self.data["listing_date"] = datetime.strptime(
                            date_str, '%Y-%m-%d')
                except Exception as e:
                    logger.warning(f"Error parsing listing date: {str(e)}")

            # Extract property type if different from default "Farm"
            property_type = self._find_field_value(
                FARMLINK_SELECTORS["labels"]["property_type"])
            if property_type:
                if "farmland" in property_type.lower():
                    self.data["property_type"] = PropertyType.FARM
                elif "house" in property_type.lower() or "residential" in property_type.lower():
                    self.data["property_type"] = PropertyType.SINGLE_FAMILY
                elif "commercial" in property_type.lower():
                    self.data["property_type"] = PropertyType.COMMERCIAL
                elif "land" in property_type.lower():
                    self.data["property_type"] = PropertyType.LAND

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")
