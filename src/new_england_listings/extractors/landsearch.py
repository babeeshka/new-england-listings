# src/new_england_listings/extractors/landsearch.py

from typing import Dict, Any, Tuple, Optional
import re
import logging
from urllib.parse import urlparse
from datetime import datetime
from bs4 import BeautifulSoup
from .base import BaseExtractor
from ..models.base import (
    PropertyType, PriceBucket, AcreageBucket,
    DistanceBucket, SchoolRatingCategory, TownPopulationBucket
)
from ..utils.text import clean_html_text, extract_acreage, clean_price
from ..utils.dates import extract_listing_date
from ..utils.geocoding import get_comprehensive_location_info
from ..config.constants import ACREAGE_BUCKETS

logger = logging.getLogger(__name__)

LANDSEARCH_SELECTORS = {
    "title": {
        "container": {"class_": "property-title"},
        "heading": {"tag": "h1"},
    },
    "price": {
        "container": {"class_": "property-price"},
        "amount": {"class_": "price-amount"},
    },
    "details": {
        "container": {"class_": "property-details"},
        "section": {"class_": "detail-section"},
        "acreage": {"class_": "property-acreage"},
        "features": {"class_": "property-features"},
        "description": {"class_": "property-description"},
    },
    "location": {
        "container": {"class_": "property-location"},
        "address": {"class_": "full-address"},
        "city": {"class_": "city"},
        "state": {"class_": "state"},
    },
    "metadata": {
        "container": {"class_": "property-metadata"},
        "date": {"class_": "listing-date"},
    }
}


class LandSearchExtractionError(Exception):
    """Custom exception for LandSearch extraction errors."""
    pass


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
            self.soup.find(**LANDSEARCH_SELECTORS["price"]["container"]),
            self.soup.find(**LANDSEARCH_SELECTORS["details"]["container"]),
            self.soup.find(**LANDSEARCH_SELECTORS["location"]["container"])
        ]

        return any(essential_elements)

    def extract_listing_name(self) -> str:
        """Extract listing name/title."""
        # Try to get from title container first
        title_container = self.soup.find(
            **LANDSEARCH_SELECTORS["title"]["container"])
        if title_container:
            heading = title_container.find(
                **LANDSEARCH_SELECTORS["title"]["heading"])
            if heading:
                return clean_html_text(heading.text)

        # Fallback to page title
        if self.soup.title:
            title = self.soup.title.string
            if "LandSearch" in title:
                return title.split(" - LandSearch")[0].strip()

        # Last resort - construct from URL
        path = urlparse(self.url).path
        if path:
            parts = path.split('/')
            if len(parts) > 2:
                return parts[-2].replace('-', ' ').title()

        return "Untitled Listing"

    def extract_price(self) -> Tuple[str, str]:
        """Extract price and determine price bucket."""
        price_container = self.soup.find(
            **LANDSEARCH_SELECTORS["price"]["container"])
        if price_container:
            # Try specific price amount element first
            price_elem = price_container.find(
                **LANDSEARCH_SELECTORS["price"]["amount"])
            if price_elem:
                return clean_price(price_elem.text)
            # Fallback to container text
            if '$' in price_container.text:
                return clean_price(price_container.text)

        # Try searching in full text for price patterns
        text = self.soup.get_text()
        price_patterns = [
            r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*dollars',
            r'listed\s+(?:for|at)\s+\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'price[d]?\s+at\s+\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)'
        ]

        for pattern in price_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return clean_price(match.group(1))

        return "Contact for Price", "N/A"

    def extract_location(self) -> str:
        """Extract property location."""
        location_container = self.soup.find(
            **LANDSEARCH_SELECTORS["location"]["container"])
        if location_container:
            # Try to get full address
            full_address = location_container.find(
                **LANDSEARCH_SELECTORS["location"]["address"])
            if full_address:
                return clean_html_text(full_address.text)

            # Try to combine city and state
            location_parts = []
            city_elem = location_container.find(
                **LANDSEARCH_SELECTORS["location"]["city"])
            if city_elem:
                location_parts.append(clean_html_text(city_elem.text))
            state_elem = location_container.find(
                **LANDSEARCH_SELECTORS["location"]["state"])
            if state_elem:
                location_parts.append(clean_html_text(state_elem.text))

            if location_parts:
                return ", ".join(location_parts)

        # Try to extract from URL
        path = urlparse(self.url).path
        location_match = re.search(r'/([^/]+)-(?:me|maine)-\d+', path, re.I)
        if location_match:
            location = location_match.group(1).replace('-', ' ').title()
            return f"{location}, ME"

        # Try to extract from title
        if self.soup.title:
            title = self.soup.title.string
            location_match = re.search(r'in\s+([^,]+),\s+(ME|Maine)', title)
            if location_match:
                return f"{location_match.group(1)}, {location_match.group(2)}"

        return "Location Unknown"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information."""
        # Try to find acreage in title first
        if self.soup.title:
            title_text = self.soup.title.string
            acres_match = re.search(
                r'(\d+(?:\.\d+)?)\s*Acres?', title_text, re.I)
            if acres_match:
                return extract_acreage(f"{acres_match.group(1)} acres")

        # Look for acreage in property details
        details = self.soup.find(
            **LANDSEARCH_SELECTORS["details"]["container"])
        if details:
            # Try specific acreage section
            acreage_elem = details.find(
                **LANDSEARCH_SELECTORS["details"]["acreage"])
            if acreage_elem:
                return extract_acreage(acreage_elem.text)

            # Search in all detail sections
            for section in details.find_all(**LANDSEARCH_SELECTORS["details"]["section"]):
                text = clean_html_text(section.text)
                if 'acre' in text.lower():
                    acres_match = re.search(
                        r'(\d+(?:\.\d+)?)\s*acres?', text, re.I)
                    if acres_match:
                        return extract_acreage(f"{acres_match.group(1)} acres")

        return "Not specified", "Unknown"

    def extract_additional_data(self):
        """Extract additional property details."""
        try:
            # Initialize raw_data
            self.raw_data = {
                "details": {},
                "location": {},
                "price": {},
                "history": {}
            }

            # Extract detailed attributes
            attributes_section = self.soup.find(
                'section', {'class': 'accordion__section', 'data-type': 'attributes'})
            if attributes_section:
                details = []

                # Process each attribute column
                for column in attributes_section.find_all('section', {'class': 'property-info__column'}):
                    title = column.find('h3')
                    if title:
                        section_name = title.text.strip()
                        definitions = column.find_all(
                            'div', {'class': 'definitions__group'})
                        for def_group in definitions:
                            dt = def_group.find('dt')
                            dd = def_group.find('dd')
                            if dt and dd:
                                key = dt.text.strip()
                                value = dd.text.strip()
                                detail = f"{section_name} - {key}: {value}"
                                details.append(detail)
                                # Store in raw_data as well
                                self.raw_data["details"][f"{section_name} - {key}"] = value
                                # Also store in simplified format
                                self.raw_data["details"][key] = value

                if details:
                    self.data["house_details"] = " | ".join(details)

            # Extract price (already set by extract_price)
            price_container = self.soup.find(
                **LANDSEARCH_SELECTORS["price"]["container"])
            if price_container:
                self.raw_data["price"]["text"] = price_container.text.strip()

            # Extract location (already set by extract_location)
            location_container = self.soup.find(
                **LANDSEARCH_SELECTORS["location"]["container"])
            if location_container:
                full_address = location_container.find(
                    **LANDSEARCH_SELECTORS["location"]["address"])
                if full_address:
                    self.raw_data["location"]["full_address"] = clean_html_text(
                        full_address.text)

            # Extract property description for notes
            description = self.soup.find(
                'div', {'class': 'property-description'})
            if description:
                self.data["notes"] = clean_html_text(description.get_text())

            # Extract property type from raw data
            if "Type" in self.raw_data["details"]:
                type_text = self.raw_data["details"]["Type"]
                if "residential" in type_text.lower():
                    self.data["property_type"] = "Single Family"
                elif "farm" in type_text.lower() or "agricultural" in type_text.lower():
                    self.data["property_type"] = "Farm"
                elif "land" in type_text.lower() or "lot" in type_text.lower():
                    self.data["property_type"] = "Land"
                elif "commercial" in type_text.lower():
                    self.data["property_type"] = "Commercial"
                else:
                    self.data["property_type"] = type_text
            elif "Subtype" in self.raw_data["details"]:
                subtype = self.raw_data["details"]["Subtype"]
                if "single family" in subtype.lower():
                    self.data["property_type"] = "Single Family"
                elif "farm" in subtype.lower():
                    self.data["property_type"] = "Farm"
                else:
                    self.data["property_type"] = subtype

            # Extract features as amenities
            features = [v for k, v in self.raw_data["details"].items()
                        if any(x in k.lower() for x in ["feature", "material", "roof"])]
            if features:
                self.data["other_amenities"] = " | ".join(features)

            # Process listing history
            history_section = self.soup.find(
                'section', {'class': 'accordion__section', 'data-type': 'updates'})
            if history_section:
                table = history_section.find('table')
                if table:
                    history = []
                    rows = table.find_all('tr')[1:]  # Skip header
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 3:
                            date = cells[0].text.strip()
                            event = cells[1].text.strip()
                            price = cells[2].text.strip()
                            history.append(f"{date}: {event} - {price}")

                    if history:
                        # Set price history
                        self.raw_data["history"]["events"] = history

                        # Extract listing date directly from the table
                        for row in rows:
                            cells = row.find_all('td')
                            if len(cells) >= 2:
                                event = cells[1].text.strip()
                                if event == "New listing":
                                    date_str = cells[0].text.strip()
                                    try:
                                        date_obj = datetime.strptime(
                                            date_str, "%b %d, %Y")
                                        self.data["listing_date"] = date_obj
                                        break
                                    except Exception as e:
                                        logger.warning(
                                            f"Could not parse listing date: {date_str} - {str(e)}")

                        # If no "New listing" found, try first date
                        if "listing_date" not in self.data and rows:
                            first_row_cells = rows[0].find_all('td')
                            if first_row_cells:
                                date_str = first_row_cells[0].text.strip()
                                try:
                                    date_obj = datetime.strptime(
                                        date_str, "%b %d, %Y")
                                    self.data["listing_date"] = date_obj
                                except Exception as e:
                                    logger.warning(
                                        f"Could not parse first date: {date_str} - {str(e)}")

            # Get location-based information if location is known
            if self.data.get("location") != "Location Unknown":
                try:
                    location_info = get_comprehensive_location_info(
                        self.data["location"])
                    if location_info:
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

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")
