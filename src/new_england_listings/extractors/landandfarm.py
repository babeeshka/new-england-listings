# src/new_england_listings/extractors/landandfarm.py
from typing import Dict, Any, Tuple
from bs4 import BeautifulSoup
import re
import logging
from .base import BaseExtractor
from ..utils.browser import get_page_content
from ..utils.text import clean_html_text, clean_price, extract_acreage
from ..utils.dates import extract_listing_date
from ..utils.geocoding import parse_location_from_url, get_comprehensive_location_info

logger = logging.getLogger(__name__)

LANDANDFARM_SELECTORS = {
    "title": [
        {"class_": "_2233487"},  # Main title class
        {"tag": "h1"},
        {"class_": "property-title"}
    ],
    "price": [
        {"class_": "cff3611"},  # Direct price class
        {"class_": "_2233487"}  # Title containing price
    ],
    "description": [
        {"class_": "_5ae12cd"},  # Property description class
        {"aria-label": "Property Description"}
    ],
    "property_type": [
        {"class_": "_094c3a5"}  # Property type/subtitle class
    ],
    "features": [
        {"class_": "property-features"},
        {"class_": "property-specs"}
    ]
}


class LandAndFarmExtractor(BaseExtractor):
    """Extractor for Land and Farm listings."""

    @property
    def platform_name(self) -> str:
        return "Land and Farm"

    def extract_listing_name(self) -> str:
        """Extract listing name."""
        logger.debug("Extracting listing name")

        # Try page title first
        if self.soup.title:
            title = self.soup.title.string
            if ' | ' in title:
                name = title.split(' | ')[0].strip()
                logger.debug(f"Found name in title: {name}")
                return name

        # Try each selector
        for selector in LANDANDFARM_SELECTORS["title"]:
            elem = self.soup.find(**selector)
            if elem and elem.text.strip():
                logger.debug(f"Found name in element: {elem.text.strip()}")
                return clean_html_text(elem.text)

        return "Untitled Listing"

    def extract_price(self) -> Tuple[str, str]:
        """Extract price information."""
        logger.debug("Extracting price")

        # Try direct price element first
        price_elem = self.soup.find(class_="cff3611")
        if price_elem:
            logger.debug(f"Found price in direct element: {price_elem.text}")
            return clean_price(price_elem.text)

        # Try title with price
        title_elem = self.soup.find(class_="_2233487")
        if title_elem:
            text = title_elem.text
            logger.debug(f"Found title with price: {text}")
            price_match = re.search(r'\$[\d,]+', text)
            if price_match:
                return clean_price(price_match.group(0))

        # Try description text
        desc_elem = self.soup.find(class_="_5ae12cd")
        if desc_elem:
            text = desc_elem.text
            price_match = re.search(r'\$[\d,]+', text)
            if price_match:
                return clean_price(price_match.group(0))

        return "Contact for Price", "N/A"
    
    def extract_location(self) -> str:
        """Extract location information."""
        logger.debug("Extracting location")

        # Try title first as it contains the full address
        if self.soup.title:
            title = self.soup.title.string
            address_match = re.search(
                r'([\w\s]+,\s*(?:ME|Maine)(?:\s+\d{5})?)', title)
            if address_match:
                location = address_match.group(1)
                logger.debug(f"Found location in title: {location}")
                return location

        # Try selectors
        for selector in LANDANDFARM_SELECTORS["location"]:
            elem = self.soup.find(**selector)
            if elem:
                text = clean_html_text(elem.text)
                if 'ME' in text or 'Maine' in text:
                    logger.debug(f"Found location in element: {text}")
                    return text

        # Try URL parsing
        url_location = parse_location_from_url(self.url)
        if url_location:
            logger.debug(f"Found location in URL: {url_location}")
            return url_location

        return "Location Unknown"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information."""
        logger.debug("Extracting acreage")

        acre_patterns = [
            r'(\d+(?:\.\d+)?)\s*acres?',
            r'Acres?:\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*acre lot',
            r'Lot Size:\s*(\d+(?:\.\d+)?)\s*acres?'
        ]

        # Try in details sections
        for selector in LANDANDFARM_SELECTORS["details"]:
            elem = self.soup.find(**selector)
            if elem:
                text = elem.text
                logger.debug(f"Checking details text: {text[:100]}...")
                for pattern in acre_patterns:
                    match = re.search(pattern, text, re.I)
                    if match:
                        return extract_acreage(f"{match.group(1)} acres")

        # Try all text
        all_text = self.soup.get_text()
        for pattern in acre_patterns:
            match = re.search(pattern, all_text, re.I)
            if match:
                logger.debug(f"Found acreage in text: {match.group(1)} acres")
                return extract_acreage(f"{match.group(1)} acres")

        return "Not specified", "Unknown"

    def extract_additional_data(self):
        """Extract additional property details."""
        try:
            # Extract description
            description = self.soup.find(class_="_5ae12cd")
            if description:
                # Remove copyright notice
                desc_text = description.text
                copyright_index = desc_text.find("Copyright ©")
                if copyright_index != -1:
                    desc_text = desc_text[:copyright_index].strip()
                self.data["notes"] = clean_html_text(desc_text)

            # Extract property type correctly
            type_elem = self.soup.find(class_="_094c3a5")
            if type_elem:
                text = type_elem.text.lower()
                if 'single family' in text:
                    self.data["property_type"] = "Single Family"
                elif 'farm' in text:
                    self.data["property_type"] = "Farm"
                elif 'land' in text:
                    self.data["property_type"] = "Land"

            # Extract house details from description
            if self.data.get("notes"):
                house_details = []

                # Look for common house features in description
                features = {
                    'bedrooms': r'(\d+)(?:-|\s)?bed(?:room)?s?',
                    'bathrooms': r'(?:full |half |primary )?bath(?:room)?s?',
                    'garage': r'(\d+)?(?:-|\s)?car garage',
                    'square feet': r'(\d+,?\d*)\s*sq(?:uare|\.)?\s*(?:ft|feet)',
                    'primary suite': r'primary suite',
                    'fireplace': r'fireplace',
                    'deck': r'deck',
                    'basement': r'basement'
                }

                desc_text = self.data["notes"].lower()
                for feature, pattern in features.items():
                    match = re.search(pattern, desc_text)
                    if match:
                        if match.groups():
                            house_details.append(f"{match.group(1)} {feature}")
                        else:
                            house_details.append(feature)

                if house_details:
                    self.data["house_details"] = " | ".join(house_details)

            # Get location-based information
            if self.data.get("location") != "Location Unknown":
                location_info = get_comprehensive_location_info(
                    self.data["location"])
                self.data.update(location_info)

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")
