"""
Land and Farm specific extractor implementation.
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
from ..models.base import PropertyType

logger = logging.getLogger(__name__)

LANDANDFARM_SELECTORS = {
    "title": {
        "main": {"class_": "_2233487"},
        "subtitle": {"class_": "_094c3a5"},
        "details": {"class_": "cff3611"}
    },
    "price": {
        "main": {"class_": "cff3611"},
        "alternate": {"class_": "_2233487"},
        "patterns": [
            r'\$[\d,]+(?:\.\d{2})?',
            r'(?:price|listed at|asking)\s*\$[\d,]+(?:\.\d{2})?',
            r'[\d,]+(?:\.\d{2})?\s*dollars'
        ]
    },
    "location": {
        "container": {"class_": "location-container"},
        "address": {"class_": "property-address"},
        "city": {"class_": "city-name"},
        "state": {"class_": "state-name"}
    },
    "description": {
        "main": {"class_": "_5ae12cd"},
        "section": {"aria-label": "Property Description"}
    },
    "details": {
        "container": {"class_": "property-details"},
        "sections": {"class_": "details-section"},
        "features": {"class_": "property-features"},
        "specs": {"class_": "property-specs"}
    },
    "metadata": {
        "date": {"class_": "listing-date"},
        "source": {"class_": "listing-source"}
    }
}


class LandAndFarmExtractor(BaseExtractor):
    """Enhanced extractor for Land and Farm listings."""

    @property
    def platform_name(self) -> str:
        return "Land and Farm"

    def _verify_page_content(self) -> bool:
        """Verify the page content was properly loaded."""
        logger.debug("Verifying page content...")

        # Debug the raw HTML
        logger.debug("Raw HTML content:")
        logger.debug(self.soup.prettify()[:1000])  # First 1000 chars

        # Debug all div classes
        logger.debug("Found div classes:")
        for div in self.soup.find_all('div', class_=True):
            logger.debug(f"- {div.get('class')}")

        # Check for essential elements
        essential_sections = {
            "Title": self.soup.find(**LANDANDFARM_SELECTORS["title"]["main"]),
            "Price": self.soup.find(**LANDANDFARM_SELECTORS["price"]["main"]),
            "Description": self.soup.find(**LANDANDFARM_SELECTORS["description"]["main"]),
            "Details": self.soup.find(**LANDANDFARM_SELECTORS["details"]["container"])
        }

        logger.debug("Essential sections found:")
        for name, element in essential_sections.items():
            logger.debug(f"{name}: {element is not None}")

        # If we have title or page title, consider page valid
        if self.soup.title or self.soup.find(**LANDANDFARM_SELECTORS["title"]["main"]):
            return True

        return any(essential_sections.values())

    def extract_listing_name(self) -> str:
        """Extract listing name with enhanced validation."""
        try:
            # Try main title first
            title_elem = self.soup.find(
                **LANDANDFARM_SELECTORS["title"]["main"])
            if title_elem:
                title = TextProcessor.clean_html_text(title_elem.text)
                if title:
                    self.raw_data["title"] = title
                    return title

            # Try page title
            if self.soup.title:
                title = self.soup.title.string
                if " | " in title:
                    title = title.split(" | ")[0].strip()
                    if title:
                        return title

            # Try constructing from URL
            url_parts = self.url.split('/')[-1].split('-')
            if len(url_parts) > 3:
                location_parts = [p.capitalize() for p in url_parts[:-2]]
                return " ".join(location_parts)

            return "Untitled Listing"

        except Exception as e:
            logger.error(f"Error extracting listing name: {str(e)}")
            return "Untitled Listing"

    def extract_price(self) -> Tuple[str, str]:
        """Extract price with enhanced validation."""
        try:
            # Try direct price element
            price_elem = self.soup.find(
                **LANDANDFARM_SELECTORS["price"]["main"])
            if price_elem:
                self.raw_data["price_text"] = price_elem.text
                return self.text_processor.standardize_price(price_elem.text)

            # Try alternate price sources
            alt_elem = self.soup.find(
                **LANDANDFARM_SELECTORS["price"]["alternate"])
            if alt_elem:
                text = alt_elem.text
                for pattern in LANDANDFARM_SELECTORS["price"]["patterns"]:
                    match = re.search(pattern, text)
                    if match:
                        return self.text_processor.standardize_price(match.group(0))

            # Try description text
            desc_elem = self.soup.find(
                **LANDANDFARM_SELECTORS["description"]["main"])
            if desc_elem:
                text = desc_elem.text
                for pattern in LANDANDFARM_SELECTORS["price"]["patterns"]:
                    match = re.search(pattern, text)
                    if match:
                        return self.text_processor.standardize_price(match.group(0))

            # Try title for price
            title_elem = self.soup.find(
                **LANDANDFARM_SELECTORS["title"]["main"])
            if title_elem:
                text = title_elem.text
                price_match = re.search(r'\$\s*([\d,]+)', text)
                if price_match:
                    return self.text_processor.standardize_price(price_match.group(1))

            return "Contact for Price", "N/A"

        except Exception as e:
            logger.error(f"Error extracting price: {str(e)}")
            return "Contact for Price", "N/A"

    def extract_location(self) -> str:
        """Extract location with enhanced validation."""
        try:
            # Try location container first
            location_container = self.soup.find(
                **LANDANDFARM_SELECTORS["location"]["container"])
            if location_container:
                # Try full address
                address = location_container.find(
                    **LANDANDFARM_SELECTORS["location"]["address"])
                if address:
                    location = TextProcessor.clean_html_text(address.text)
                    if self._validate_location(location):
                        return location

                # Try city and state combination
                city = location_container.find(
                    **LANDANDFARM_SELECTORS["location"]["city"])
                state = location_container.find(
                    **LANDANDFARM_SELECTORS["location"]["state"])
                if city and state:
                    location = f"{TextProcessor.clean_html_text(city.text)}, {TextProcessor.clean_html_text(state.text)}"
                    if self._validate_location(location):
                        return location

            # Try extracting from title if other methods failed
            title_elem = self.soup.find(
                **LANDANDFARM_SELECTORS["title"]["main"])
            if title_elem:
                title_text = title_elem.text
                location_match = re.search(
                    r'in\s+([\w\s]+),\s+([A-Z]{2})', title_text)
                if location_match:
                    city, state = location_match.groups()
                    location = f"{city.strip()}, {state.strip()}"
                    if self._validate_location(location):
                        return location

            # Try extracting from page title
            if self.soup.title:
                title_text = self.soup.title.string
                if " | " in title_text:
                    title_parts = title_text.split(" | ")
                    if len(title_parts) > 1:
                        location_part = title_parts[1]
                        if self._validate_location(location_part):
                            return location_part

            # Try parsing from URL
            url_location = self.location_service.parse_location_from_url(
                self.url)
            if url_location and self._validate_location(url_location):
                return url_location

            return "Location Unknown"

        except Exception as e:
            logger.error(f"Error extracting location: {str(e)}")
            return "Location Unknown"

    def _validate_location(self, location: str) -> bool:
        """Validate location string."""
        if not location:
            return False
        # Check for New England state reference
        state_pattern = r'(?:ME|NH|VT|MA|CT|RI|Maine|New\s+Hampshire|Vermont|Massachusetts|Connecticut|Rhode\s+Island)\b'
        return bool(re.search(state_pattern, location, re.I))

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage with enhanced validation."""
        try:
            # First try extracting from the title
            title_elem = self.soup.find(
                **LANDANDFARM_SELECTORS["title"]["main"])
            if title_elem:
                text = title_elem.text
                acres_match = re.search(
                    r'(\d+(?:\.\d+)?)\s*Acres?', text, re.I)
                if acres_match:
                    return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

            # Try page title
            if self.soup.title:
                text = self.soup.title.string
                acres_match = re.search(
                    r'(\d+(?:\.\d+)?)\s*Acres?', text, re.I)
                if acres_match:
                    return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

            # Try URL for acreage information
            url_path = self.url.split('/')[-1]
            acres_match = re.search(r'(\d+(?:\.\d+)?)-acres?', url_path, re.I)
            if acres_match:
                return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

            # Try details section
            details = self.soup.find(
                **LANDANDFARM_SELECTORS["details"]["container"])
            if details:
                for section in details.find_all(**LANDANDFARM_SELECTORS["details"]["sections"]):
                    text = TextProcessor.clean_html_text(section.text)
                    acres_patterns = [
                        r'(\d+(?:\.\d+)?)\s*acres?',
                        r'(\d+(?:\.\d+)?)\s*acre lot',
                        r'(\d+(?:\.\d+)?)\s*acre parcel'
                    ]
                    for pattern in acres_patterns:
                        match = re.search(pattern, text, re.I)
                        if match:
                            return self.text_processor.standardize_acreage(f"{match.group(1)} acres")

            # Try specs section
            specs = self.soup.find(**LANDANDFARM_SELECTORS["details"]["specs"])
            if specs:
                text = TextProcessor.clean_html_text(specs.text)
                acres_match = re.search(
                    r'(\d+(?:\.\d+)?)\s*acres?', text, re.I)
                if acres_match:
                    return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

            # Try description
            description = self._extract_description()
            if description:
                acres_match = re.search(
                    r'(\d+(?:\.\d+)?)\s*acres?', description, re.I)
                if acres_match:
                    return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

            return "Not specified", "Unknown"

        except Exception as e:
            logger.error(f"Error extracting acreage: {str(e)}")
            return "Not specified", "Unknown"

    def extract_property_details(self) -> Dict[str, Any]:
        """Extract comprehensive property details."""
        try:
            details = {}

            # Extract from title
            title_text = ""
            title_elem = self.soup.find(
                **LANDANDFARM_SELECTORS["title"]["main"])
            if title_elem:
                title_text = title_elem.text

            # Extract from page title
            page_title = ""
            if self.soup.title:
                page_title = self.soup.title.string

            # Extract from description
            description = self._extract_description() or ""

            # Combined search text
            search_text = f"{title_text} {page_title} {description}"

            # Extract house details with comprehensive patterns
            house_patterns = {
                "bedrooms": [r'(\d+)\s*bed(?:room)?s?', r'(\d+)-bed(?:room)?', r'(\d+)\s*BR'],
                "bathrooms": [r'(\d+(?:\.\d+)?)\s*bath(?:room)?s?', r'(\d+(?:\.\d+)?)-bath', r'(\d+(?:\.\d+)?)\s*BA'],
                "sqft": [r'(\d+(?:,\d+)?)\s*sq(?:uare)?\s*(?:ft|feet)', r'(\d+(?:,\d+)?)\s*sf', r'(\d+(?:,\d+)?)\s*sqft'],
                "year_built": [r'built\s+in\s+(\d{4})', r'year\s+built:?\s*(\d{4})'],
                "garage": [r'(\d+)(?:\s*-?\s*)?car garage', r'(\d+)\s*garage']
            }

            for key, patterns in house_patterns.items():
                for pattern in patterns:
                    match = re.search(pattern, search_text, re.I)
                    if match:
                        details[key] = match.group(1).replace(',', '')
                        break

            # Extract land features
            land_features = [
                "wooded", "cleared", "fenced", "pasture",
                "cropland", "wetlands", "pond", "stream", "creek",
                "waterfront", "lake", "mountain", "view"
            ]
            features = []
            for feature in land_features:
                feature_pattern = rf'\b{feature}\b'
                if re.search(feature_pattern, search_text, re.I):
                    features.append(feature.capitalize())

            if features:
                details["land_features"] = features

            return details

        except Exception as e:
            logger.error(f"Error extracting property details: {str(e)}")
            return {}

    def determine_property_type(self, details: Dict[str, Any]) -> str:
        """Determine property type from extracted details."""
        try:
            # Get search text from title, description and URL
            title_elem = self.soup.find(
                **LANDANDFARM_SELECTORS["title"]["main"])
            title_text = title_elem.text if title_elem else ""

            description = self._extract_description() or ""
            url_path = self.url.lower()

            combined_text = f"{title_text} {description} {url_path}".lower()

            # Check for explicit property types
            if any(kw in combined_text for kw in ["bedroom", "bath", "home", "house", "residence"]):
                return "Single Family"

            if any(kw in combined_text for kw in ["farm", "ranch", "agricultural", "barn", "pasture", "cropland"]):
                return "Farm"

            if any(kw in combined_text for kw in ["commercial", "business", "retail", "office", "industrial"]):
                return "Commercial"

            if any(kw in combined_text for kw in ["land", "lot", "acreage", "vacant"]):
                return "Land"

            # Check for house details
            if any(key in details for key in ["bedrooms", "bathrooms", "sqft"]):
                return "Single Family"

            # Default to land if we have acreage
            if details.get("land_features") or "acreage" in combined_text:
                return "Land"

            return "Unknown"

        except Exception as e:
            logger.error(f"Error determining property type: {str(e)}")
            return "Unknown"

    def extract_amenities(self) -> List[str]:
        """Extract property amenities and features."""
        try:
            amenities = set()
            features_section = self.soup.find(
                **LANDANDFARM_SELECTORS["details"]["features"])

            if features_section:
                # Extract listed features
                for item in features_section.find_all("li"):
                    amenity = TextProcessor.clean_html_text(item.text)
                    if amenity:
                        amenities.add(amenity)

                # Look for specific amenities in text
                text = features_section.get_text().lower()
                amenity_keywords = {
                    "well": "Well water",
                    "septic": "Septic system",
                    "electric": "Electricity",
                    "utilities": "Utilities available",
                    "road": "Road frontage",
                    "fenced": "Fenced",
                    "wooded": "Wooded",
                    "cleared": "Cleared land",
                    "stream": "Stream",
                    "pond": "Pond",
                    "barn": "Barn",
                    "outbuilding": "Outbuildings",
                    "garden": "Garden area",
                    "view": "Scenic view",
                    "waterfront": "Waterfront",
                    "hunting": "Hunting land"
                }

                for keyword, amenity in amenity_keywords.items():
                    if keyword in text:
                        amenities.add(amenity)

            # Also check description for amenities
            description = self._extract_description() or ""
            for keyword, amenity in amenity_keywords.items():
                if keyword in description.lower():
                    amenities.add(amenity)

            return list(amenities)

        except Exception as e:
            logger.error(f"Error extracting amenities: {str(e)}")
            return []

    def _extract_description(self) -> Optional[str]:
        """Extract and clean property description."""
        try:
            description = []
            desc_elem = self.soup.find(
                **LANDANDFARM_SELECTORS["description"]["main"])

            if desc_elem:
                # Get all paragraphs
                paragraphs = desc_elem.find_all("p") or [desc_elem]

                for p in paragraphs:
                    text = TextProcessor.clean_html_text(p.text)
                    # Skip generic or empty content
                    if (text and
                        "copyright" not in text.lower() and
                            "all rights reserved" not in text.lower()):
                        description.append(text)

            return " ".join(description) if description else None

        except Exception as e:
            logger.error(f"Error extracting description: {str(e)}")
            return None

    def extract_additional_data(self):
        """Extract all additional property information."""
        try:
            # Extract basic property details
            details = self.extract_property_details()
            self.raw_data["property_details"] = details

            # Set property type
            self.data["property_type"] = self.determine_property_type(details)

            # Format house details if present
            house_info = []
            if details.get("bedrooms"):
                house_info.append(f"{details['bedrooms']} bedrooms")
            if details.get("bathrooms"):
                house_info.append(f"{details['bathrooms']} bathrooms")
            if details.get("sqft"):
                house_info.append(f"{details['sqft']} sqft")
            if details.get("year_built"):
                house_info.append(f"Built {details['year_built']}")
            if details.get("garage"):
                house_info.append(f"{details['garage']}-car garage")

            if house_info:
                self.data["house_details"] = " | ".join(house_info)

            # Extract land features for amenities
            if details.get("land_features"):
                self.data["other_amenities"] = " | ".join(
                    details["land_features"])

            # Extract listing date
            listing_date = self.soup.find(
                **LANDANDFARM_SELECTORS["metadata"]["date"])
            if listing_date:
                date_text = TextProcessor.clean_html_text(listing_date.text)
                date_str = DateExtractor.parse_date_string(date_text)
                if date_str:
                    self.data["listing_date"] = date_str

            # Extract description as notes
            description = self._extract_description()
            if description:
                self.data["notes"] = description

            # Extract amenities
            amenities = self.extract_amenities()
            if amenities:
                existing_amenities = self.data.get("other_amenities", "").split(
                    " | ") if self.data.get("other_amenities") else []
                all_amenities = list(
                    set([a for a in existing_amenities if a] + amenities))
                if all_amenities:
                    self.data["other_amenities"] = " | ".join(all_amenities)

            # Try to extract additional information from the URL
            url_path = self.url.split('/')[-1]

            # Check for property size in URL
            size_match = re.search(r'(\d+(?:\.\d+)?)-sq-ft', url_path)
            if size_match and "house_details" not in self.data:
                sqft = size_match.group(1)
                self.data["house_details"] = f"{sqft} sqft"

            # Check for bedrooms/bathrooms in URL
            bed_match = re.search(r'(\d+)-bedroom', url_path)
            bath_match = re.search(r'(\d+(?:\.\d+)?)-bath', url_path)
            if (bed_match or bath_match) and "house_details" not in self.data:
                house_details = []
                if bed_match:
                    house_details.append(f"{bed_match.group(1)} bedrooms")
                if bath_match:
                    house_details.append(f"{bath_match.group(1)} bathrooms")
                if house_details:
                    self.data["house_details"] = " | ".join(house_details)

            # Process location information if location is valid
            if self.data["location"] != "Location Unknown":
                location_info = self.location_service.get_comprehensive_location_info(
                    self.data["location"])

                # Map location data to schema
                for key, value in location_info.items():
                    # Skip existing values
                    if key in self.data and self.data[key]:
                        continue

                    # Map keys to match our schema
                    if key == 'nearest_city':
                        self.data['nearest_city'] = value
                    elif key == 'nearest_city_distance':
                        self.data['nearest_city_distance'] = value
                    elif key == 'nearest_city_distance_bucket':
                        self.data['nearest_city_distance_bucket'] = value
                    elif key == 'distance_to_portland':
                        self.data['distance_to_portland'] = value
                    elif key == 'portland_distance_bucket':
                        self.data['portland_distance_bucket'] = value
                    elif key == 'town_population':
                        self.data['town_population'] = value
                    elif key == 'town_pop_bucket':
                        self.data['town_pop_bucket'] = value
                    elif key == 'school_district':
                        self.data['school_district'] = value
                    elif key == 'school_rating':
                        self.data['school_rating'] = value
                    elif key == 'school_rating_cat':
                        self.data['school_rating_cat'] = value
                    elif key == 'hospital_distance':
                        self.data['hospital_distance'] = value
                    elif key == 'hospital_distance_bucket':
                        self.data['hospital_distance_bucket'] = value
                    elif key == 'closest_hospital':
                        self.data['closest_hospital'] = value
                    else:
                        # Store other properties directly
                        self.data[key] = value

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")
            logger.error(traceback.format_exc())
            self.raw_data["extraction_error"] = str(e)

    def extract(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Main extraction method with enhanced validation."""
        logger.debug(f"Starting extraction for {self.platform_name}")
        self.soup = soup
        self.raw_data = {}

        try:
            # Verify page content first
            if not self._verify_page_content():
                logger.warning(
                    "Page content verification failed - continuing with limited extraction")
                self.raw_data['extraction_status'] = 'partial'
            else:
                self.raw_data['extraction_status'] = 'verified'

            # Extract core data directly
            self.data["listing_name"] = self.extract_listing_name()
            self.data["location"] = self.extract_location()
            self.data["price"], self.data["price_bucket"] = self.extract_price()
            self.data["acreage"], self.data["acreage_bucket"] = self.extract_acreage_info()

            # Extract additional platform-specific data
            self.extract_additional_data()

            # Mark extraction as successful
            self.raw_data['extraction_status'] = 'success'

            return self.data

        except Exception as e:
            logger.error(f"Error in extraction: {str(e)}")
            logger.error(traceback.format_exc())

            # Mark the extraction as failed but return partial data
            self.raw_data['extraction_status'] = 'failed'
            self.raw_data['extraction_error'] = str(e)

            return self.data
