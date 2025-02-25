# src/new_england_listings/extractors/farmland.py

from typing import Dict, Any, Tuple, Optional, List
import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup, Tag
from .base import BaseExtractor
from ..models.base import (
    PropertyType, PriceBucket, AcreageBucket,
    DistanceBucket, SchoolRatingCategory, TownPopulationBucket
)
from ..utils.text import clean_html_text, extract_acreage, clean_price, extract_property_type
from ..utils.dates import extract_listing_date
from ..utils.geocoding import get_comprehensive_location_info, parse_location_from_url
from ..config.constants import ACREAGE_BUCKETS

logger = logging.getLogger(__name__)

# Updated selectors for New England Farmland Finder
FARMLAND_SELECTORS = {
    "title": {
        "main": {"class_": ["property-title", "farmland__title", "page-title"]},
        "fallback": {"tag": "h1"}
    },
    "price": {
        "container": {"class_": ["property-price", "pricing-info", "price-section"]},
        "amount": {"class_": ["price-amount", "property-price-value"]},
        "text_patterns": [
            r'(?:Listed|Asking|Price)(?:\s+at)?\s*\$?([\d,]+)',
            r'\$\s*([\d,]+)(?:\s+(?:for|asking|price))?',
            r'(?:lease|rent)(?:\s+of)?\s*\$?([\d,]+)'
        ]
    },
    "details": {
        "container": {"class_": ["property-details", "field-group--columns", "listing-details", "content"]},
        "section": {"class_": ["info-section", "detail-section"]},
        "list": {"class_": ["details-list", "property-features"]},
        "acreage": {"text": ["Total number of acres", "Acreage", "Property size", "Land area", "Total acres"]}
    },
    "location": {
        "container": {"class_": ["property-location", "location-info", "address-section"]},
        "county": {"class_": ["county-name", "property-county"]},
        "address": {"class_": ["property-address", "listing-address"]}
    },
    "agricultural": {
        "cropland": {"text": ["Acres of cropland", "Cropland", "Tillable acres"]},
        "pasture": {"text": ["Acres of pasture", "Pasture", "Grazing land"]},
        "forest": {"text": ["Acres of forested land", "Forest", "Wooded acres"]},
        "soil_quality": {"class_": ["soil-quality", "soil-description"]}
    },
    "amenities": {
        "container": {"class_": ["amenities-list", "property-features", "farm-features"]},
        "water": {"text": ["Water sources", "Water access", "Water features"]},
        "buildings": {"text": ["Farm infrastructure", "Buildings", "Structures"]}
    }
}


class FarmlandExtractionError(Exception):
    """Custom exception for Farmland extraction errors."""
    pass


class FarmlandExtractor(BaseExtractor):
    """Enhanced extractor for Maine Farmland Trust and New England Farmland Finder."""

    def __init__(self, url: str):
        """
        Initialize the farmland extractor with URL and platform-specific flags.

        Args:
            url (str): The URL of the farmland listing
        """
        # Determine platform based on URL
        self.is_mft = "mainefarmlandtrust.org" in url.lower()
        self.is_neff = "newenglandfarmlandfinder.org" in url.lower()

        super().__init__(url)

        # Default type for farmland sites
        self.data["property_type"] = PropertyType.FARM

        # Store URL data for fallbacks
        self.url_data = {}

    @property
    def platform_name(self) -> str:
        """
        Return the platform name based on the URL.

        Returns:
            str: Name of the platform hosting the listing
        """
        return "Maine Farmland Trust" if self.is_mft else "New England Farmland Finder"

    def _verify_page_content(self) -> bool:
        """Verify that the page content was properly loaded."""
        logger.debug("Verifying page content...")

        # Debug the raw HTML
        logger.debug("Raw HTML content:")
        logger.debug(self.soup.prettify()[:1000])  # First 1000 chars

        # Debug all div classes
        logger.debug("Found div classes:")
        for div in self.soup.find_all('div', class_=True):
            logger.debug(f"- {div.get('class')}")

        # Debug all h1 elements
        logger.debug("Found h1 elements:")
        for h1 in self.soup.find_all('h1'):
            logger.debug(f"- {h1.get('class')} : {h1.text.strip()[:100]}")

        # Check for key sections
        sections = [
            ("Main content", self.soup.find("div", class_="field-group--columns")),
            ("Page title", self.soup.find("h1", class_="page-title")),
            ("Property info", self.soup.find(
                string=lambda x: x and "Total number of acres" in str(x))),
            ("Alternate content", self.soup.find("article")),
            ("Basic content", self.soup.find("div", class_="content")),
            ("Farm title", self.soup.find("h1", class_="farmland__title")),
            # Add more general selectors
            ("Any h1", self.soup.find("h1")),
            ("Main div", self.soup.find("div", id="main")),
            ("Content div", self.soup.find(
                "div", class_=lambda x: x and "content" in x.lower())),
        ]

        found_sections = []
        for section_name, section in sections:
            if section:
                logger.debug(
                    f"Found {section_name}: {section.get_text()[:100]}")
                found_sections.append(section_name)

        if not found_sections:
            logger.error("No valid content sections found")
            return False

        logger.info(f"Found content sections: {', '.join(found_sections)}")
        return True

    def _find_with_selector(self, selector_group, selector_name):
        """Helper to find elements with selectors that might have list-based classes."""
        selector = FARMLAND_SELECTORS[selector_group][selector_name]

        # Make a copy to avoid modifying the original
        selector_copy = selector.copy()

        # Handle class_ as list if present
        if "class_" in selector_copy and isinstance(selector_copy["class_"], list):
            # When we have a list of classes, we need to convert it to a string for bs4
            # BeautifulSoup handles space-separated class strings properly
            selector_copy["class_"] = " ".join(selector_copy["class_"])

        # Filter out None values
        clean_selector = {k: v for k,
                          v in selector_copy.items() if v is not None}

        return self.soup.find(**clean_selector) if clean_selector else None

    def _find_with_text(self, container, text_patterns):
        """Find elements based on text content with multiple possible patterns."""
        if not container:
            return None

        # Handle single string or list of strings
        if isinstance(text_patterns, str):
            text_patterns = [text_patterns]

        for pattern in text_patterns:
            element = container.find(
                string=lambda x: x and pattern in str(x))
            if element:
                return element

        return None

    def _extract_from_url(self):
        """Extract information from the URL as a fallback."""
        url_parts = self.url.split('/')[-1].split('-')
        data = {}

        # Try to extract acreage
        acreage_pattern = r'(\d+)[\s-]acres?'
        acreage_match = re.search(acreage_pattern, self.url, re.I)
        if acreage_match:
            data['acreage'] = f"{acreage_match.group(1)} acres"
            acreage_value = float(acreage_match.group(1))
            # Set acreage bucket based on thresholds
            for threshold, bucket in sorted(ACREAGE_BUCKETS.items()):
                if acreage_value < threshold:
                    data['acreage_bucket'] = bucket
                    break
            if 'acreage_bucket' not in data:
                data['acreage_bucket'] = "Extensive (100+ acres)"

        # Try to extract location
        location_indicators = ['in', 'at', 'near']
        county_match = re.search(r'(\w+)[\s-]county', self.url, re.I)
        state_match = re.search(r'[/-]([A-Z]{2})(?:[/-]|$)', self.url)

        location_parts = []
        town_match = None

        # Extract town name from URL
        for i, part in enumerate(url_parts):
            if part.lower() not in ['acres', 'for', 'sale', 'lease', 'rent', 'farmland', 'property']:
                if i > 0 and (url_parts[i-1].lower() in location_indicators or i == len(url_parts) - 3):
                    town_match = part
                    location_parts.append(part.replace('-', ' ').title())

        if county_match:
            location_parts.append(f"{county_match.group(1).title()} County")

        if state_match:
            location_parts.append(state_match.group(1))
        elif "maine" in self.url.lower() or "me" in url_parts:
            location_parts.append("ME")

        if location_parts:
            data['location'] = ', '.join(location_parts)

        # Try to extract property type
        if 'farmland' in self.url.lower():
            data['property_type'] = PropertyType.FARM

        # Try to extract listing name
        if len(url_parts) > 2:
            name_parts = []
            for part in url_parts:
                if part.lower() not in ['acres', 'for', 'sale', 'lease', 'rent', 'county', 'me', 'farmland']:
                    name_parts.append(part.replace('-', ' ').title())
                if len(name_parts) >= 3:  # Limit to first few meaningful parts
                    break

            if name_parts:
                data['listing_name'] = ' '.join(name_parts)

        return data

    def extract(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Main extraction method with content verification."""
        self.soup = soup

        # Verify page content before proceeding
        if not self._verify_page_content():
            logger.error("Failed to get complete page content")
            return self.data

        # Pre-extract URL-based data for fallbacks
        self.url_data = self._extract_from_url()
        logger.debug(f"URL-based fallback data: {self.url_data}")

        # Extract core data directly
        self.data["listing_name"] = self.extract_listing_name()
        self.data["location"] = self.extract_location()
        self.data["price"], self.data["price_bucket"] = self.extract_price()
        self.data["acreage"], self.data["acreage_bucket"] = self.extract_acreage_info()

        # Extract additional platform-specific data
        self.extract_additional_data()

        # Store raw data for debugging
        self.raw_data["url_extracted"] = self.url_data

        return self.data

    def extract_listing_name(self) -> str:
        """Extract the listing name/title with enhanced error handling."""
        logger.debug("Extracting listing name...")

        if self.is_neff:
            # Method 1: First check for farmland__title class
            title_elem = self.soup.find("h1", class_="farmland__title")
            if title_elem:
                title_text = clean_html_text(title_elem.text)
                property_title = title_text  # Store for potential fallback

                # Try to match the farm name pattern
                farm_match = re.match(r'^([^•\-|,]+)', title_text)
                if farm_match:
                    farm_name = farm_match.group(1).strip()
                    logger.debug(f"Extracted farm name: {farm_name}")
                    return farm_name

            # Method 2: Look for farm name in the first part of Additional Information
            additional_info = self.soup.find(
                string=lambda x: x and "Additional Information" in str(x))
            if additional_info:
                info_text = additional_info.find_next("div")
                if info_text:
                    text = clean_html_text(info_text.text)
                    sentences = text.split('.')
                    for sentence in sentences[:2]:  # Check first two sentences
                        if "Farm" in sentence:
                            # Extract just the farm name part
                            farm_name = re.search(
                                r'([^,]+Farm[^,]*)', sentence)
                            if farm_name:
                                logger.debug(
                                    f"Found farm name in description: {farm_name.group(1)}")
                                return farm_name.group(1).strip()

            # Method 3: Try to extract from URL
            if 'listing_name' in self.url_data:
                return self.url_data['listing_name']

            # Method 4: If all else fails, try to use the full property title
            if 'property_title' in locals() and property_title:
                return property_title

            # Try finding h1 with any class
            h1_elem = self.soup.find("h1")
            if h1_elem:
                title_text = clean_html_text(h1_elem.text)
                logger.debug(f"Found title from h1: {title_text}")
                return title_text

            # Final fallback: return default
            return "Untitled Farm Property"

        # Try using newer version's selectors for non-NEFF sites
        title_elem = None

        # Try selectors from FARMLAND_SELECTORS
        title_elem = self._find_with_selector("title", "main")
        if title_elem:
            return clean_html_text(title_elem.text)

        # Try fallback selector
        title_elem = self._find_with_selector("title", "fallback")
        if title_elem:
            return clean_html_text(title_elem.text)

        # Try URL fallback
        if 'listing_name' in self.url_data:
            return self.url_data['listing_name']

        return "Untitled Farm Property"

    def extract_location(self) -> str:
        """Extract location information with enhanced accuracy."""
        logger.debug("Extracting location...")

        if self.is_neff:
            try:
                # Try direct location field first
                location_label = self.soup.find(
                    string=lambda x: x and x.strip() == "Location")
                if location_label:
                    location_value = location_label.find_next("div")
                    if location_value:
                        location = clean_html_text(location_value.text)
                        logger.debug(f"Found location: {location}")
                        if location and any(s in location.upper() for s in ['ME', 'VT', 'NH', 'MA', 'CT', 'RI']):
                            return location

                # If no direct location found, try constructing from URL
                if 'location' in self.url_data:
                    return self.url_data['location']

                # Try location from the title
                title_elem = self.soup.find("h1")
                if title_elem:
                    title_text = title_elem.text
                    location_match = re.search(
                        r'[•\-|,]\s*([^•\-|,]+(?:County|ME|VT|NH|MA|CT|RI)[^•\-|,]*)', title_text)
                    if location_match:
                        location = location_match.group(1).strip()
                        logger.debug(
                            f"Extracted location from title: {location}")
                        return location

            except Exception as e:
                logger.warning(f"Error extracting location: {str(e)}")

        else:
            # Try page-specific selectors first
            for class_name in ["property-location", "location-info", "address-section"]:
                location_container = self.soup.find(class_=class_name)
                if location_container:
                    # Try to extract location text
                    location = clean_html_text(location_container.text)
                    if location and self._validate_location(location):
                        return location

            # Look for county info
            for class_name in ["county-name", "property-county"]:
                county_elem = self.soup.find(class_=class_name)
                if county_elem:
                    county = clean_html_text(county_elem.text)
                    if self._validate_county(county):
                        return f"{county} County, ME"

            # Try URL fallback
            if 'location' in self.url_data:
                return self.url_data['location']

        # Last resort: try to parse location from URL
        location_from_url = parse_location_from_url(self.url)
        if location_from_url:
            return location_from_url

        return "Location Unknown"

    def _validate_county(self, county: str) -> bool:
        """Validate Maine county name."""
        maine_counties = {
            "Androscoggin", "Aroostook", "Cumberland", "Franklin",
            "Hancock", "Kennebec", "Knox", "Lincoln", "Oxford",
            "Penobscot", "Piscataquis", "Sagadahoc", "Somerset",
            "Waldo", "Washington", "York"
        }
        return county.strip() in maine_counties

    def _validate_location(self, location: str) -> bool:
        """Validate location string."""
        if not location:
            return False
        # Check for New England state references
        return bool(re.search(r'(?:ME|Maine|VT|Vermont|NH|New\s+Hampshire|MA|Massachusetts|CT|Connecticut|RI|Rhode\s+Island)\b', location, re.I))

    def extract_price(self) -> Tuple[str, str]:
        """Extract price information with improved reliability."""
        logger.debug("Extracting price...")

        if self.is_neff:
            try:
                # Look for sale price
                price_patterns = [
                    "Sale price",
                    "Price",
                    "Asking price",
                    "Listed for"
                ]

                for pattern in price_patterns:
                    price_elem = self.soup.find(
                        string=lambda x: x and pattern in str(x))
                    if price_elem:
                        price_value = price_elem.find_next("div")
                        if price_value:
                            price_text = price_value.text.strip()
                            logger.debug(f"Found price: {price_text}")
                            return clean_price(price_text)

                # Check for lease information
                lease_elem = self.soup.find(
                    string=lambda x: x and "lease" in str(x).lower())
                if lease_elem:
                    logger.debug("Found lease information")
                    return "Contact for Lease Terms", "N/A"

            except Exception as e:
                logger.warning(f"Error extracting price: {str(e)}")

        else:
            # Try using the new selectors from FARMLAND_SELECTORS
            try:
                # First look for price tags
                for class_name in ["property-price", "pricing-info", "price-section"]:
                    price_container = self.soup.find(class_=class_name)
                    if price_container:
                        # Try direct price amount
                        for amount_class in ["price-amount", "property-price-value"]:
                            price_elem = price_container.find(
                                class_=amount_class)
                            if price_elem:
                                return clean_price(price_elem.text)

                        # Try text patterns
                        text = price_container.get_text()
                        for pattern in FARMLAND_SELECTORS["price"]["text_patterns"]:
                            match = re.search(pattern, text, re.I)
                            if match:
                                return clean_price(match.group(1))

                # Try finding price in any details section
                for class_name in ["property-details", "field-group--columns", "listing-details"]:
                    details_section = self.soup.find(class_=class_name)
                    if details_section:
                        text = details_section.get_text()
                        for pattern in FARMLAND_SELECTORS["price"]["text_patterns"]:
                            match = re.search(pattern, text, re.I)
                            if match:
                                return clean_price(match.group(1))

                # Check for lease terms in the page text
                page_text = self.soup.get_text().lower()
                if 'lease' in page_text or 'rent' in page_text:
                    lease_patterns = [
                        r'(?:lease|rent)(?:\s+for)?\s*\$?([\d,]+)(?:\s+per|\s*/|\s+a)?\s*(?:year|month|acre)',
                        r'(?:annual|monthly)(?:\s+lease|rent)(?:\s+of)?\s*\$?([\d,]+)',
                        r'\$\s*([\d,]+)(?:\s+per|\s*/|\s+a)?\s*(?:year|month|acre)'
                    ]

                    for pattern in lease_patterns:
                        match = re.search(pattern, page_text)
                        if match:
                            return clean_price(match.group(1))

                    # If we found lease terms but no price, note it's a lease
                    return "Lease - Contact for Price", PriceBucket.NA

            except Exception as e:
                logger.warning(f"Error extracting price: {str(e)}")

        return "Contact for Price", PriceBucket.NA

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information with improved accuracy."""
        logger.debug("Starting acreage extraction...")

        if self.is_neff:
            try:
                total_acres = 0.0
                acreage_found = False

                # First try to find total acreage
                total_elem = self.soup.find(
                    string=lambda x: x and "Total number of acres" in str(x))
                if total_elem:
                    total_value = total_elem.find_next("div")
                    if total_value:
                        try:
                            total_acres = float(
                                clean_html_text(total_value.text))
                            acreage_found = True
                        except ValueError:
                            logger.warning(
                                "Could not convert total acreage to float")

                # If no total found, sum individual fields
                if not acreage_found:
                    acreage_fields = {
                        "cropland": "Acres of cropland",
                        "pasture": "Acres of pasture",
                        "forest": "Acres of forested land"
                    }

                    for field_type, search_text in acreage_fields.items():
                        field_elem = self.soup.find(
                            string=lambda x: x and search_text in str(x))
                        if field_elem:
                            value_elem = field_elem.find_next("div")
                            if value_elem:
                                try:
                                    acres = float(
                                        clean_html_text(value_elem.text))
                                    total_acres += acres
                                    acreage_found = True
                                except ValueError:
                                    logger.warning(
                                        f"Could not convert {field_type} acreage to float")

                if acreage_found:
                    formatted_acres = f"{total_acres:.1f} acres"
                    # Determine bucket
                    for threshold, bucket in sorted(ACREAGE_BUCKETS.items()):
                        if total_acres < threshold:
                            return formatted_acres, bucket
                    return formatted_acres, "Extensive (100+ acres)"

                # Try to extract from URL as fallback
                if 'acreage' in self.url_data:
                    return self.url_data['acreage'], self.url_data.get('acreage_bucket', "Unknown")

                # Try to extract from title
                title_elem = self.soup.find("h1")
                if title_elem:
                    title_text = title_elem.text
                    acreage_match = re.search(
                        r'(\d+(?:\.\d+)?)\s*acres?', title_text, re.I)
                    if acreage_match:
                        acres = float(acreage_match.group(1))
                        formatted_acres = f"{acres:.1f} acres"
                        # Determine bucket
                        for threshold, bucket in sorted(ACREAGE_BUCKETS.items()):
                            if acres < threshold:
                                return formatted_acres, bucket
                        return formatted_acres, "Extensive (100+ acres)"

            except Exception as e:
                logger.warning(f"Error extracting acreage details: {str(e)}")

        else:
            try:
                # Try the new version's approach
                # Try to extract from URL first if not found in the page
                acreage_from_url = None
                if 'acreage' in self.url_data:
                    acreage_from_url = self.url_data['acreage']

                # Try extraction from page content
                total_acres = 0.0
                details = None
                for class_name in ["property-details", "field-group--columns", "listing-details", "content"]:
                    details = self.soup.find(class_=class_name)
                    if details:
                        break

                if details:
                    # Try with various acreage text patterns
                    acreage_patterns = FARMLAND_SELECTORS["details"]["acreage"]["text"]
                    if isinstance(acreage_patterns, str):
                        acreage_patterns = [acreage_patterns]

                    for pattern in acreage_patterns:
                        acreage_elem = details.find(
                            string=lambda x: x and pattern in str(x))
                        if acreage_elem:
                            # Try to find the value near this element
                            parent = acreage_elem.find_parent()
                            if parent:
                                # Look for value in next sibling or div
                                value_elem = parent.find_next(
                                    "div") or parent.find_next_sibling() or parent.parent.find_next("div")
                                if value_elem:
                                    return extract_acreage(value_elem.text)

                                # If no dedicated element, try the parent text
                                parent_text = parent.get_text()
                                acres_match = re.search(
                                    r'(\d+(?:\.\d+)?)\s*acres?', parent_text, re.I)
                                if acres_match:
                                    return extract_acreage(acres_match.group(0))

                    # If not found with standard patterns, try a more generic approach
                    acres_pattern = re.compile(
                        r'(\d+(?:\.\d+)?)\s*acres?', re.I)
                    for tag in details.find_all(['p', 'div', 'span', 'li']):
                        match = acres_pattern.search(tag.get_text())
                        if match:
                            return extract_acreage(match.group(0))

                    # Try heading tags for acreage
                    for heading in self.soup.find_all(['h1', 'h2', 'h3']):
                        match = acres_pattern.search(heading.get_text())
                        if match:
                            return extract_acreage(match.group(0))

                # If we didn't find acreage in the page content, use URL extraction as fallback
                if acreage_from_url:
                    return extract_acreage(acreage_from_url)

                # Try whole page search as a last resort
                page_text = self.soup.get_text()
                acres_match = re.search(
                    r'(\d+(?:\.\d+)?)\s*acres?', page_text, re.I)
                if acres_match:
                    return extract_acreage(acres_match.group(0))

            except Exception as e:
                logger.error(f"Error extracting acreage: {str(e)}")
                # Try URL fallback on exception
                if 'acreage' in self.url_data:
                    return self.url_data['acreage'], self.url_data.get('acreage_bucket', "Unknown")

        return "Not specified", "Unknown"

    def extract_additional_data(self):
        """Extract comprehensive property details."""
        # Use super's extract_additional_data first
        try:
            super().extract_additional_data()
        except Exception as e:
            logger.warning(f"Base additional data extraction error: {str(e)}")

        if self.is_neff:
            try:
                logger.debug(
                    "Extracting additional New England Farmland Finder data...")
                self._extract_basic_details()
                self._extract_acreage_details()
                self._extract_farm_details()
                self._extract_property_features()
                self._extract_dates()

                # Get location-based information
                if self.data.get("location") != "Location Unknown":
                    try:
                        location_info = get_comprehensive_location_info(
                            self.data["location"])
                        # Only update fields that aren't already set
                        for key, value in location_info.items():
                            if key not in self.data or not self.data[key]:
                                self.data[key] = value
                    except Exception as e:
                        logger.warning(
                            f"Error getting location info: {str(e)}")

            except Exception as e:
                logger.error(f"Error in additional data extraction: {str(e)}")
                logger.debug("Exception details:", exc_info=True)
        else:
            # Use the newer extraction method for agricultural details
            try:
                # Extract agricultural details
                ag_details = self.extract_agricultural_details()
                self.raw_data["agricultural_details"] = ag_details

                # Format farm details
                farm_details = []
                if ag_details.get("soil_quality"):
                    farm_details.append(f"Soil: {ag_details['soil_quality']}")
                if ag_details.get("water_sources"):
                    farm_details.append(
                        f"Water: {ag_details['water_sources']}")
                if ag_details.get("infrastructure"):
                    farm_details.append(
                        f"Infrastructure: {ag_details['infrastructure']}")

                if farm_details:
                    self.data["farm_details"] = " | ".join(farm_details)

                # Process location information
                if self.data["location"] != "Location Unknown":
                    try:
                        location_info = get_comprehensive_location_info(
                            self.data["location"])
                        if location_info:
                            self._process_location_info(location_info)
                    except Exception as e:
                        logger.error(
                            f"Error processing location info: {str(e)}")
            except Exception as e:
                logger.error(
                    f"Error in agricultural data extraction: {str(e)}")

    def _extract_basic_details(self):
        """Extract basic property details."""
        self.data["property_type"] = "Farm"

        # Extract owner type
        owner_elem = self.soup.find(
            string=lambda x: x and "Property owner" in str(x))
        if owner_elem:
            owner_value = owner_elem.find_next("div")
            if owner_value:
                self.data["owner_type"] = clean_html_text(owner_value.text)

    def _extract_acreage_details(self):
        """Extract detailed acreage information."""
        acreage_fields = {
            "Total acres": "Total number of acres",
            "Cropland": "Acres of cropland",
            "Pasture": "Acres of pasture",
            "Forest": "Acres of forested land"
        }

        acreage_details = []
        for field_name, search_text in acreage_fields.items():
            field_elem = self.soup.find(
                string=lambda x: x and search_text in str(x))
            if field_elem:
                value_elem = field_elem.find_next("div")
                if value_elem:
                    value = clean_html_text(value_elem.text)
                    try:
                        acres = float(value)
                        if field_name == "Total acres":
                            self.data["acreage"] = f"{acres:.1f} acres"
                            # Set acreage bucket based on thresholds
                            for threshold, bucket in sorted(ACREAGE_BUCKETS.items()):
                                if acres < threshold:
                                    self.data["acreage_bucket"] = bucket
                                    break
                        acreage_details.append(f"{field_name}: {value} acres")
                    except ValueError:
                        logger.warning(
                            f"Could not convert acreage to float: {value}")

        if acreage_details:
            self.data["acreage_details"] = " | ".join(acreage_details)

    def _extract_farm_details(self):
        """Extract detailed farm infrastructure and features."""
        farm_details = []

        # Infrastructure details
        infra_elem = self.soup.find(
            string=lambda x: x and "Farm infrastructure details" in str(x))
        if infra_elem:
            details = infra_elem.find_next("div")
            if details:
                farm_details.append(
                    f"Infrastructure: {clean_html_text(details.text)}")

        # Water sources
        water_elem = self.soup.find(
            string=lambda x: x and "Water sources details" in str(x))
        if water_elem:
            water_details = water_elem.find_next("div")
            if water_details:
                farm_details.append(
                    f"Water Sources: {clean_html_text(water_details.text)}")

        # Equipment details
        equipment_elem = self.soup.find(
            string=lambda x: x and "Equipment and machinery details" in str(x))
        if equipment_elem:
            equipment_details = equipment_elem.find_next("div")
            if equipment_details:
                farm_details.append(
                    f"Equipment: {clean_html_text(equipment_details.text)}")

        # Housing details
        housing_elem = self.soup.find(
            string=lambda x: x and "Farmer housing details" in str(x))
        if housing_elem:
            housing_details = housing_elem.find_next("div")
            if housing_details:
                self.data["house_details"] = clean_html_text(
                    housing_details.text)

        if farm_details:
            self.data["farm_details"] = " | ".join(farm_details)

    def _extract_property_features(self):
        """Extract additional property features and characteristics."""
        features = []

        # Check for organic certification
        organic_elem = self.soup.find(
            string=lambda x: x and "certified organic" in str(x).lower())
        if organic_elem:
            organic_value = organic_elem.find_next("div")
            if organic_value:
                features.append(
                    f"Organic Status: {clean_html_text(organic_value.text)}")

        # Check for conservation easement
        easement_elem = self.soup.find(
            string=lambda x: x and "Conservation Easement" in str(x))
        if easement_elem:
            easement_details = easement_elem.find_next("div")
            if easement_details:
                features.append(
                    f"Conservation Easement: {clean_html_text(easement_details.text)}")

        # Check for forest management plan
        forest_elem = self.soup.find(
            string=lambda x: x and "forest management plan" in str(x).lower())
        if forest_elem:
            forest_details = forest_elem.find_next("div")
            if forest_details:
                features.append(
                    f"Forest Management: {clean_html_text(forest_details.text)}")

        if features:
            self.data["property_features"] = " | ".join(features)

    def _extract_dates(self):
        """Extract listing dates and other temporal information."""
        # Posted date
        date_elem = self.soup.find(
            string=lambda x: x and "Date posted" in str(x))
        if date_elem:
            date_value = date_elem.find_next("div")
            if date_value:
                self.data["listing_date"] = clean_html_text(date_value.text)

        # Any additional dates (availability, etc.)
        availability_elem = self.soup.find(
            string=lambda x: x and "Date available" in str(x))
        if availability_elem:
            avail_value = availability_elem.find_next("div")
            if avail_value:
                self.data["available_date"] = clean_html_text(avail_value.text)

    def extract_agricultural_details(self) -> Dict[str, Any]:
        """Extract detailed agricultural information."""
        try:
            details = {}
            details_container = None
            for class_name in ["property-details", "field-group--columns", "listing-details", "content"]:
                details_container = self.soup.find(class_=class_name)
                if details_container:
                    break

            if details_container:
                # Extract soil quality
                soil_quality_class = FARMLAND_SELECTORS["agricultural"]["soil_quality"]["class_"]
                if isinstance(soil_quality_class, list):
                    soil_quality_class = " ".join(soil_quality_class)
                soil_elem = details_container.find(class_=soil_quality_class)
                if soil_elem:
                    details["soil_quality"] = clean_html_text(soil_elem.text)

                # Extract water sources
                water_patterns = FARMLAND_SELECTORS["amenities"]["water"]["text"]
                if isinstance(water_patterns, str):
                    water_patterns = [water_patterns]

                for pattern in water_patterns:
                    water_elem = details_container.find(
                        string=lambda x: x and pattern in str(x)
                    )
                    if water_elem:
                        parent = water_elem.find_parent()
                        if parent:
                            value_elem = parent.find_next("div")
                            if value_elem:
                                details["water_sources"] = clean_html_text(
                                    value_elem.text)
                                break

                # Extract infrastructure
                building_patterns = FARMLAND_SELECTORS["amenities"]["buildings"]["text"]
                if isinstance(building_patterns, str):
                    building_patterns = [building_patterns]

                for pattern in building_patterns:
                    buildings_elem = details_container.find(
                        string=lambda x: x and pattern in str(x)
                    )
                    if buildings_elem:
                        parent = buildings_elem.find_parent()
                        if parent:
                            value_elem = parent.find_next("div")
                            if value_elem:
                                details["infrastructure"] = clean_html_text(
                                    value_elem.text)
                                break

            return details

        except Exception as e:
            logger.error(f"Error extracting agricultural details: {str(e)}")
            return {}

    def _process_location_info(self, location_info: Dict[str, Any]):
        """Process location information with Farmland specific logic."""
        # Call the base implementation first
        super()._process_location_info(location_info)

        try:
            # Farmland specific processing
            # Handle soil quality data that might be specific to farmland
            if 'soil_quality_rating' in location_info:
                self.data["soil_quality_rating"] = float(
                    location_info["soil_quality_rating"])

            # Process agricultural zone data
            if 'agricultural_zone' in location_info:
                self.data["agricultural_zone"] = location_info["agricultural_zone"]

            # Process water rights data
            if 'water_rights' in location_info:
                self.data["water_rights"] = location_info["water_rights"]

        except Exception as e:
            logger.error(
                f"Error processing Farmland-specific location info: {str(e)}")

    def _get_distance_bucket(self, distance: float) -> str:
        """Convert distance to appropriate bucket enum."""
        if distance <= 10:
            return DistanceBucket.UNDER_10
        elif distance <= 20:
            return DistanceBucket.TO_20
        elif distance <= 40:
            return DistanceBucket.TO_40
        elif distance <= 60:
            return DistanceBucket.TO_60
        elif distance <= 80:
            return DistanceBucket.TO_80
        else:
            return DistanceBucket.OVER_80

    def _get_population_bucket(self, population: int) -> str:
        """Convert population to appropriate bucket enum."""
        if population < 5000:
            return TownPopulationBucket.VERY_SMALL
        elif population < 15000:
            return TownPopulationBucket.SMALL
        elif population < 50000:
            return TownPopulationBucket.MEDIUM
        elif population < 100000:
            return TownPopulationBucket.LARGE
        else:
            return TownPopulationBucket.VERY_LARGE

    def _get_school_rating_category(self, rating: float) -> str:
        """Convert school rating to appropriate category enum."""
        if rating <= 3:
            return SchoolRatingCategory.POOR
        elif rating <= 5:
            return SchoolRatingCategory.BELOW_AVERAGE
        elif rating <= 7:
            return SchoolRatingCategory.AVERAGE
        elif rating <= 9:
            return SchoolRatingCategory.ABOVE_AVERAGE
        else:
            return SchoolRatingCategory.EXCELLENT

    def extract_house_details(self) -> Optional[str]:
        """Extract house-specific details if present."""
        try:
            details = []
            details_container = None
            for class_name in ["property-details", "field-group--columns", "listing-details", "content"]:
                details_container = self.soup.find(class_=class_name)
                if details_container:
                    break

            if details_container:
                # Look for housing section
                housing_elem = details_container.find(
                    string=lambda x: x and "Farmer housing" in str(x))
                if housing_elem:
                    parent = housing_elem.find_parent()
                    if parent:
                        value_elem = parent.find_next("div")
                        if value_elem:
                            text = clean_html_text(value_elem.text)

                            # Extract specific details
                            bed_match = re.search(r'(\d+)\s*bed', text, re.I)
                            bath_match = re.search(
                                r'(\d+(?:\.\d+)?)\s*bath', text, re.I)
                            sqft_match = re.search(
                                r'(\d+(?:,\d+)?)\s*sq(?:uare)?\s*ft', text, re.I)

                            if bed_match:
                                details.append(f"{bed_match.group(1)} bedroom")
                            if bath_match:
                                details.append(
                                    f"{bath_match.group(1)} bathroom")
                            if sqft_match:
                                details.append(f"{sqft_match.group(1)} sqft")

                            # Add additional features
                            features = []
                            if "basement" in text.lower():
                                features.append("Basement")
                            if "garage" in text.lower():
                                features.append("Garage")
                            if "porch" in text.lower() or "deck" in text.lower():
                                features.append("Outdoor space")

                            if features:
                                details.extend(features)

            return " | ".join(details) if details else None

        except Exception as e:
            logger.error(f"Error extracting house details: {str(e)}")
            return None

    def extract_amenities(self) -> List[str]:
        """Extract property amenities and features."""
        try:
            amenities = set()
            container = None
            for class_name in ["amenities-list", "property-features", "farm-features"]:
                container = self.soup.find(class_=class_name)
                if container:
                    break

            if container:
                # Extract listed amenities
                for item in container.find_all("li"):
                    amenity = clean_html_text(item.text)
                    if amenity:
                        amenities.add(amenity)

                # Look for specific features in text
                text = container.get_text().lower()
                feature_keywords = {
                    "irrigation": "Irrigation system",
                    "fenced": "Fenced areas",
                    "greenhouse": "Greenhouse",
                    "solar": "Solar power",
                    "well": "Well water",
                    "spring": "Natural spring",
                    "pond": "Pond",
                    "stream": "Stream"
                }

                for keyword, feature in feature_keywords.items():
                    if keyword in text:
                        amenities.add(feature)

            return list(amenities)

        except Exception as e:
            logger.error(f"Error extracting amenities: {str(e)}")
            return []
