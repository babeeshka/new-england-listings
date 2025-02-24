# src/new_england_listings/extractors/realtor.py

from typing import Dict, Any, Tuple, Optional, List
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime
from .base import BaseExtractor
from ..models.base import (
    PropertyType, PriceBucket, AcreageBucket,
    DistanceBucket, SchoolRatingCategory, TownPopulationBucket
)
from ..utils.text import clean_html_text, extract_acreage, clean_price
from ..utils.dates import extract_listing_date
from ..utils.geocoding import get_comprehensive_location_info

logger = logging.getLogger(__name__)

REALTOR_SELECTORS = {
    "price": {
        "main": {"data-testid": "list-price"},
        "formatted": {"data-testid": "price"},
        "container": {"class_": "Price__Component"}
    },
    "details": {
        "container": {"data-testid": "property-meta"},
        "beds": {"data-testid": "property-meta-beds"},
        "baths": {"data-testid": "property-meta-baths"},
        "sqft": {"data-testid": "property-meta-sqft"},
        "lot": {"data-testid": "property-meta-lot-size"},
        "type": {"data-testid": "property-type"},
        "features": {"data-testid": "property-features"},
        "amenities": {"class_": "amenities-container"}
    },
    "location": {
        "address": {"data-testid": "address"},
        "city_state": {"data-testid": "city-state"}
    },
    "description": {
        "container": {"data-testid": "description"},
        "truncated": {"class_": "truncated-text"}
    },
    "status": {
        "date": {"class_": "list-date"}
    }
}


class RealtorExtractionError(Exception):
    """Custom exception for Realtor.com extraction errors."""
    pass


class RealtorExtractor(BaseExtractor):
    """Enhanced extractor for Realtor.com listings."""

    def __init__(self, url: str):
        super().__init__(url)
        # Store URL data for fallbacks
        self.url_data = self._extract_from_url()

    @property
    def platform_name(self) -> str:
        return "Realtor.com"

    def _extract_from_url(self) -> Dict[str, Any]:
        """Extract useful information from the URL as a fallback."""
        data = {}
        try:
            # Try to extract location from URL pattern
            # Example: /realestateandhomes-detail/1-Town-Farm-Rd_Windham_ME_04062_M31064-16251
            url_parts = self.url.split('/')[-1].split('_')
            if len(url_parts) >= 3:
                street = url_parts[0].replace('-', ' ').title()
                city = url_parts[1].replace('-', ' ').title()
                state = url_parts[2]

                data['location'] = f"{city}, {state}"
                data['listing_name'] = f"{street}, {city}, {state}"
                # Default assumption for Realtor.com
                data['property_type'] = PropertyType.SINGLE_FAMILY

                # Get zip code if available
                if len(url_parts) >= 4:
                    zip_code = url_parts[3]
                    if re.match(r'^\d{5}(-\d{4})?$', zip_code):
                        data['location'] = f"{city}, {state} {zip_code}"
                        data['listing_name'] = f"{street}, {city}, {state} {zip_code}"
        except Exception as e:
            logger.warning(f"Error extracting data from URL: {str(e)}")

        return data

    def _verify_page_content(self) -> bool:
        """Verify the page content was properly loaded."""
        logger.debug("Verifying page content...")

        # Check for our custom meta tag that indicates blocking was detected
        blocking_meta = self.soup.find(
            "meta", {"name": "extraction-status", "content": "blocked-but-attempting"})
        if blocking_meta:
            logger.warning(
                "Page was blocked but continuing with limited extraction")
            # We'll return True here to allow the extraction process to continue
            return True

        # Check for essential elements
        essential_elements = [
            self.soup.find(**REALTOR_SELECTORS["price"]["main"]),
            self.soup.find(**REALTOR_SELECTORS["details"]["container"]),
            self.soup.find(**REALTOR_SELECTORS["location"]["address"])
        ]

        # Debug logging
        for selector_type, selectors in REALTOR_SELECTORS.items():
            for name, selector in selectors.items():
                try:
                    elem = self.soup.find(**selector)
                    logger.debug(f"{selector_type}.{name}: {elem is not None}")
                except Exception as e:
                    logger.debug(
                        f"Error checking {selector_type}.{name}: {str(e)}")

        # Check for blocking elements but don't immediately fail
        page_text = self.soup.get_text().lower()
        blocking_patterns = [
            "captcha",
            "security check",
            "please verify",
            "access denied",
            "pardon our interruption"
        ]

        if any(pattern in page_text for pattern in blocking_patterns):
            logger.warning(
                f"Potential blocking detected, but continuing with limited extraction")
            return True  # Return true to continue with extraction

        return any(essential_elements)

    def extract_listing_name(self) -> str:
        """Extract listing name from address."""
        try:
            # Try address data-testid first
            address = self.soup.find(
                **REALTOR_SELECTORS["location"]["address"])
            if address:
                return clean_html_text(address.text)

            # Look for any address-like text in h1 tags
            for h1 in self.soup.find_all('h1'):
                text = clean_html_text(h1.text)
                # Looks like an address with number and street
                if re.search(r'\d+\s+\w+', text):
                    return text

            # Try URL-based extraction as fallback
            if 'listing_name' in self.url_data:
                return self.url_data['listing_name']

            # Fallback to location
            location = self.extract_location()
            if location != "Location Unknown":
                return f"Property at {location}"

            return "Untitled Listing"

        except Exception as e:
            logger.error(f"Error extracting listing name: {str(e)}")
            # Fallback to URL extraction on error
            if 'listing_name' in self.url_data:
                return self.url_data['listing_name']
            return "Untitled Listing"

    def extract_price(self) -> Tuple[str, PriceBucket]:
        """Extract price with enhanced validation."""
        try:
            # Try main price element
            price_elem = self.soup.find(**REALTOR_SELECTORS["price"]["main"])
            if price_elem:
                self.raw_data["price_text"] = price_elem.text
                return clean_price(price_elem.text)

            # Try formatted price
            formatted_elem = self.soup.find(
                **REALTOR_SELECTORS["price"]["formatted"])
            if formatted_elem:
                return clean_price(formatted_elem.text)

            # Try price container
            container = self.soup.find(
                **REALTOR_SELECTORS["price"]["container"])
            if container:
                price_text = container.get_text()
                if '$' in price_text:
                    return clean_price(price_text)

            # Search for dollar amount in any text
            dollar_pattern = r'\$\s*([\d,]+)'
            for div in self.soup.find_all(['div', 'span', 'h1', 'h2']):
                match = re.search(dollar_pattern, div.text)
                if match:
                    return clean_price(match.group(1))

            return "Contact for Price", PriceBucket.NA

        except Exception as e:
            logger.error(f"Error extracting price: {str(e)}")
            return "Contact for Price", PriceBucket.NA

    def extract_location(self) -> str:
        """Extract location with enhanced validation."""
        try:
            # Check if we have a URL-extracted location in our meta tag
            url_location_meta = self.soup.find(
                "meta", {"name": "url-extracted-location"})
            if url_location_meta:
                location = url_location_meta.get("content")
                if location and self._validate_location(location):
                    return location

            # Try separate address components
            address_part = self.soup.find(
                **REALTOR_SELECTORS["location"]["address"])
            city_state = self.soup.find(
                **REALTOR_SELECTORS["location"]["city_state"])

            if address_part and city_state:
                location = f"{clean_html_text(address_part.text)}, {clean_html_text(city_state.text)}"
                if self._validate_location(location):
                    return location

            # Look for location pattern in h1/h2 tags
            for tag in self.soup.find_all(['h1', 'h2']):
                text = clean_html_text(tag.text)
                location_match = re.search(r'([A-Za-z\s]+,\s*[A-Z]{2})', text)
                if location_match:
                    location = location_match.group(1)
                    if self._validate_location(location):
                        return location

            # Try extracting from URL using fallback data
            if 'location' in self.url_data:
                return self.url_data['location']

            # Last resort - try extracting from URL
            parts = self.url.split('_')
            if len(parts) >= 3:
                city = parts[-3].replace('-', ' ').title()
                state = parts[-2].upper()
                return f"{city}, {state}"

            return "Location Unknown"

        except Exception as e:
            logger.error(f"Error extracting location: {str(e)}")
            # Try fallback on error
            if 'location' in self.url_data:
                return self.url_data['location']
            return "Location Unknown"

    def _validate_location(self, location: str) -> bool:
        """Validate location string."""
        if not location:
            return False
        # Check for New England state reference
        state_pattern = r'(?:ME|NH|VT|MA|CT|RI|Maine|New\s+Hampshire|Vermont|Massachusetts|Connecticut|Rhode\s+Island)\b'
        return bool(re.search(state_pattern, location, re.I))

    def extract_acreage_info(self) -> Tuple[str, AcreageBucket]:
        """Extract acreage with enhanced validation."""
        try:
            # Try the data-testid selector first
            lot_elem = self.soup.find(**REALTOR_SELECTORS["details"]["lot"])
            if lot_elem:
                lot_text = clean_html_text(lot_elem.text)
                self.raw_data["lot_text"] = lot_text

                # Handle different size formats
                acre_match = re.search(r'([\d,.]+)\s*acres?', lot_text, re.I)
                if acre_match:
                    return extract_acreage(f"{acre_match.group(1)} acres")

                sqft_match = re.search(
                    r'([\d,.]+)\s*sq\s*\.?\s*ft', lot_text, re.I)
                if sqft_match:
                    sqft = float(sqft_match.group(1).replace(',', ''))
                    acres = sqft / 43560  # Convert sqft to acres
                    return extract_acreage(f"{acres:.2f} acres")

            # Look for lot size in any div with relevant terms
            lot_pattern = re.compile(r'([\d,.]+)\s*acres?', re.I)
            sqft_pattern = re.compile(r'([\d,.]+)\s*sq\s*\.?\s*ft', re.I)

            # First look for acre mentions
            for div in self.soup.find_all(['div', 'span', 'p']):
                div_text = div.get_text()
                if 'lot' in div_text.lower() or 'acres' in div_text.lower():
                    acre_match = lot_pattern.search(div_text)
                    if acre_match:
                        return extract_acreage(f"{acre_match.group(1)} acres")

            # Then look for sqft mentions
            for div in self.soup.find_all(['div', 'span', 'p']):
                div_text = div.get_text()
                if 'lot' in div_text.lower() or 'sq ft' in div_text.lower():
                    sqft_match = sqft_pattern.search(div_text)
                    if sqft_match:
                        sqft = float(sqft_match.group(1).replace(',', ''))
                        acres = sqft / 43560  # Convert sqft to acres
                        return extract_acreage(f"{acres:.2f} acres")

            # Try description
            description = self.extract_description()
            if description:
                acre_match = lot_pattern.search(description)
                if acre_match:
                    return extract_acreage(f"{acre_match.group(1)} acres")

                sqft_match = sqft_pattern.search(description)
                if sqft_match:
                    sqft = float(sqft_match.group(1).replace(',', ''))
                    acres = sqft / 43560  # Convert sqft to acres
                    return extract_acreage(f"{acres:.2f} acres")

            return "Not specified", AcreageBucket.UNKNOWN

        except Exception as e:
            logger.error(f"Error extracting acreage: {str(e)}")
            return "Not specified", AcreageBucket.UNKNOWN

    def extract_property_details(self) -> Dict[str, Any]:
        """Extract comprehensive property details."""
        try:
            details = {}
            container = self.soup.find(
                **REALTOR_SELECTORS["details"]["container"])

            if container:
                # Extract basic metrics
                metrics = {
                    "beds": REALTOR_SELECTORS["details"]["beds"],
                    "baths": REALTOR_SELECTORS["details"]["baths"],
                    "sqft": REALTOR_SELECTORS["details"]["sqft"]
                }

                for key, selector in metrics.items():
                    try:
                        elem = container.find(**selector)
                        if elem:
                            value = clean_html_text(elem.text)
                            match = re.search(r'(\d+(?:\.\d+)?)', value)
                            if match:
                                details[key] = match.group(1)
                    except Exception as e:
                        logger.debug(f"Error extracting {key}: {str(e)}")

                # Extract property type
                try:
                    type_elem = container.find(
                        **REALTOR_SELECTORS["details"]["type"])
                    if type_elem:
                        details["property_type"] = clean_html_text(
                            type_elem.text)
                except Exception as e:
                    logger.debug(f"Error extracting property type: {str(e)}")

            # If we couldn't get details from the container, try generic approach
            if not details:
                # Look for bed/bath mentions in any text
                for div in self.soup.find_all(['div', 'span', 'p']):
                    text = div.get_text()

                    # Look for beds
                    if 'bed' in text.lower():
                        bed_match = re.search(
                            r'(\d+(?:\.\d+)?)\s*bed', text, re.I)
                        if bed_match and "beds" not in details:
                            details["beds"] = bed_match.group(1)

                    # Look for baths
                    if 'bath' in text.lower():
                        bath_match = re.search(
                            r'(\d+(?:\.\d+)?)\s*bath', text, re.I)
                        if bath_match and "baths" not in details:
                            details["baths"] = bath_match.group(1)

                    # Look for square footage
                    if 'sq ft' in text.lower() or 'sqft' in text.lower():
                        sqft_match = re.search(
                            r'(\d+(?:,\d+)?)\s*sq', text, re.I)
                        if sqft_match and "sqft" not in details:
                            details["sqft"] = sqft_match.group(
                                1).replace(',', '')

            # Extract features
            features = self.extract_features()
            if features:
                details["features"] = features

            return details

        except Exception as e:
            logger.error(f"Error extracting property details: {str(e)}")
            return {}

    def extract_features(self) -> List[str]:
        """Extract property features and amenities."""
        try:
            features = set()

            # Try the features section first
            try:
                features_section = self.soup.find(
                    **REALTOR_SELECTORS["details"]["features"])
                if features_section:
                    for item in features_section.find_all(["li", "div"]):
                        feature = clean_html_text(item.text)
                        if feature:
                            features.add(feature)
            except Exception as e:
                logger.debug(f"Error extracting features: {str(e)}")

            # Try amenities section
            try:
                amenities_section = self.soup.find(
                    **REALTOR_SELECTORS["details"]["amenities"])
                if amenities_section:
                    for item in amenities_section.find_all(["li", "div"]):
                        feature = clean_html_text(item.text)
                        if feature:
                            features.add(feature)
            except Exception as e:
                logger.debug(f"Error extracting amenities: {str(e)}")

            # Look for features in description
            description = self.extract_description()
            if description:
                # Look for common feature patterns
                feature_indicators = [
                    "features include",
                    "amenities include",
                    "property features",
                    "highlights",
                    "this home includes"
                ]

                for indicator in feature_indicators:
                    if indicator in description.lower():
                        parts = description.split(indicator, 1)[1].split(".")
                        if parts:
                            feature_text = parts[0]
                            # Split by commas or "and"
                            for feature in re.split(r',|\sand\s', feature_text):
                                clean_feature = clean_html_text(feature)
                                if clean_feature and len(clean_feature) > 3:
                                    features.add(clean_feature)

            return list(features)

        except Exception as e:
            logger.error(f"Error extracting features: {str(e)}")
            return []

    def determine_property_type(self, details: Dict[str, Any]) -> PropertyType:
        """Determine property type from extracted details."""
        try:
            # Check explicit property type
            prop_type = details.get("property_type", "").lower()

            if "single family" in prop_type or "house" in prop_type:
                return PropertyType.SINGLE_FAMILY
            elif "farm" in prop_type or "ranch" in prop_type:
                return PropertyType.FARM
            elif "commercial" in prop_type:
                return PropertyType.COMMERCIAL
            elif "land" in prop_type or "lot" in prop_type:
                return PropertyType.LAND

            # Check features
            features = details.get("features", [])
            features_text = " ".join(features).lower()

            if "farm" in features_text or "barn" in features_text:
                return PropertyType.FARM
            elif any(x in features_text for x in ["house", "bedroom", "bathroom"]):
                return PropertyType.SINGLE_FAMILY
            elif "commercial" in features_text:
                return PropertyType.COMMERCIAL
            elif "land" in features_text:
                return PropertyType.LAND

            # Look for property type in page text
            page_text = self.soup.get_text().lower()
            if "farm" in page_text and ("barn" in page_text or "acres" in page_text):
                return PropertyType.FARM
            elif "vacant land" in page_text or "empty lot" in page_text:
                return PropertyType.LAND
            elif "commercial" in page_text and "business" in page_text:
                return PropertyType.COMMERCIAL

            # If beds/baths are present, assume single family
            if details.get("beds") or details.get("baths"):
                return PropertyType.SINGLE_FAMILY

            # Fallback to URL data
            if 'property_type' in self.url_data:
                return self.url_data.get('property_type')

            return PropertyType.UNKNOWN

        except Exception as e:
            logger.error(f"Error determining property type: {str(e)}")
            return PropertyType.UNKNOWN

    def extract_additional_data(self):
        """Extract all additional property information."""
        try:
            # Extract property details
            details = self.extract_property_details()
            self.raw_data["property_details"] = details

            # Set property type
            self.data["property_type"] = self.determine_property_type(details)

            # Format house details
            house_info = []
            if details.get("beds"):
                house_info.append(f"{details['beds']} bedrooms")
            if details.get("baths"):
                house_info.append(f"{details['baths']} bathrooms")
            if details.get("sqft"):
                house_info.append(f"{details['sqft']} sqft")
            if house_info:
                self.data["house_details"] = " | ".join(house_info)

            # Extract amenities
            if details.get("features"):
                amenities = [f for f in details["features"]
                             if not any(x in f.lower() for x in ["house", "residential", "farm", "land"])]
                if amenities:
                    self.data["other_amenities"] = " | ".join(amenities)

            # Extract description as notes
            description = self.extract_description()
            if description:
                self.data["notes"] = description

            # Try to find listing date
            try:
                # First look for date elements
                date_elem = None
                try:
                    date_elem = self.soup.find(
                        **REALTOR_SELECTORS["status"]["date"])
                except:
                    pass

                if date_elem:
                    date_text = clean_html_text(date_elem.text)
                    self.data["listing_date"] = extract_listing_date(date_text)
                else:
                    # Look for date patterns in text
                    for div in self.soup.find_all(['div', 'span', 'p']):
                        text = div.get_text()
                        if any(x in text.lower() for x in ["listed", "posted", "date"]):
                            date_match = re.search(
                                r'\d{1,2}/\d{1,2}/\d{4}', text)
                            if date_match:
                                self.data["listing_date"] = date_match.group(0)
                                break
            except Exception as e:
                logger.warning(f"Error parsing listing date: {str(e)}")

            # Process location information
            if self.data["location"] != "Location Unknown":
                try:
                    location_info = get_comprehensive_location_info(
                        self.data["location"])
                    if location_info:
                        self._process_location_info(location_info)
                except Exception as e:
                    logger.error(f"Error processing location info: {str(e)}")

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")
            self.raw_data["extraction_error"] = str(e)

    def _process_location_info(self, location_info: Dict[str, Any]):
        """Process and validate location-based information."""
        try:
            # Distance metrics
            if 'distance_to_portland' in location_info:
                self.data["distance_to_portland"] = float(
                    location_info["distance_to_portland"])
                self.data["portland_distance_bucket"] = self._get_distance_bucket(
                    float(location_info["distance_to_portland"]))

            # Population metrics
            if 'town_population' in location_info:
                self.data["town_population"] = int(
                    location_info["town_population"])
                self.data["town_pop_bucket"] = self._get_population_bucket(
                    int(location_info["town_population"]))

            # School metrics
            if 'school_rating' in location_info:
                self.data["school_rating"] = float(
                    location_info["school_rating"])
                self.data["school_rating_cat"] = self._get_school_rating_category(
                    float(location_info["school_rating"]))
                if 'school_district' in location_info:
                    self.data["school_district"] = location_info["school_district"]

            # Healthcare metrics
            if 'hospital_distance' in location_info:
                self.data["hospital_distance"] = float(
                    location_info["hospital_distance"])
                self.data["hospital_distance_bucket"] = self._get_distance_bucket(
                    float(location_info["hospital_distance"]))
                if 'closest_hospital' in location_info:
                    self.data["closest_hospital"] = location_info["closest_hospital"]

            # Amenities metrics
            if 'restaurants_nearby' in location_info:
                self.data["restaurants_nearby"] = int(
                    location_info["restaurants_nearby"])
            if 'grocery_stores_nearby' in location_info:
                self.data["grocery_stores_nearby"] = int(
                    location_info["grocery_stores_nearby"])

            # Store raw location data for debugging
            self.raw_data["location_info"] = location_info

        except Exception as e:
            logger.error(f"Error processing location info: {str(e)}")
            self.raw_data["location_processing_error"] = str(e)

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

    def extract_description(self) -> Optional[str]:
        """Extract and clean property description."""
        try:
            description = []
            try:
                desc_container = self.soup.find(
                    **REALTOR_SELECTORS["description"]["container"])
                if desc_container:
                    # Check for truncated text first
                    try:
                        truncated = desc_container.find(
                            **REALTOR_SELECTORS["description"]["truncated"])
                        if truncated:
                            return clean_html_text(truncated.text)
                    except:
                        pass

                    # Otherwise get all text content
                    paragraphs = desc_container.find_all("p") or [
                        desc_container]
                    for p in paragraphs:
                        text = clean_html_text(p.text)
                        if text and "listing provided by" not in text.lower():
                            description.append(text)
            except Exception as e:
                logger.debug(f"Error with description container: {str(e)}")

            # If no description found, look for chunks of text
            if not description:
                # Look for paragraphs with substantial text
                for p in self.soup.find_all('p'):
                    text = clean_html_text(p.text)
                    if len(text) > 100 and not any(x in text.lower() for x in ["listing provided by", "disclaimer", "copyright"]):
                        description.append(text)

            return " ".join(description) if description else None

        except Exception as e:
            logger.error(f"Error extracting description: {str(e)}")
            return None

    def extract(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Main extraction method with enhanced validation."""
        self.soup = soup

        # Verify page content first
        if not self._verify_page_content():
            logger.warning(
                "Page content verification failed, but continuing with limited extraction")
            # NOT raising an exception here to allow fallback methods to work

        try:
            # Extract core data directly
            try:
                self.data["listing_name"] = self.extract_listing_name()
            except Exception as e:
                logger.error(f"Error extracting listing name: {str(e)}")
                if 'listing_name' in self.url_data:
                    self.data["listing_name"] = self.url_data['listing_name']
                else:
                    self.data["listing_name"] = "Untitled Listing"

            try:
                self.data["location"] = self.extract_location()
            except Exception as e:
                logger.error(f"Error extracting location: {str(e)}")
                if 'location' in self.url_data:
                    self.data["location"] = self.url_data['location']
                else:
                    self.data["location"] = "Location Unknown"

            try:
                self.data["price"], self.data["price_bucket"] = self.extract_price()
            except Exception as e:
                logger.error(f"Error extracting price: {str(e)}")
                self.data["price"], self.data["price_bucket"] = "Contact for Price", PriceBucket.NA

            try:
                self.data["acreage"], self.data["acreage_bucket"] = self.extract_acreage_info(
                )
            except Exception as e:
                logger.error(f"Error extracting acreage: {str(e)}")
                self.data["acreage"], self.data["acreage_bucket"] = "Not specified", AcreageBucket.UNKNOWN

            # Extract additional platform-specific data
            try:
                self.extract_additional_data()
            except Exception as e:
                logger.error(f"Error in additional data extraction: {str(e)}")

            # Extract description for notes if not already set
            if "notes" not in self.data:
                try:
                    description = self.extract_description()
                    if description:
                        self.data["notes"] = description
                except Exception as e:
                    logger.error(f"Error extracting description: {str(e)}")

            # Add verification step for property type
            if "property_type" not in self.data or self.data["property_type"] == PropertyType.UNKNOWN:
                try:
                    details = self.extract_property_details()
                    self.data["property_type"] = self.determine_property_type(
                        details)
                except Exception as e:
                    logger.error(f"Error determining property type: {str(e)}")
                    self.data["property_type"] = PropertyType.UNKNOWN

            # Additional verification for location
            if self.data["location"] == "Location Unknown" and 'location' in self.url_data:
                self.data["location"] = self.url_data['location']

            # Process location information for additional data fields
            if self.data["location"] != "Location Unknown":
                try:
                    location_info = get_comprehensive_location_info(
                        self.data["location"])
                    if location_info:
                        self._process_location_info(location_info)
                except Exception as e:
                    logger.error(f"Error getting location info: {str(e)}")

            # Store raw data for debugging
            self.data["raw_data"] = self.raw_data

            return self.data

        except Exception as e:
            logger.error(f"Error in extraction: {str(e)}")

            # Create minimal record with URL data if available
            if self.url_data:
                for key, value in self.url_data.items():
                    if key not in self.data or not self.data[key]:
                        self.data[key] = value

                # Set default values for required fields
                if "price" not in self.data:
                    self.data["price"], self.data["price_bucket"] = "Contact for Price", PriceBucket.NA
                if "acreage" not in self.data:
                    self.data["acreage"], self.data["acreage_bucket"] = "Not specified", AcreageBucket.UNKNOWN

                return self.data

            raise RealtorExtractionError(
                f"Failed to extract listing data: {str(e)}")

    def _clean_measurements(self, text: str) -> Optional[float]:
        """Clean and convert measurement strings to float values."""
        try:
            # Remove commas and non-numeric characters except decimal points
            cleaned = re.sub(r'[^\d.]', '', text)
            if cleaned:
                return float(cleaned)
            return None
        except (ValueError, TypeError):
            return None

    def _extract_date(self, text: str) -> Optional[datetime]:
        """Extract and parse date from text."""
        try:
            # Common date formats on Realtor.com
            date_patterns = [
                r'(\d{1,2}/\d{1,2}/\d{4})',
                r'(\d{4}-\d{2}-\d{2})',
                r'([A-Za-z]+ \d{1,2}, \d{4})'
            ]

            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    date_str = match.group(1)
                    try:
                        return datetime.strptime(date_str, '%Y-%m-%d')
                    except ValueError:
                        try:
                            return datetime.strptime(date_str, '%m/%d/%Y')
                        except ValueError:
                            return datetime.strptime(date_str, '%B %d, %Y')
            return None
        except Exception:
            return None
