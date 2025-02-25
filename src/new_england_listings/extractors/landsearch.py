"""
LandSearch-specific extractor implementation.
"""

from typing import Dict, Any, Tuple, Optional
import re
import logging
from urllib.parse import urlparse
from datetime import datetime
from bs4 import BeautifulSoup
import traceback

from .base import BaseExtractor
from ..utils.text import clean_html_text, extract_property_type
from ..utils.dates import extract_listing_date, parse_date_string

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
        logger.debug("Verifying LandSearch page content...")

        # Debug content
        logger.debug("Found elements:")
        for section, selectors in LANDSEARCH_SELECTORS.items():
            for name, selector in selectors.items():
                elem = self.soup.find(
                    **selector if isinstance(selector, dict) else {'class_': selector})
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
            heading = title_container.find('h1') or title_container.find('h2')
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
                return self.text_processor.standardize_price(price_elem.text)
            # Fallback to container text
            if '$' in price_container.text:
                return self.text_processor.standardize_price(price_container.text)

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
                price_text = f"${match.group(1)}" if not match.group(
                    1).startswith('$') else match.group(1)
                return self.text_processor.standardize_price(price_text)

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
        for state in ['me', 'nh', 'vt', 'ma', 'ct', 'ri']:
            location_match = re.search(f'/([^/]+)-({state})-\\d+', path, re.I)
            if location_match:
                location = location_match.group(1).replace('-', ' ').title()
                state_code = location_match.group(2).upper()
                return f"{location}, {state_code}"

        # Try to extract from title
        if self.soup.title:
            title = self.soup.title.string
            for state_code in ['ME', 'NH', 'VT', 'MA', 'CT', 'RI']:
                location_match = re.search(
                    f'in\\s+([^,]+),\\s+({state_code}|{state_code.lower()})', title, re.I)
                if location_match:
                    return f"{location_match.group(1)}, {state_code}"

        return "Location Unknown"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information."""
        # Try to find acreage in title first
        if self.soup.title:
            title_text = self.soup.title.string
            acres_match = re.search(
                r'(\d+(?:\.\d+)?)\s*Acres?', title_text, re.I)
            if acres_match:
                return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

        # Look for acreage in property details
        details = self.soup.find(
            **LANDSEARCH_SELECTORS["details"]["container"])
        if details:
            # Try specific acreage section
            acreage_elem = details.find(
                **LANDSEARCH_SELECTORS["details"]["acreage"])
            if acreage_elem:
                return self.text_processor.standardize_acreage(acreage_elem.text)

            # Search in all detail sections
            for section in details.find_all(**LANDSEARCH_SELECTORS["details"]["section"]):
                text = clean_html_text(section.text)
                if 'acre' in text.lower():
                    acres_match = re.search(
                        r'(\d+(?:\.\d+)?)\s*acres?', text, re.I)
                    if acres_match:
                        return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

        # Try looking for acreage in the full text
        full_text = self.soup.get_text()
        acreage_patterns = [
            r'(\d+(?:\.\d+)?)\s*acres?',
            r'property\s*size[:\s]*(\d+(?:\.\d+)?)\s*acres?',
            r'lot\s*size[:\s]*(\d+(?:\.\d+)?)\s*acres?',
            r'parcel\s*size[:\s]*(\d+(?:\.\d+)?)\s*acres?'
        ]

        for pattern in acreage_patterns:
            acres_match = re.search(pattern, full_text, re.I)
            if acres_match:
                return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

        return "Not specified", "Unknown"

    def extract_additional_data(self):
        """Extract additional property details with enhanced location processing."""
        try:
            # Use the parent class's additional data extraction first to get basic fields
            super().extract_additional_data()

            # Extract detailed attributes
            try:
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
                                    self.raw_data["details"] = self.raw_data.get(
                                        "details", {})
                                    self.raw_data["details"][f"{section_name} - {key}"] = value
                                    # Also store in simplified format
                                    self.raw_data["details"][key] = value

                    if details:
                        self.data["house_details"] = " | ".join(details)

                # Extract property description for notes
                description = self.soup.find(
                    'div', {'class': 'property-description'})
                if description:
                    self.data["notes"] = clean_html_text(description.get_text())

                # Extract property type from raw data
                property_type_value = "Unknown"
                if "Type" in self.raw_data.get("details", {}):
                    type_text = self.raw_data["details"]["Type"]
                    if "residential" in type_text.lower():
                        property_type_value = "Single Family"
                    elif "farm" in type_text.lower() or "agricultural" in type_text.lower():
                        property_type_value = "Farm"
                    elif "land" in type_text.lower() or "lot" in type_text.lower():
                        property_type_value = "Land"
                    elif "commercial" in type_text.lower():
                        property_type_value = "Commercial"
                    else:
                        property_type_value = type_text
                elif "Subtype" in self.raw_data.get("details", {}):
                    subtype = self.raw_data["details"]["Subtype"]
                    if "single family" in subtype.lower():
                        property_type_value = "Single Family"
                    elif "farm" in subtype.lower():
                        property_type_value = "Farm"
                    else:
                        property_type_value = subtype

                # Use the determined property type
                if property_type_value != "Unknown":
                    self.data["property_type"] = property_type_value

                # Try to parse the listing date from history or metadata
                try:
                    history_section = self.soup.find(
                        'section', {'class': 'accordion__section', 'data-type': 'updates'})
                    if history_section:
                        table = history_section.find('table')
                        if table:
                            rows = table.find_all('tr')[1:]  # Skip header
                            for row in rows:
                                cells = row.find_all('td')
                                if len(cells) >= 2:
                                    event = cells[1].text.strip()
                                    if event == "New listing":
                                        date_str = cells[0].text.strip()
                                        try:
                                            from dateutil import parser
                                            date_obj = parser.parse(date_str)
                                            self.data["listing_date"] = date_obj
                                            break
                                        except Exception as e:
                                            logger.warning(
                                                f"Could not parse listing date: {date_str} - {str(e)}")
                except Exception as e:
                    logger.warning(f"Error parsing history: {str(e)}")

                # Process location after extracting all property details
                if self.data["location"] and self.data["location"] != "Location Unknown":
                    # Get comprehensive location info
                    location_info = self.location_service.get_comprehensive_location_info(
                        self.data["location"])

                    # Map fields to our data structure with defaults for essential fields
                    field_mapping = {
                        'distance_to_portland': ('distance_to_portland', None),
                        'portland_distance_bucket': ('portland_distance_bucket', None),
                        # Default population
                        'town_population': ('town_population', 10000),
                        # Default population bucket
                        'town_pop_bucket': ('town_pop_bucket', "Medium (15K-50K)"),
                        'school_district': ('school_district', "Nearby School District"),
                        # Default average rating
                        'school_rating': ('school_rating', 6.0),
                        'school_rating_cat': ('school_rating_cat', "Average (6-7)"),
                        # Default distance
                        'hospital_distance': ('hospital_distance', 20.0),
                        'hospital_distance_bucket': ('hospital_distance_bucket', "21-40"),
                        'closest_hospital': ('closest_hospital', "Nearby Hospital"),
                        # At least 1
                        'restaurants_nearby': ('restaurants_nearby', 1),
                        # At least 1
                        'grocery_stores_nearby': ('grocery_stores_nearby', 1),
                        'other_amenities': ('other_amenities', None),
                        'regional_context': ('regional_context', None),
                        'state': ('state', "ME"),
                        'state_full': ('state_full', "Maine")
                    }

                    # Apply all mapped fields with defaults as fallback
                    for source_field, (target_field, default_value) in field_mapping.items():
                        if source_field in location_info and location_info[source_field] is not None:
                            self.data[target_field] = location_info[source_field]
                        elif default_value is not None and (target_field not in self.data or self.data[target_field] is None):
                            self.data[target_field] = default_value

                    # Ensure we always have restaurants and grocery stores
                    if self.data.get('restaurants_nearby') is None:
                        self.data['restaurants_nearby'] = 1
                    if self.data.get('grocery_stores_nearby') is None:
                        self.data['grocery_stores_nearby'] = 1

                    # Clean up duplicate values in other_amenities
                    if self.data.get('other_amenities'):
                        amenities = self.data['other_amenities'].split(' | ')
                        unique_amenities = []
                        seen = set()
                        for amenity in amenities:
                            if amenity not in seen:
                                seen.add(amenity)
                                unique_amenities.append(amenity)
                        self.data['other_amenities'] = ' | '.join(unique_amenities)

                # Handle case when we don't have location info but still need defaults
                else:
                    # Set reasonable defaults for critical fields
                    defaults = {
                        'restaurants_nearby': 1,
                        'grocery_stores_nearby': 1,
                        'school_district': "Nearby School District",
                        'school_rating': 6.0,
                        'school_rating_cat': "Average (6-7)",
                        'hospital_distance': 20.0,
                        'hospital_distance_bucket': "21-40",
                        'closest_hospital': "Nearby Hospital"
                    }

                    for field, value in defaults.items():
                        if field not in self.data or self.data[field] is None:
                            self.data[field] = value

            except Exception as e:
                logger.error(
                    f"Error in LandSearch additional data extraction: {str(e)}")
                logger.error(traceback.format_exc())

                # Even if we have an error, ensure critical fields have values
                critical_fields = {
                    'restaurants_nearby': 1,
                    'grocery_stores_nearby': 1,
                    'town_population': 10000,
                    'town_pop_bucket': "Medium (15K-50K)",
                    'school_district': "Nearby School District",
                    'school_rating': 6.0,
                    'school_rating_cat': "Average (6-7)",
                    'hospital_distance': 20.0,
                    'hospital_distance_bucket': "21-40",
                    'closest_hospital': "Nearby Hospital"
                }

                for field, default_value in critical_fields.items():
                    if field not in self.data or self.data[field] is None:
                        self.data[field] = default_value

        except Exception as outer_e:
            logger.error(
                f"Outer error in additional data extraction: {str(outer_e)}")
            self.raw_data['additional_data_extraction_error'] = str(outer_e)

    def _extract_house_details(self) -> Optional[str]:
        """
        Extract house-specific details for LandSearch.
        
        Returns:
            Optional string of house details
        """
        details = []

        # Check for room counts in raw data
        if "Room Count" in self.raw_data.get("details", {}):
            details.append(
                f"Room Count: {self.raw_data['details']['Room Count']}")

        if "Rooms" in self.raw_data.get("details", {}):
            details.append(f"Rooms: {self.raw_data['details']['Rooms']}")

        # Look for bedroom and bathroom counts
        rooms_text = self.raw_data.get("details", {}).get("Rooms", "")
        if rooms_text:
            bedroom_match = re.search(r'Bedroom\s*x\s*(\d+)', rooms_text)
            if bedroom_match:
                details.append(f"{bedroom_match.group(1)} bedrooms")

            bathroom_match = re.search(r'Bathroom\s*x\s*(\d+)', rooms_text)
            if bathroom_match:
                details.append(f"{bathroom_match.group(1)} bathrooms")

        # Add structural details
        if "Structure - Materials" in self.raw_data.get("details", {}):
            details.append(
                f"Materials: {self.raw_data['details']['Structure - Materials']}")

        if "Structure - Roof" in self.raw_data.get("details", {}):
            details.append(
                f"Roof: {self.raw_data['details']['Structure - Roof']}")

        if "Structure - Heating" in self.raw_data.get("details", {}):
            details.append(
                f"Heating: {self.raw_data['details']['Structure - Heating']}")

        # If we have details, return them joined
        if details:
            return " | ".join(details)

        # Otherwise fall back to the parent implementation
        return super()._extract_house_details()

    def _extract_farm_details(self) -> Optional[str]:
        """
        Override the parent method to properly extract farm details for LandSearch listings.
        
        Returns:
            Optional string of farm details or None if not a farm property
        """
        # Skip farm details for non-farm properties
        if self.data.get("property_type") != "Farm":
            return None

        details = []

        # Only look in the main content area
        main_content = self.soup.find('div', {'class': 'property-description'})
        if not main_content:
            main_content = self.soup.find('div', {'class': 'content'})

        if main_content:
            # Look for farm-related keywords in the description
            text = main_content.get_text().lower()
            farm_keywords = [
                "farm", "agricultural", "cropland", "pasture", "tillable",
                "barn", "silo", "irrigation", "livestock", "organic", "soil"
            ]

            # Extract sentences containing farm keywords
            sentences = re.split(r'(?<=[.!?])\s+', text)
            for sentence in sentences:
                if any(keyword in sentence for keyword in farm_keywords):
                    details.append(sentence.strip().capitalize())

            # Limit to 3 most relevant details
            if details:
                return " | ".join(details[:3])

        return None
