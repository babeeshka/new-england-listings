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

    def _extract_listing_name_from_url(self) -> str:
        """Generate a listing name from URL."""
        try:
            path_parts = urlparse(self.url).path.split('/')
            if len(path_parts) > 2:
                address_slug = path_parts[2]  # /homedetails/[address-slug]/

                # Convert hyphenated address to readable format
                readable = address_slug.replace('-', ' ').title()

                # Clean up any trailing numbers
                readable = re.sub(r'\s\d+\s?$', '', readable)

                return readable

            return f"Zillow Property {self.zpid}" if self.zpid else "Untitled Zillow Listing"
        except Exception as e:
            logger.debug(f"Error extracting listing name from URL: {e}")
            return f"Zillow Property {self.zpid}" if self.zpid else "Untitled Zillow Listing"

    # These abstract methods MUST BE IMPLEMENTED - they were indented incorrectly
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

            # ...rest of acreage extraction logic...
            # [The rest of your existing extract_acreage_info method would go here - I'm truncating for brevity]

            return "Not specified", "Unknown"

        except Exception as e:
            logger.error(f"Error extracting acreage: {str(e)}")
            return "Not specified", "Unknown"

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

            # ...rest of additional data extraction...
            # [The rest of your existing extract_additional_data method would go here]

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

            # STEP 2: If not blocked, try to extract more data
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

            # STEP 3: Always enrich with location services for maximum data
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
