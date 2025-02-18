# src/new_england_listings/extractors/farmland.py
from typing import Dict, Any, Tuple
import re
import logging
from bs4 import BeautifulSoup
from .base import BaseExtractor
from ..utils.text import clean_price, extract_acreage, clean_html_text, extract_property_type
from ..utils.dates import extract_listing_date
from ..utils.geocoding import parse_location_from_url
from ..utils.geocoding import get_comprehensive_location_info
from ..config.constants import ACREAGE_BUCKETS

logger = logging.getLogger(__name__)


class FarmlandExtractor(BaseExtractor):
    """Extractor for farmland listings from Maine Farmland Trust and New England Farmland Finder."""

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
                logger.debug(f"Found {section_name}: {section.get_text()[:100]}")
                found_sections.append(section_name)

        if not found_sections:
            logger.error("No valid content sections found")
            return False

        logger.info(f"Found content sections: {', '.join(found_sections)}")
        return True

    def extract(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Main extraction method with content verification."""
        self.soup = soup

        # Verify page content before proceeding
        if not self._verify_page_content():
            logger.error("Failed to get complete page content")
            return self.data

        # Continue with regular extraction
        return super().extract(soup)

    @property
    def platform_name(self) -> str:
        return "Maine Farmland Trust" if "mainefarmlandtrust.org" in self.url else "New England Farmland Finder"

    def extract_listing_name(self) -> str:
        """Extract the listing name/title with enhanced error handling."""
        logger.debug("Extracting listing name...")

        if "newenglandfarmlandfinder.org" in self.url:
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
                            farm_name = re.search(r'([^,]+Farm[^,]*)', sentence)
                            if farm_name:
                                logger.debug(
                                    f"Found farm name in description: {farm_name.group(1)}")
                                return farm_name.group(1).strip()

            # Method 3: Try to extract from URL
            url_parts = self.url.split('/')[-1].split('-')
            farm_parts = []
            for part in url_parts:
                if part.lower() in ['me', 'vt', 'nh', 'ma', 'ct', 'ri', 'acres', 'sale', 'lease', 'county']:
                    break
                farm_parts.append(part.capitalize())
            if farm_parts and 'farm' in ' '.join(farm_parts).lower():
                title = ' '.join(farm_parts)
                logger.debug(f"Constructed title from URL: {title}")
                return title

            # Method 4: If all else fails, try to use the full property title
            if 'property_title' in locals() and property_title:
                return property_title

            # Final fallback: return default
            return "Untitled Farm Property"

        return "Untitled Farm Property"

    def extract_location(self) -> str:
        """Extract location information with enhanced accuracy."""
        logger.debug("Extracting location...")

        if "newenglandfarmlandfinder.org" in self.url:
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
                url_parts = self.url.split('-')
                state_indicators = {'me': 'ME', 'vt': 'VT',
                                    'nh': 'NH', 'ma': 'MA', 'ct': 'CT', 'ri': 'RI'}

                for part in url_parts:
                    if part.lower() in state_indicators:
                        state = state_indicators[part.lower()]
                        city_index = url_parts.index(part) - 1
                        if city_index >= 0:
                            city = url_parts[city_index].capitalize()
                            location = f"{city}, {state}"
                            logger.debug(
                                f"Extracted location from URL: {location}")
                            return location

            except Exception as e:
                logger.warning(f"Error extracting location: {str(e)}")

        return "Location Unknown"

    def extract_price(self) -> Tuple[str, str]:
        """Extract price information with improved reliability."""
        logger.debug("Extracting price...")

        if "newenglandfarmlandfinder.org" in self.url:
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

        return "Contact for Price", "N/A"

    def extract_additional_data(self):
        """Extract comprehensive property details."""
        # Keep all your existing code in this method
        super().extract_additional_data()

        if "newenglandfarmlandfinder.org" in self.url:
            try:
                # Keep all your existing extraction code...
                self._extract_basic_details()
                self._extract_acreage_details()
                self._extract_farm_details()
                self._extract_property_features()
                self._extract_dates()

                # Add this new section at the end of the method
                # Get location-based information
                if self.data.get("location") != "Location Unknown":
                    try:
                        location_info = get_comprehensive_location_info(
                            self.data["location"])
                        # Only update fields that aren't already set
                        for key, value in location_info.items():
                            if key not in self.data or self.data[key] is None:
                                self.data[key] = value
                    except Exception as e:
                        logger.warning(f"Error getting location info: {str(e)}")

            except Exception as e:
                logger.error(f"Error in additional data extraction: {str(e)}")
                logger.debug("Exception details:", exc_info=True)

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
        infra_elem = self.soup.find(string=lambda x: x and "Farm infrastructure details" in str(x))
        if infra_elem:
            details = infra_elem.find_next("div")
            if details:
                farm_details.append(f"Infrastructure: {clean_html_text(details.text)}")

        # Water sources
        water_elem = self.soup.find(string=lambda x: x and "Water sources details" in str(x))
        if water_elem:
            water_details = water_elem.find_next("div")
            if water_details:
                farm_details.append(f"Water Sources: {clean_html_text(water_details.text)}")

        # Equipment details
        equipment_elem = self.soup.find(string=lambda x: x and "Equipment and machinery details" in str(x))
        if equipment_elem:
            equipment_details = equipment_elem.find_next("div")
            if equipment_details:
                farm_details.append(f"Equipment: {clean_html_text(equipment_details.text)}")

        # Housing details
        housing_elem = self.soup.find(string=lambda x: x and "Farmer housing details" in str(x))
        if housing_elem:
            housing_details = housing_elem.find_next("div")
            if housing_details:
                self.data["house_details"] = clean_html_text(housing_details.text)

        if farm_details:
            self.data["farm_details"] = " | ".join(farm_details)

    def _extract_property_features(self):
        """Extract additional property features and characteristics."""
        features = []

        # Check for organic certification
        organic_elem = self.soup.find(string=lambda x: x and "certified organic" in str(x).lower())
        if organic_elem:
            organic_value = organic_elem.find_next("div")
            if organic_value:
                features.append(f"Organic Status: {clean_html_text(organic_value.text)}")

        # Check for conservation easement
        easement_elem = self.soup.find(string=lambda x: x and "Conservation Easement" in str(x))
        if easement_elem:
            easement_details = easement_elem.find_next("div")
            if easement_details:
                features.append(f"Conservation Easement: {clean_html_text(easement_details.text)}")

        # Check for forest management plan
        forest_elem = self.soup.find(string=lambda x: x and "forest management plan" in str(x).lower())
        if forest_elem:
            forest_details = forest_elem.find_next("div")
            if forest_details:
                features.append(f"Forest Management: {clean_html_text(forest_details.text)}")

        if features:
            self.data["property_features"] = " | ".join(features)

    def _extract_dates(self):
        """Extract listing dates and other temporal information."""
        # Posted date
        date_elem = self.soup.find(string=lambda x: x and "Date posted" in str(x))
        if date_elem:
            date_value = date_elem.find_next("div")
            if date_value:
                self.data["listing_date"] = clean_html_text(date_value.text)

        # Any additional dates (availability, etc.)
        availability_elem = self.soup.find(string=lambda x: x and "Date available" in str(x))
        if availability_elem:
            avail_value = availability_elem.find_next("div")
            if avail_value:
                self.data["available_date"] = clean_html_text(avail_value.text)

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage information with improved accuracy."""
        logger.debug("Starting acreage extraction...")
        
        if "newenglandfarmlandfinder.org" in self.url:
            try:
                total_acres = 0.0
                acreage_found = False
                
                # First try to find total acreage
                total_elem = self.soup.find(string=lambda x: x and "Total number of acres" in str(x))
                if total_elem:
                    total_value = total_elem.find_next("div")
                    if total_value:
                        try:
                            total_acres = float(clean_html_text(total_value.text))
                            acreage_found = True
                        except ValueError:
                            logger.warning("Could not convert total acreage to float")

                # If no total found, sum individual fields
                if not acreage_found:
                    acreage_fields = {
                        "cropland": "Acres of cropland",
                        "pasture": "Acres of pasture",
                        "forest": "Acres of forested land"
                    }

                    for field_type, search_text in acreage_fields.items():
                        field_elem = self.soup.find(string=lambda x: x and search_text in str(x))
                        if field_elem:
                            value_elem = field_elem.find_next("div")
                            if value_elem:
                                try:
                                    acres = float(clean_html_text(value_elem.text))
                                    total_acres += acres
                                    acreage_found = True
                                except ValueError:
                                    logger.warning(f"Could not convert {field_type} acreage to float")

                if acreage_found:
                    formatted_acres = f"{total_acres:.1f} acres"
                    # Determine bucket
                    for threshold, bucket in sorted(ACREAGE_BUCKETS.items()):
                        if total_acres < threshold:
                            return formatted_acres, bucket
                    return formatted_acres, "Extensive (100+ acres)"

            except Exception as e:
                logger.warning(f"Error extracting acreage details: {str(e)}")

        return "Not specified", "Unknown"