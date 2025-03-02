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
    """Enhanced extractor for Zillow listings with location-first hybrid approach."""

    def __init__(self, url: str):
        """Initialize extractor with URL and extract zpid."""
        super().__init__(url)
        self.zpid = self._extract_zpid(url)
        self.property_data = None  # Will store extracted JSON data if available
        self.is_blocked = False  # Flag to indicate if we're facing a CAPTCHA/blocking
        self.extraction_source = "unknown"  # Track where data came from

    @property
    def platform_name(self) -> str:
        return "Zillow"

    def _extract_zpid(self, url: str) -> Optional[str]:
        """Extract the Zillow Property ID (zpid) from the URL."""
        zpid_match = re.search(r'\/(\d+)_zpid', url)
        if zpid_match:
            return zpid_match.group(1)
        return None

    def save_debug_html(self):
        """Save HTML for debugging."""
        try:
            with open('zillow_debug.html', 'w', encoding='utf-8') as f:
                f.write(str(self.soup))
            logger.info("Saved HTML to zillow_debug.html for inspection")

            # Also extract any text content to see if it contains useful data
            with open('zillow_text.txt', 'w', encoding='utf-8') as f:
                f.write(self.soup.get_text())
            logger.info("Saved text to zillow_text.txt for inspection")
        except Exception as e:
            logger.error(f"Error saving debug files: {str(e)}")

    def _check_for_blocking(self) -> bool:
        """Check if Zillow is serving a CAPTCHA or blocking page."""
        if not self.soup:
            return True

        # Check page text for blocking indicators
        page_text = self.soup.get_text().lower()
        blocking_indicators = [
            "captcha",
            "security check",
            "please verify",
            "suspicious activity",
            "unusual traffic",
            "press and hold",
            "bot detection",
            "human verification"
        ]

        # Check for empty page or minimal content
        if len(page_text) < 1000:
            logger.warning(
                "Page content is suspiciously short - likely blocked")
            return True

        # Check for blocking indicators
        if any(indicator in page_text for indicator in blocking_indicators):
            logger.warning(
                f"Detected blocking content on Zillow: {[ind for ind in blocking_indicators if ind in page_text]}")
            return True

        # Check for key elements - if ALL are missing, likely blocked
        key_elements = [
            # Any price element
            self.soup.select_one("span[data-testid='price']"),
            self.soup.select_one(".ds-price"),
            # Any address element
            self.soup.select_one("[data-testid='home-details-chip']"),
            # Any facts section
            self.soup.select_one("[data-testid='facts-container']"),
        ]

        if all(elem is None for elem in key_elements):
            logger.warning(
                "All key page elements are missing - likely blocked")
            return True

        return False

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

    def _extract_listing_name_from_url(self) -> str:
        """Generate a listing name from URL."""
        try:
                path_parts = urlparse(self.url).path.split('/')
                if len(path_parts) > 2:
                    # /homedetails/[address-slug]/
                    address_slug = path_parts[2]

                    # Convert hyphenated address to readable format
                    readable = address_slug.replace('-', ' ').title()

                    # Clean up any trailing numbers
                    readable = re.sub(r'\s\d+\s?$', '', readable)

                    return readable

                return f"Zillow Property {self.zpid}" if self.zpid else "Untitled Zillow Listing"
        except Exception as e:
            logger.debug(f"Error extracting listing name from URL: {e}")
            return f"Zillow Property {self.zpid}" if self.zpid else "Untitled Zillow Listing"

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
        """Extract price with enhanced pattern matching."""
        try:
            # STRATEGY 1: Try to extract from JSON data first (most reliable)
            if self.property_data:
                # Check various paths where price might be stored
                price_paths = [
                    # Path 1: Direct price value
                    lambda d: d.get('price'),
                    # Path 2: Formatted price
                    lambda d: d.get('priceFormatted'),
                    # Path 3: Price object
                    lambda d: d.get('price', {}).get('value') if isinstance(
                        d.get('price'), dict) else None,
                    # Path 4: List price
                    lambda d: d.get('listPrice'),
                    # Path 5: Zestimate
                    lambda d: d.get('zestimate', {}).get('amount') if isinstance(
                        d.get('zestimate'), dict) else None,
                    # Path 6: Schema.org price
                    lambda d: d.get('offers', {}).get('price') if isinstance(
                        d.get('offers'), dict) else None,
                    # Path 7: Deep nested price
                    lambda d: d.get('hdpData', {}).get('homeInfo', {}).get(
                        'price') if isinstance(d.get('hdpData'), dict) else None
                ]

                for path_func in price_paths:
                    price_value = path_func(self.property_data)
                    if price_value:
                        if isinstance(price_value, (int, float)):
                            formatted_price = f"${price_value:,}"
                            return self.text_processor.standardize_price(formatted_price)
                        elif isinstance(price_value, str) and any(c.isdigit() for c in price_value):
                            return self.text_processor.standardize_price(price_value)

            # STRATEGY 2: Try direct HTML extraction with multiple selector patterns
            price_selectors = [
                # Current price selector from ZILLOW_SELECTORS
                ZILLOW_SELECTORS["summary"]["price"]["selector"],
                # Additional common Zillow price selectors
                "[data-testid='price']",
                ".price",
                ".ds-price",
                ".hdp__sc-ox3bo0-0",  # Recent selector pattern
                ".Text-c11n-8-99-3__sc-aiai24-0[data-testid='price']",
                "span[data-testid='price']",
                ".eVfrAY",  # Class from the example you shared
                "h3.ds-price"
            ]

            for selector in price_selectors:
                try:
                    price_elem = self.soup.select_one(selector)
                    if price_elem:
                        price_text = price_elem.get_text().strip()
                        if any(c.isdigit() for c in price_text):
                            return self.text_processor.standardize_price(price_text)
                except Exception:
                    continue

            # STRATEGY 3: Look for a price pattern in text with specific context
            price_patterns = [
                # Basic price pattern
                r'\$([\d,]+(?:\.\d+)?)',
                # Price with context
                r'Price: \$([\d,]+(?:\.\d+)?)',
                r'Listed for \$([\d,]+(?:\.\d+)?)',
                r'Listed at \$([\d,]+(?:\.\d+)?)',
                r'Asking \$([\d,]+(?:\.\d+)?)',
                r'Home Value: \$([\d,]+(?:\.\d+)?)'
            ]

            # First try in the summary section, then the whole page
            summary_elem = self.soup.select_one(
                ZILLOW_SELECTORS["summary"]["container"])
            if summary_elem:
                summary_text = summary_elem.get_text()
                for pattern in price_patterns:
                    price_match = re.search(pattern, summary_text)
                    if price_match:
                        price_text = f"${price_match.group(1)}"
                        return self.text_processor.standardize_price(price_text)

            # Try in full page text
            text = self.soup.get_text()
            for pattern in price_patterns:
                price_match = re.search(pattern, text)
                if price_match:
                    price_text = f"${price_match.group(1)}"
                    return self.text_processor.standardize_price(price_text)

            # STRATEGY 4: Extract from URL if it contains price
            price_url_pattern = r'[_-](\d+)k[_-]'
            url_match = re.search(price_url_pattern, self.url.lower())
            if url_match:
                price_value = int(url_match.group(1)) * 1000
                formatted_price = f"${price_value:,}"
                return self.text_processor.standardize_price(formatted_price)

            return "Contact for Price", "N/A"

        except Exception as e:
            logger.error(f"Error extracting price: {str(e)}")
            return "Contact for Price", "N/A"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage with enhanced pattern matching."""
        try:
            # STRATEGY 1: Extract from JSON data
            if self.property_data:
                # Try common property data paths
                lot_paths = [
                    # Path 1: resoFacts (common in Zillow)
                    lambda d: (d.get('resoFacts', {}).get('lotSize'),
                               d.get('resoFacts', {}).get('lotSizeUnit'))
                    if isinstance(d.get('resoFacts'), dict) else (None, None),
                    # Path 2: direct lot size
                    lambda d: (d.get('lotSize'), d.get('lotSizeUnit')),
                    # Path 3: lot area values
                    lambda d: (d.get('lotAreaValue'), d.get('lotAreaUnit')),
                    # Path 4: hdp data
                    lambda d: (d.get('hdpData', {}).get(
                        'homeInfo', {}).get('lotSize'), "sqft")
                    if isinstance(d.get('hdpData'), dict) else (None, None),
                    # Path 5: fact list
                    lambda d: next(((item.get('factValue'), item.get('factValueUnit'))
                                    for item in d.get('facts', [])
                                    if isinstance(item, dict) and 'lot' in item.get('factLabel', '').lower()),
                                   (None, None))
                    if isinstance(d.get('facts'), list) else (None, None)
                ]

                for path_func in lot_paths:
                    lot_size, unit = path_func(self.property_data)
                    if lot_size:
                        # Convert to acres if in sq ft
                        if unit and str(unit).lower() in ['sqft', 'sq ft', 'square feet', 'square foot']:
                            try:
                                acres = float(lot_size) / 43560
                                return self.text_processor.standardize_acreage(f"{acres:.2f} acres")
                            except (ValueError, TypeError):
                                pass
                        else:
                            # Assume acres or add unit if provided
                            unit_str = f" {unit}" if unit and unit.lower(
                            ) != 'acres' else " acres"
                            return self.text_processor.standardize_acreage(f"{lot_size}{unit_str}")

            # STRATEGY 2: Use Fact categories from HTML
            lot_section_selectors = [
                # Headers or section titles that might contain lot information
                'h6:-soup-contains("Lot")',
                '.ds-data-heading:-soup-contains("Lot")',
                '.ds-section-title:-soup-contains("Lot")',
                '.dFhjAe',  # Class from the example you shared
                '.Text-c11n-8-99-3__sc-aiai24-0:-soup-contains("Lot")',
                # Parent sections
                'section[data-testid="lot-section"]',
                '[data-testid="facts-section"]'
            ]

            for selector in lot_section_selectors:
                try:
                    section = self.soup.select_one(selector)
                    if section:
                        # Look for size within this section - first try list items
                        list_items = section.find_all('li')
                        for li in list_items:
                            li_text = li.get_text().lower()
                            if 'size' in li_text and ('acre' in li_text or 'acres' in li_text):
                                # Extract acreage from the list item
                                acre_match = re.search(
                                    r'(\d+(?:\.\d+)?)\s*acres?', li_text)
                                if acre_match:
                                    return self.text_processor.standardize_acreage(f"{acre_match.group(1)} acres")

                        # If list items don't work, try the whole section text
                        section_text = section.get_text().lower()
                        acre_match = re.search(
                            r'(\d+(?:\.\d+)?)\s*acres?', section_text)
                        if acre_match:
                            return self.text_processor.standardize_acreage(f"{acre_match.group(1)} acres")

                        # Try square feet pattern and convert to acres
                        sqft_match = re.search(
                            r'(\d+(?:,\d+)?)\s*(?:sq\.?\s*ft\.?|square\s*feet)', section_text)
                        if sqft_match:
                            try:
                                sqft = float(sqft_match.group(1).replace(',', ''))
                                acres = sqft / 43560
                                return self.text_processor.standardize_acreage(f"{acres:.2f} acres")
                            except (ValueError, TypeError):
                                pass
                except Exception:
                    continue

            # STRATEGY 3: Search whole page text for acre mentions
            # First look in Facts sections
            facts_section = self.soup.select_one(
                ZILLOW_SELECTORS["summary"]["facts"]["selector"])
            if facts_section:
                facts_text = facts_section.get_text().lower()

                # Look for acre patterns
                acre_patterns = [
                    r'(\d+(?:\.\d+)?)\s*acres?',
                    r'lot\s*(?:size)?:?\s*(\d+(?:\.\d+)?)\s*acres?',
                    r'lot\s*size:?\s*(\d+(?:,\d+)?)\s*sq\s*\.?\s*ft\.'
                ]

                for pattern in acre_patterns:
                    match = re.search(pattern, facts_text)
                    if match:
                        # Convert sqft to acres if needed
                        if 'sq' in pattern:
                            try:
                                sqft = float(match.group(1).replace(',', ''))
                                acres = sqft / 43560
                                return self.text_processor.standardize_acreage(f"{acres:.2f} acres")
                            except (ValueError, TypeError):
                                pass
                        else:
                            return self.text_processor.standardize_acreage(f"{match.group(1)} acres")

            # STRATEGY 4: Search full page for lot sizes
            full_text = self.soup.get_text().lower()

            # Look specifically for patterns likely to indicate lot size
            lot_size_patterns = [
                r'lot\s*size:?\s*(\d+(?:\.\d+)?)\s*acres?',
                r'(\d+(?:\.\d+)?)\s*acres?\s*lot',
                r'property\s*size:?\s*(\d+(?:\.\d+)?)\s*acres?',
                r'land\s*size:?\s*(\d+(?:\.\d+)?)\s*acres?',
                # The pattern from your example: "Size: 78 Acres"
                r'size:?\s*(\d+(?:\.\d+)?)\s*acres?'
            ]

            for pattern in lot_size_patterns:
                match = re.search(pattern, full_text)
                if match:
                    return self.text_processor.standardize_acreage(f"{match.group(1)} acres")

            # As a last resort, search for any mention of acres
            acres_match = re.search(r'(\d+(?:\.\d+)?)\s*acres?', full_text)
            if acres_match:
                return self.text_processor.standardize_acreage(f"{acres_match.group(1)} acres")

            return "Not specified", "Unknown"

        except Exception as e:
            logger.error(f"Error extracting acreage: {str(e)}")
            return "Not specified", "Unknown"

    def _extract_location_from_url(self) -> Optional[str]:
        """Extract location from URL when other methods fail."""
        try:
                # Extract from URL path pattern: /homedetails/534-Reef-Rd-Waldoboro-ME-04572/224599069_zpid
                path_parts = urlparse(self.url).path.split('/')
                if len(path_parts) > 2:
                    address_part = path_parts[2]  # Get the address slug

                    # Try to find STATE-ZIP pattern (like ME-04572)
                    state_zip_match = re.search(
                        r'-([A-Z]{2})-(\d{5})', address_part)
                    if state_zip_match:
                        state = state_zip_match.group(1)

                        # Find the town/city before the state
                        town_pattern = r'-([\w-]+)-' + state
                        town_match = re.search(town_pattern, address_part)

                        if town_match:
                            town = town_match.group(1).replace('-', ' ').title()
                            return f"{town}, {state}"

                    # Fallback: try simpler pattern for just State
                    simpler_match = re.search(
                        r'-([\w-]+)-([A-Z]{2})', address_part)
                    if simpler_match:
                        town = simpler_match.group(1).replace('-', ' ').title()
                        state = simpler_match.group(2)
                        return f"{town}, {state}"

                return None
        except Exception as e:
            logger.debug(f"Error extracting location from URL: {e}")
            return None

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

    def extract_property_details(self) -> Dict[str, Any]:
        """Extract comprehensive property details."""
        details = {}

        try:
            # Try to extract from JSON data first
            if self.property_data:
                # Try to get basic facts
                if isinstance(self.property_data.get('resoFacts'), dict):
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
                if isinstance(self.property_data.get('homeFactsList'), list):
                    features = []
                    for fact in self.property_data['homeFactsList']:
                        if isinstance(fact, dict) and 'factLabel' in fact and 'factValue' in fact:
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
        """Main extraction method with hybrid location-first approach."""
        self.soup = soup
        self.raw_data = {}

        try:
            # Save debug info
            self.save_debug_html()

            # Check if we're blocked
            self.is_blocked = self._check_for_blocking()

            # Set up default data structure
            self.data = {
                "url": self.url,
                "platform": "Zillow",
                "listing_name": "Untitled Zillow Listing",
                "location": "Location Unknown",
                "price": "Contact for Price",
                "price_bucket": "N/A",
                "property_type": "Single Family",
                "acreage": "Not specified",
                "acreage_bucket": "Unknown",
                "last_updated": datetime.now(),
                "data_source": "hybrid"  # Track data source
            }

            # Always include the zpid if available
            if self.zpid:
                self.data["zpid"] = self.zpid

            # STEP 1: Extract minimal core data regardless of blocking
            # Always try to get location from URL if nothing else
            location_from_url = self._extract_location_from_url()
            if location_from_url:
                self.data["location"] = location_from_url
                self.extraction_source = "url"

            # Basic listing name from URL
            listing_name_from_url = self._extract_listing_name_from_url()
            if listing_name_from_url:
                self.data["listing_name"] = listing_name_from_url

            # STEP 2: If blocked, try to use property records if we have the address
            if self.is_blocked and location_from_url:
                # This would attempt to get property data from county records
                # Extract address and town from location
                address_match = re.match(
                    r'^(.+),\s*([^,]+),\s*([A-Z]{2})', self.data["listing_name"])
                if address_match:
                    street_address = address_match.group(1).strip()
                    town = address_match.group(2).strip()
                    state = address_match.group(3).strip()

                    try:
                        from ..utils.property_records import MainePropertyRecords
                        records = MainePropertyRecords()
                        property_data = records.search_by_address(
                            street_address, town, state)

                        if property_data and not property_data.get('requires_implementation', True):
                            # If we got actual data (not just a stub), use it
                            logger.info(
                                f"Found property data from county records: {property_data}")

                            # Add property record data to our results
                            if 'price' in property_data:
                                self.data["price"] = property_data['price']
                                if hasattr(self.text_processor, 'standardize_price'):
                                    _, price_bucket = self.text_processor.standardize_price(
                                        property_data['price'])
                                    self.data["price_bucket"] = price_bucket

                            if 'acreage' in property_data:
                                self.data["acreage"] = property_data['acreage']
                                if hasattr(self.text_processor, 'standardize_acreage'):
                                    _, acreage_bucket = self.text_processor.standardize_acreage(
                                        property_data['acreage'])
                                    self.data["acreage_bucket"] = acreage_bucket

                            self.data["property_records_source"] = property_data.get(
                                'source')
                            self.data["property_records_url"] = property_data.get(
                                'record_url')
                    except Exception as e:
                        logger.error(f"Error getting property records: {e}")

            # STEP 3: If not blocked, try to extract more data
            if not self.is_blocked:
                # Try to extract JSON data
                self.property_data = self._extract_json_data()

                # Only proceed with detailed extraction if we're not blocked
                logger.info("Not blocked - attempting full Zillow extraction")

                # Try to get core property details
                try:
                    listing_name = self.extract_listing_name()
                    if listing_name and len(listing_name) > 5:
                        self.data["listing_name"] = listing_name
                        self.extraction_source = "direct"
                except Exception as e:
                    logger.debug(f"Error extracting listing name: {e}")

                try:
                    location = self.extract_location()
                    if location and location != "Location Unknown":
                        self.data["location"] = location
                        self.extraction_source = "direct"
                except Exception as e:
                    logger.debug(f"Error extracting location: {e}")

                try:
                    price, price_bucket = self.extract_price()
                    if price != "Contact for Price":
                        self.data["price"] = price
                        self.data["price_bucket"] = price_bucket
                        self.extraction_source = "direct"
                except Exception as e:
                    logger.debug(f"Error extracting price: {e}")

                try:
                    acreage, acreage_bucket = self.extract_acreage_info()
                    if acreage != "Not specified":
                        self.data["acreage"] = acreage
                        self.data["acreage_bucket"] = acreage_bucket
                        self.extraction_source = "direct"
                except Exception as e:
                    logger.debug(f"Error extracting acreage: {e}")

                # Property details like beds/baths if available
                try:
                    details = self.extract_property_details()
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

                    # Description as notes
                    if 'description' in details and details['description']:
                        self.data["notes"] = details['description']
                except Exception as e:
                    logger.debug(f"Error extracting property details: {e}")
            else:
                logger.warning(
                    "Zillow blocking detected - relying on location services")
                self.data["extraction_blocked"] = True

            # STEP 4: Always enrich with location services for maximum data
            if self.data["location"] != "Location Unknown":
                logger.info(
                    f"Enriching with location services for: {self.data['location']}")

                # Get comprehensive location info
                try:
                    location_info = self.location_service.get_comprehensive_location_info(
                        self.data["location"])

                    # Add all location data
                    for key, value in location_info.items():
                        if key not in self.data or not self.data[key]:
                            self.data[key] = value

                    # Track that we used location services
                    self.data["location_enriched"] = True
                except Exception as e:
                    logger.error(
                        f"Error enriching with location services: {e}")
            else:
                logger.warning("Cannot enrich without valid location")

            # Log extraction source for transparency
            logger.info(
                f"Data source: {self.extraction_source}, Location enriched: {self.data.get('location_enriched', False)}")

            self.raw_data['extraction_status'] = 'success'
            return self.data

        except Exception as e:
            logger.error(f"Error in extraction: {str(e)}")
            logger.debug(traceback.format_exc())

            # Mark as failed but return what we have
            self.raw_data['extraction_status'] = 'failed'
            self.raw_data['extraction_error'] = str(e)

            return self.data
