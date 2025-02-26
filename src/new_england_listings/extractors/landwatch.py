# src/new_england_listings/extractors/landwatch.py

"""
LandWatch specific extractor implementation.
"""

from typing import Dict, Any, Tuple, Optional, List
from bs4 import BeautifulSoup
import re
import logging
import random
import time
import traceback
from datetime import datetime

from .base import BaseExtractor
from ..utils.text import TextProcessor
from ..utils.dates import DateExtractor
from ..utils.location_service import LocationService
from ..models.base import PropertyType

logger = logging.getLogger(__name__)

LANDWATCH_SELECTORS = {
    "title": {
        "main": {"class_": "property-title", "tag": "h1"},
        "alt": {"id": "listing-title"}
    },
    "price": {
        "main": {"class_": "price"},
        "alt": {"class_": "listing-price"},
        "patterns": [
            r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*dollars',
            r'listed\s+(?:for|at)\s+\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'price[d]?\s+at\s+\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)'
        ]
    },
    "location": {
        "main": {"class_": "location"},
        "alt": {"class_": "listing-address"}
    },
    "details": {
        "container": {"class_": "listing-details"},
        "section": {"class_": "details-section"},
        "features": {"class_": "property-features"},
        "description": {"class_": "description-text"}
    },
    "metadata": {
        "listing_id": {"class_": "listing-id"},
        "date": {"class_": "listing-date"}
    }
}


class LandWatchExtractor(BaseExtractor):
    """Enhanced extractor for LandWatch listings."""

    @property
    def platform_name(self) -> str:
        return "LandWatch"

    def _verify_page_content(self) -> bool:
        """Verify the page content was properly loaded."""
        logger.debug("Verifying page content...")

        # Check for blocking indicators (common on LandWatch)
        page_text = self.soup.get_text().lower()
        blocking_indicators = [
            "captcha",
            "security check",
            "please verify",
            "access denied",
            "robot"
        ]

        if any(indicator in page_text for indicator in blocking_indicators):
            logger.warning("Potential blocking detected on LandWatch")
            return False

        # Check for minimal valid content
        if len(self.soup.get_text()) < 500:  # Very little content
            logger.warning("Insufficient page content")
            return False

        # Check for key elements
        crucial_elements = [
            self.soup.find("h1"),  # Should have a title
            self.soup.find(class_="listing-details")  # Should have details
        ]

        return any(crucial_elements)

    def extract_listing_name(self) -> str:
        """Extract listing name/title."""
        try:
            # Try main title selector
            title_elem = self.soup.find(**LANDWATCH_SELECTORS["title"]["main"])
            if title_elem:
                return TextProcessor.clean_html_text(title_elem.text)

            # Try alternative title selector
            alt_title = self.soup.find(**LANDWATCH_SELECTORS["title"]["alt"])
            if alt_title:
                return TextProcessor.clean_html_text(alt_title.text)

            # Look for any h1
            h1 = self.soup.find("h1")
            if h1:
                return TextProcessor.clean_html_text(h1.text)

            # Try to extract from meta tags
            meta_title = self.soup.find("meta", property="og:title")
            if meta_title and meta_title.get("content"):
                return meta_title["content"]

            # Fallback to URL-based title
            url_parts = self.url.split('/')
            if len(url_parts) > 3:
                return url_parts[-2].replace('-', ' ').title()

            return "Untitled Listing"

        except Exception as e:
            logger.error(f"Error extracting listing name: {str(e)}")
            return "Untitled Listing"

    def extract_price(self) -> Tuple[str, str]:
        """Extract price information."""
        try:
            # Try main price element
            price_elem = self.soup.find(**LANDWATCH_SELECTORS["price"]["main"])
            if price_elem:
                return self.text_processor.standardize_price(price_elem.text)

            # Try alternative price element
            alt_price = self.soup.find(**LANDWATCH_SELECTORS["price"]["alt"])
            if alt_price:
                return self.text_processor.standardize_price(alt_price.text)

            # Search in full text for price patterns
            text = self.soup.get_text()
            for pattern in LANDWATCH_SELECTORS["price"]["patterns"]:
                match = re.search(pattern, text, re.I)
                if match:
                    price_text = f"${match.group(1)}" if not match.group(
                        1).startswith('$') else match.group(1)
                    return self.text_processor.standardize_price(price_text)

            return "Contact for Price", "N/A"

        except Exception as e:
            logger.error(f"Error extracting price: {str(e)}")
            return "Contact for Price", "N/A"

    def extract_location(self) -> str:
        """Extract property location."""
        try:
            # Try main location element
            location_elem = self.soup.find(
                **LANDWATCH_SELECTORS["location"]["main"])
            if location_elem:
                return TextProcessor.clean_html_text(location_elem.text)

            # Try alternative location element
            alt_location = self.soup.find(
                **LANDWATCH_SELECTORS["location"]["alt"])
            if alt_location:
                return TextProcessor.clean_html_text(alt_location.text)

            # Try meta tags
            meta_location = self.soup.find("meta", property="og:locality")
            if meta_location and meta_location.get("content"):
                region = self.soup.find("meta", property="og:region")
                region_text = region.get("content") if region else ""
                if region_text:
                    return f"{meta_location['content']}, {region_text}"
                return meta_location["content"]

            # Try to extract from URL
            url_parts = self.url.split('/')
            for part in url_parts:
                if 'county' in part.lower():
                    county = re.sub(r'-county.*', '',
                                    part).replace('-', ' ').title()
                    state = next((s for s in ['vermont', 'maine', 'new-hampshire', 'massachusetts', 'connecticut', 'rhode-island']
                                 if s in self.url.lower()), "")
                    if state:
                        state_abbr = {
                            'vermont': 'VT',
                            'maine': 'ME',
                            'new-hampshire': 'NH',
                            'massachusetts': 'MA',
                            'connecticut': 'CT',
                            'rhode-island': 'RI'
                        }.get(state, "")
                        return f"{county} County, {state_abbr}"
                    return f"{county} County"

            # Parse from title if location isn't found elsewhere
            title = self.extract_listing_name()
            for state in ['Vermont', 'Maine', 'New Hampshire', 'Massachusetts', 'Connecticut', 'Rhode Island']:
                if state in title:
                    return state

            for abbr in ['VT', 'ME', 'NH', 'MA', 'CT', 'RI']:
                if abbr in title:
                    return abbr

            return "Location Unknown"

        except Exception as e:
            logger.error(f"Error extracting location: {str(e)}")
            return "Location Unknown"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information."""
        try:
            # Look for acreage in description or details
            details = self.soup.find(
                **LANDWATCH_SELECTORS["details"]["container"])
            description = ""

            if details:
                description = details.get_text()
            else:
                # Try alternative description element
                desc_elem = self.soup.find(
                    **LANDWATCH_SELECTORS["details"]["description"])
                if desc_elem:
                    description = desc_elem.get_text()

            if description:
                # Look for acreage patterns
                acreage_patterns = [
                    r'(\d+(?:\.\d+)?)\s*acres?',
                    r'(\d+(?:\.\d+)?)\s*acre lot',
                    r'(\d+(?:\.\d+)?)\s*acre parcel',
                    r'property\s+(?:is|of)\s*(\d+(?:\.\d+)?)\s*acres?',
                    r'lot\s+size[:\s]*(\d+(?:\.\d+)?)\s*acres?'
                ]

                for pattern in acreage_patterns:
                    match = re.search(pattern, description, re.I)
                    if match:
                        return self.text_processor.standardize_acreage(f"{match.group(1)} acres")

            # Try to extract from page title
            if self.soup.title:
                title_text = self.soup.title.string
                acres_match = re.search(
                    r'(\d+(?:\.\d+)?)\s*Acres?', title_text, re.I)
                if acres_match:
                    return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

            # Try to extract from the URL
            for part in self.url.split('/'):
                if 'acre' in part.lower():
                    match = re.search(r'(\d+(?:\.\d+)?)-acres?', part.lower())
                    if match:
                        return self.text_processor.standardize_acreage(f"{match.group(1)} acres")

            return "Not specified", "Unknown"

        except Exception as e:
            logger.error(f"Error extracting acreage: {str(e)}")
            return "Not specified", "Unknown"

    def extract_property_details(self) -> Dict[str, Any]:
        """Extract comprehensive property details."""
        try:
            details = {}

            # Get description text
            description = ""
            desc_elem = self.soup.find(
                **LANDWATCH_SELECTORS["details"]["description"])
            if desc_elem:
                description = desc_elem.get_text()
            else:
                # Try looking in details container
                details_container = self.soup.find(
                    **LANDWATCH_SELECTORS["details"]["container"])
                if details_container:
                    description = details_container.get_text()

            if description:
                # Look for property features
                features_patterns = {
                    "water": ["water", "well", "spring", "creek", "river", "stream", "pond", "lake"],
                    "power": ["electric", "power", "utilities"],
                    "road": ["road", "access", "driveway"],
                    "terrain": ["wooded", "field", "pasture", "meadow", "forest", "cleared", "flat", "rolling", "mountain"],
                    "structures": ["house", "cabin", "building", "barn", "garage", "shed"]
                }

                found_features = []
                for category, keywords in features_patterns.items():
                    for keyword in keywords:
                        if re.search(r'\b' + keyword + r'\b', description, re.I):
                            context_match = re.search(
                                r'[^.!?]*\b' + keyword + r'\b[^.!?]*', description, re.I)
                            if context_match:
                                found_features.append(
                                    context_match.group(0).strip())
                                break  # Only include one feature per category

                if found_features:
                    details["features"] = found_features

                # Try to extract property type
                type_keywords = {
                    "Single Family": ["home", "house", "cabin", "residence", "cottage"],
                    "Land": ["land", "lot", "acreage", "vacant", "undeveloped", "raw land"],
                    "Farm": ["farm", "ranch", "agricultural", "pasture", "farmland", "orchard"],
                    "Commercial": ["commercial", "business", "retail", "store", "office", "industrial"]
                }

                for prop_type, keywords in type_keywords.items():
                    if any(re.search(r'\b' + keyword + r'\b', description, re.I) for keyword in keywords):
                        details["property_type"] = prop_type
                        break

            # Extract listing ID if available
            id_elem = self.soup.find(
                **LANDWATCH_SELECTORS["metadata"]["listing_id"])
            if id_elem:
                details["listing_id"] = TextProcessor.clean_html_text(
                    id_elem.text)

            return details

        except Exception as e:
            logger.error(f"Error extracting property details: {str(e)}")
            return {}

    def extract_additional_data(self):
        """Extract all additional property information."""
        try:
            # Use the parent method first
            super().extract_additional_data()

            # Get additional property details
            details = self.extract_property_details()

            # Set property type if found
            if "property_type" in details:
                self.data["property_type"] = details["property_type"]

            # Format features for amenities
            if "features" in details:
                existing_amenities = self.data.get("other_amenities", "")
                new_amenities = " | ".join(details["features"])

                if existing_amenities:
                    self.data["other_amenities"] = f"{existing_amenities} | {new_amenities}"
                else:
                    self.data["other_amenities"] = new_amenities

            # Try to extract listing date
            date_elem = self.soup.find(
                **LANDWATCH_SELECTORS["metadata"]["date"])
            if date_elem:
                date_text = TextProcessor.clean_html_text(date_elem.text)
                date_str = DateExtractor.extract_date_from_text(date_text)
                if date_str:
                    self.data["listing_date"] = date_str

            # Process description for notes field
            desc_elem = self.soup.find(
                **LANDWATCH_SELECTORS["details"]["description"])
            if desc_elem:
                description = TextProcessor.clean_html_text(
                    desc_elem.get_text())
                if description:
                    self.data["notes"] = description

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")
            self.raw_data["extraction_error"] = str(e)
