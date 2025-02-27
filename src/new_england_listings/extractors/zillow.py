# src/new_england_listings/extractors/zillow.py

"""
Zillow specific extractor implementation.
"""

from typing import Dict, Any, Tuple, Optional, List, Union
import re
import logging
import json
import traceback
from urllib.parse import urlparse
from datetime import datetime
from bs4 import BeautifulSoup, Tag

from .base import BaseExtractor
from ..utils.text import TextProcessor
from ..utils.dates import DateExtractor
from ..utils.location_service import LocationService
from ..models.base import PropertyType

logger = logging.getLogger(__name__)

ZILLOW_SELECTORS = {
    "summary": {
        "container": {"data-testid": "home-summary-container"},
        "price": {
            "class_": ["ds-summary-row", "price-container"],
            "data-testid": "price",
            "selector": "[data-testid='price']"
        },
        "address": {
            "class_": ["ds-address-container", "address"],
            "data-testid": "home-details-chip",
            "selector": "[data-testid='home-details-chip']"
        },
        "facts": {
            "class_": ["ds-home-fact-list", "home-facts"],
            "data-testid": "facts-container",
            "selector": "[data-testid='facts-container']"
        }
    },
    "description": {
        "container": {"data-testid": "description-container"},
        "text": {"data-testid": "description-text"}
    },
    "details": {
        "container": {"data-testid": "home-details-content"},
        "facts": {"data-testid": "facts-section"},
        "features": {"data-testid": "features-section"}
    },
    "metadata": {
        "json": {"id": "hdpApolloPreloadedData", "type": "application/json"}
    }
}


class ZillowExtractor(BaseExtractor):
    """Enhanced extractor for Zillow listings."""

    def __init__(self, url: str):
        """Initialize extractor with URL and extract zpid."""
        super().__init__(url)
        self.zpid = self._extract_zpid(url)
        self.property_data = None  # Will store extracted JSON data if available

    @property
    def platform_name(self) -> str:
        return "Zillow"

    def _extract_zpid(self, url: str) -> Optional[str]:
        """Extract the Zillow Property ID (zpid) from the URL."""
        zpid_match = re.search(r'\/(\d+)_zpid', url)
        if zpid_match:
            return zpid_match.group(1)
        return None

    def _extract_json_data(self) -> Dict:
        """Extract structured property data from embedded JSON."""
        try:
            # Try to find the Apollo preloaded data script
            script = self.soup.find("script", id="hdpApolloPreloadedData")
            if script and script.string:
                data = json.loads(script.string)

                # Navigate to property data in the JSON structure
                if 'apiCache' in data:
                    for key, value in data['apiCache'].items():
                        if 'property' in key:
                            property_data = json.loads(value)
                            if 'property' in property_data:
                                logger.debug(
                                    "Successfully extracted property JSON data")
                                return property_data['property']

            # Try alternative script tags
            for script in self.soup.find_all("script", type="application/json"):
                if script.string and "zpid" in script.string:
                    try:
                        data = json.loads(script.string)
                        if 'props' in data and 'pageProps' in data['props'] and 'property' in data['props']['pageProps']:
                            return data['props']['pageProps']['property']
                    except:
                        continue

            logger.warning("Could not extract structured JSON data")
            return {}

        except Exception as e:
            logger.error(f"Error extracting JSON data: {str(e)}")
            return {}

    def _verify_page_content(self) -> bool:
        """Verify the page content was properly loaded."""
        # First extract any structured data we can find
        self.property_data = self._extract_json_data()

        # Check for Zillow blocking indicators
        page_text = self.soup.get_text().lower()
        blocking_indicators = [
            "captcha",
            "security check",
            "please verify",
            "suspicious activity",
            "unusual traffic"
        ]

        if any(indicator in page_text for indicator in blocking_indicators):
            logger.warning("Detected blocking content on Zillow")
            # We'll continue anyway and rely on URL-based extraction as fallback

        # If we have property_data, consider the page valid
        if self.property_data:
            return True

        # Otherwise check for essential page elements
        price_elem = self.soup.select_one(
            ZILLOW_SELECTORS["summary"]["price"]["selector"])
        address_elem = self.soup.select_one(
            ZILLOW_SELECTORS["summary"]["address"]["selector"])

        return bool(price_elem or address_elem or self.zpid)

    def extract_listing_name(self) -> str:
        """Extract the listing name/title."""
        try:
            # Try to get from JSON data first
            if self.property_data:
                address = self.property_data.get('address', {})
                street = address.get('streetAddress', '')
                city = address.get('city', '')
                state = address.get('state', '')
                zip_code = address.get('zipcode', '')

                if street and city and state:
                    return f"{street}, {city}, {state} {zip_code}".strip()

            # Try to get from address element
            address_elem = self.soup.select_one(
                ZILLOW_SELECTORS["summary"]["address"]["selector"])
            if address_elem:
                return TextProcessor.clean_html_text(address_elem.text)

            # Try any h1 element
            h1 = self.soup.find("h1")
            if h1:
                return TextProcessor.clean_html_text(h1.text)

            # Try to extract from URL
            path_parts = urlparse(self.url).path.split('/')
            if len(path_parts) > 2:
                address_part = path_parts[2]  # /homedetails/[address-slug]/
                return address_part.replace('-', ' ').title()

            return f"Zillow Property {self.zpid}" if self.zpid else "Untitled Zillow Listing"

        except Exception as e:
            logger.error(f"Error extracting listing name: {str(e)}")
            return f"Zillow Property {self.zpid}" if self.zpid else "Untitled Zillow Listing"

    def extract_price(self) -> Tuple[str, str]:
        """Extract price with enhanced validation."""
        try:
            # Try to extract from JSON data first
            if self.property_data:
                price = self.property_data.get('price', {})
                if isinstance(price, dict) and 'value' in price:
                    price_value = price.get('value')
                    if price_value:
                        formatted_price = f"${price_value:,}"
                        return self.text_processor.standardize_price(formatted_price)

                # Try alternate price locations in the JSON
                zestimate = self.property_data.get('zestimate', {})
                if isinstance(zestimate, dict) and 'amount' in zestimate:
                    price_value = zestimate.get('amount')
                    if price_value:
                        formatted_price = f"${price_value:,}"
                        return self.text_processor.standardize_price(formatted_price)

            # Try price element
            price_elem = self.soup.select_one(
                ZILLOW_SELECTORS["summary"]["price"]["selector"])
            if price_elem:
                return self.text_processor.standardize_price(price_elem.text)

            # Try looking for any price pattern in the text
            text = self.soup.get_text()
            price_pattern = r'\$([\d,]+)'
            price_match = re.search(price_pattern, text)
            if price_match:
                price_text = price_match.group(0)
                return self.text_processor.standardize_price(price_text)

            return "Contact for Price", "N/A"

        except Exception as e:
            logger.error(f"Error extracting price: {str(e)}")
            return "Contact for Price", "N/A"

    def extract_location(self) -> str:
        """Extract location with enhanced validation."""
        try:
            # Try to extract from JSON data first
            if self.property_data:
                address = self.property_data.get('address', {})
                city = address.get('city', '')
                state = address.get('state', '')
                zip_code = address.get('zipcode', '')

                if city and state:
                    location = f"{city}, {state}"
                    if zip_code:
                        location += f" {zip_code}"
                    return location

            # Try address element
            address_elem = self.soup.select_one(
                ZILLOW_SELECTORS["summary"]["address"]["selector"])
            if address_elem:
                address_text = TextProcessor.clean_html_text(address_elem.text)
                # Try to extract city, state from full address
                location_match = re.search(
                    r'([^,]+),\s*([A-Z]{2})', address_text)
                if location_match:
                    return f"{location_match.group(1)}, {location_match.group(2)}"
                return address_text

            # Try meta tags
            meta_location = self.soup.find("meta", {"property": "og:locality"})
            meta_region = self.soup.find("meta", {"property": "og:region"})
            if meta_location and meta_region:
                return f"{meta_location['content']}, {meta_region['content']}"

            # Try extracting from URL
            path_parts = urlparse(self.url).path.split('/')
            if len(path_parts) > 2:
                address_part = path_parts[2]  # /homedetails/[address-slug]/
                location_match = re.search(
                    r'([A-Za-z-]+)-([A-Z]{2})-\d+$', address_part)
                if location_match:
                    city = location_match.group(1).replace('-', ' ').title()
                    state = location_match.group(2).upper()
                    return f"{city}, {state}"

            return "Location Unknown"

        except Exception as e:
            logger.error(f"Error extracting location: {str(e)}")
            return "Location Unknown"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage with enhanced validation."""
        try:
            # Try to extract from JSON data first
            if self.property_data:
                # Check for lot size in resoFacts
                reso_facts = self.property_data.get('resoFacts', {})
                lot_size = reso_facts.get('lotSize')
                if lot_size:
                    # Convert to acres if in sq ft
                    if reso_facts.get('lotSizeUnit') == 'sqft':
                        acres = float(lot_size) / 43560
                        return self.text_processor.standardize_acreage(f"{acres:.2f} acres")
                    else:
                        return self.text_processor.standardize_acreage(f"{lot_size} acres")

                # Try alternate locations in JSON
                lot_area = self.property_data.get('lotAreaValue')
                lot_unit = self.property_data.get('lotAreaUnit')
                if lot_area and lot_unit:
                    if lot_unit.lower() == 'sqft':
                        acres = float(lot_area) / 43560
                        return self.text_processor.standardize_acreage(f"{acres:.2f} acres")
                    elif lot_unit.lower() == 'acres':
                        return self.text_processor.standardize_acreage(f"{lot_area} acres")

            # Try facts section
            facts_elem = self.soup.select_one(
                ZILLOW_SELECTORS["summary"]["facts"]["selector"])
            if facts_elem:
                facts_text = facts_elem.get_text()
                # Look for lot size
                lot_patterns = [
                    r'(\d+(?:\.\d+)?)\s*acres?',
                    r'lot\s*(?:size)?:?\s*(\d+(?:\.\d+)?)\s*acres?',
                    r'(\d+(?:\.\d+)?)\s*acre\s+lot',
                    r'lot:?\s*(\d+(?:,\d+)?)\s*sq\s*\.?\s*ft'
                ]

                for pattern in lot_patterns:
                    match = re.search(pattern, facts_text, re.I)
                    if match:
                        # Convert sqft to acres if needed
                        if 'sq' in pattern:
                            sqft = float(match.group(1).replace(',', ''))
                            acres = sqft / 43560
                            return self.text_processor.standardize_acreage(f"{acres:.2f} acres")
                        else:
                            return self.text_processor.standardize_acreage(f"{match.group(1)} acres")

            # Try to find acreage in description
            description_elem = self.soup.select_one(
                ZILLOW_SELECTORS["description"]["text"])
            if description_elem:
                desc_text = description_elem.get_text()
                acres_match = re.search(
                    r'(\d+(?:\.\d+)?)\s*acres?', desc_text, re.I)
                if acres_match:
                    return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

                # Look for sq ft lot size
                sqft_match = re.search(
                    r'lot\s*(?:size)?:?\s*(\d+(?:,\d+)?)\s*sq\s*\.?\s*ft', desc_text, re.I)
                if sqft_match:
                    sqft = float(sqft_match.group(1).replace(',', ''))
                    acres = sqft / 43560
                    return self.text_processor.standardize_acreage(f"{acres:.2f} acres")

            # Check the full page text as a last resort
            full_text = self.soup.get_text()
            acres_match = re.search(
                r'(\d+(?:\.\d+)?)\s*acres?', full_text, re.I)
            if acres_match:
                return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

            return "Not specified", "Unknown"

        except Exception as e:
            logger.error(f"Error extracting acreage: {str(e)}")
            return "Not specified", "Unknown"

    def extract_property_details(self) -> Dict[str, Any]:
        """Extract comprehensive property details."""
        details = {}

        try:
            # Try to extract from JSON data first
            if self.property_data:
                # Try to get basic facts
                if 'resoFacts' in self.property_data:
                    facts = self.property_data['resoFacts']
                    if 'bedrooms' in facts:
                        details['bedrooms'] = facts['bedrooms']
                    if 'bathrooms' in facts:
                        details['bathrooms'] = facts['bathrooms']
                    if 'livingArea' in facts:
                        details['sqft'] = facts['livingArea']
                    if 'yearBuilt' in facts:
                        details['year_built'] = facts['yearBuilt']

                # Try alternate locations
                if 'bedrooms' in self.property_data:
                    details['bedrooms'] = self.property_data['bedrooms']
                if 'bathrooms' in self.property_data:
                    details['bathrooms'] = self.property_data['bathrooms']
                if 'livingArea' in self.property_data:
                    details['sqft'] = self.property_data['livingArea']
                if 'yearBuilt' in self.property_data:
                    details['year_built'] = self.property_data['yearBuilt']

                # Get description
                if 'description' in self.property_data:
                    details['description'] = self.property_data['description']

                # Get features and amenities
                if 'homeFactsList' in self.property_data:
                    features = []
                    for fact in self.property_data['homeFactsList']:
                        if 'factLabel' in fact and 'factValue' in fact:
                            features.append(
                                f"{fact['factLabel']}: {fact['factValue']}")
                    if features:
                        details['features'] = features

            # If we don't have complete details, try extracting from HTML
            if len(details) < 3:  # If we're missing several key details
                # Try facts section
                facts_elem = self.soup.select_one(
                    ZILLOW_SELECTORS["summary"]["facts"]["selector"])
                if facts_elem:
                    facts_text = facts_elem.get_text()

                    # Extract bed/bath/sqft from facts
                    bed_match = re.search(r'(\d+)\s*beds?', facts_text, re.I)
                    if bed_match and 'bedrooms' not in details:
                        details['bedrooms'] = bed_match.group(1)

                    bath_match = re.search(
                        r'(\d+(?:\.\d+)?)\s*baths?', facts_text, re.I)
                    if bath_match and 'bathrooms' not in details:
                        details['bathrooms'] = bath_match.group(1)

                    sqft_match = re.search(
                        r'(\d+(?:,\d+)?)\s*sq\s*ft', facts_text, re.I)
                    if sqft_match and 'sqft' not in details:
                        details['sqft'] = sqft_match.group(1).replace(',', '')

                # Try to get description
                if 'description' not in details:
                    desc_elem = self.soup.select_one(
                        ZILLOW_SELECTORS["description"]["text"])
                    if desc_elem:
                        details['description'] = TextProcessor.clean_html_text(
                            desc_elem.get_text())

                # Try to get features
                if 'features' not in details:
                    features_elem = self.soup.select_one(
                        ZILLOW_SELECTORS["details"]["features"])
                    if features_elem:
                        features = []
                        for li in features_elem.find_all('li'):
                            feature = TextProcessor.clean_html_text(
                                li.get_text())
                            if feature:
                                features.append(feature)
                        if features:
                            details['features'] = features

            return details

        except Exception as e:
            logger.error(f"Error extracting property details: {str(e)}")
            return details

    def extract_additional_data(self):
        """Extract all additional property information."""
        try:
            # Use the parent method first to get basic data
            super().extract_additional_data()

            # Get comprehensive property details
            details = self.extract_property_details()

            # Set house details
            house_info = []
            if 'bedrooms' in details:
                house_info.append(f"{details['bedrooms']} bedrooms")
            if 'bathrooms' in details:
                house_info.append(f"{details['bathrooms']} bathrooms")
            if 'sqft' in details:
                house_info.append(f"{details['sqft']} sqft")
            if 'year_built' in details:
                house_info.append(f"Built {details['year_built']}")

            if house_info:
                self.data["house_details"] = " | ".join(house_info)

            # Add description to notes
            if 'description' in details:
                self.data["notes"] = details['description']

            # Extract features for amenities
            if 'features' in details:
                existing_amenities = self.data.get("other_amenities", "")
                new_amenities = " | ".join(details['features'])

                if existing_amenities:
                    self.data["other_amenities"] = f"{existing_amenities} | {new_amenities}"
                else:
                    self.data["other_amenities"] = new_amenities

            # Try to determine listing date
            if self.property_data:
                # Try various date fields in Zillow's JSON
                date_fields = [
                    'datePosted', 'dateListed', 'listingUpdatedDate',
                    'lastUpdatedDate', 'postedDate'
                ]

                for field in date_fields:
                    if field in self.property_data:
                        date_value = self.property_data[field]
                        if isinstance(date_value, str):
                            try:
                                date_obj = datetime.fromisoformat(
                                    date_value.replace('Z', '+00:00'))
                                self.data["listing_date"] = date_obj
                                break
                            except:
                                pass

            # Process location information for enriched data
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
            logger.debug(traceback.format_exc())
            self.raw_data["extraction_error"] = str(e)

    def extract(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Main extraction method with enhanced error handling."""
        self.soup = soup
        self.raw_data = {}

        try:
            # Verify page content and extract structured data if available
            page_valid = self._verify_page_content()
            if not page_valid:
                logger.warning(
                    "Page validation failed - using fallback extraction")

            # Extract core data
            self.data["listing_name"] = self.extract_listing_name()
            self.data["location"] = self.extract_location()
            self.data["price"], self.data["price_bucket"] = self.extract_price()
            self.data["acreage"], self.data["acreage_bucket"] = self.extract_acreage_info()

            # Determine property type
            if self.property_data:
                home_type = self.property_data.get('homeType', '').lower()
                if 'single' in home_type or 'house' in home_type:
                    self.data["property_type"] = "Single Family"
                elif 'land' in home_type or 'lot' in home_type:
                    self.data["property_type"] = "Land"
                elif 'farm' in home_type or 'ranch' in home_type:
                    self.data["property_type"] = "Farm"
                elif 'commercial' in home_type or 'industrial' in home_type:
                    self.data["property_type"] = "Commercial"
                else:
                    # Default assumption for Zillow
                    self.data["property_type"] = "Single Family"
            else:
                # Default assumption
                self.data["property_type"] = "Single Family"

            # Extract additional data
            self.extract_additional_data()

            # Store raw data for debugging
            self.raw_data["url_extracted"] = self.url_data if hasattr(
                self, 'url_data') else {}
            self.raw_data['extraction_status'] = 'success'

            return self.data

        except Exception as e:
            logger.error(f"Error in extraction: {str(e)}")
            logger.error(traceback.format_exc())

            # Mark the extraction as failed but return partial data
            self.raw_data['extraction_status'] = 'failed'
            self.raw_data['extraction_error'] = str(e)

            return self.data
