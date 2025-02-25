"""
Base extractor module providing a robust foundation for all platform-specific extractors.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional, List, Union
from bs4 import BeautifulSoup
import logging
import random
import time
import traceback
from datetime import datetime
import re

from ..models.base import PropertyListing
from ..utils.location_service import LocationService, TextProcessingService
from ..utils.dates import extract_listing_date, parse_date_string, is_recent_listing

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Custom exception for extraction errors with enhanced tracking."""

    def __init__(self,
                 message: str,
                 extractor: Optional[str] = None,
                 raw_data: Optional[Dict[str, Any]] = None,
                 original_exception: Optional[Exception] = None,
                 stacktrace: Optional[str] = None):
        super().__init__(message)
        self.extractor = extractor
        self.raw_data = raw_data or {}
        self.timestamp = datetime.now()
        self.original_exception = original_exception
        self.stacktrace = stacktrace or (
            traceback.format_exc() if original_exception else None
        )


class BaseExtractor(ABC):
    """
    Enhanced base extractor with robust extraction strategies
    and comprehensive error handling.
    
    This class provides a framework for extracting property listing data 
    from various platforms. It includes comprehensive error handling, 
    robust fallback mechanisms, and standardized data processing.
    """

    def __init__(self, url: str):
        """
        Initialize the base extractor.
        
        Args:
            url (str): The URL of the listing
        """
        self.url = url
        self.soup = None
        self.raw_data: Dict[str, Any] = {
            "extraction_source": self.platform_name,
            "url": url,
            "extraction_timestamp": datetime.now().isoformat()
        }

        # Initialize default data structure aligned with Notion database schema
        self.data: Dict[str, Any] = {
            "url": url,
            "platform": self.platform_name,
            "listing_name": "Untitled Listing",
            "location": "Location Unknown",
            "price": "Contact for Price",
            "price_bucket": "N/A",
            "property_type": "Unknown",
            "acreage": "Not specified",
            "acreage_bucket": "Unknown",
            "last_updated": datetime.now()
        }

        # Initialize service objects
        self.location_service = LocationService()
        self.text_processor = TextProcessingService()

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the name of the platform this extractor handles."""
        pass

    def extract_with_fallbacks(self,
                               extraction_methods: List[callable],
                               default_value: Any = "Not specified") -> Any:
        """
        Attempt multiple extraction methods with fallbacks.
        
        Args:
            extraction_methods (list): List of methods to try in order
            default_value (Any): Value to return if all methods fail
        
        Returns:
            Extracted data or default value
        """
        for method in extraction_methods:
            try:
                result = method()
                if result and result != default_value:
                    return result
            except Exception as e:
                logger.debug(
                    f"Extraction method failed: {method.__name__ if hasattr(method, '__name__') else 'anonymous'}, "
                    f"Error: {str(e)}"
                )

        return default_value

    def _verify_page_content(self) -> bool:
        """
        Verify the page content is valid and contains expected elements.
        
        Returns:
            bool: Whether the page content is considered valid
        """
        try:
            # Check for minimal valid content
            if not self.soup or len(self.soup.get_text()) < 100:
                logger.warning("Insufficient page content")
                return False

            # Check for blocking indicators
            blocking_indicators = [
                "captcha",
                "security check",
                "please verify",
                "access denied",
                "pardon our interruption"
            ]
            page_text = self.soup.get_text().lower()
            if any(indicator in page_text for indicator in blocking_indicators):
                logger.warning("Potential blocking content detected")
                return False

            return True
        except Exception as e:
            logger.error(f"Page content verification failed: {str(e)}")
            return False

    def _process_location(self, raw_location: str) -> Dict[str, Any]:
        """
        Process and enrich location information.
        
        Args:
            raw_location (str): Raw location string
        
        Returns:
            Dict with parsed and enriched location data
        """
        try:
            # Skip processing for unknown locations
            if not raw_location or raw_location.lower() == 'location unknown':
                return {"raw": raw_location, "is_valid": False}

            # Parse location
            location_info = self.location_service.get_comprehensive_location_info(
                raw_location)

            # Add raw location to the result
            location_info["raw"] = raw_location

            # Mark as valid if we have some basic information
            location_info["is_valid"] = bool(location_info.get("nearest_city") or
                                             location_info.get("state"))

            return location_info

        except Exception as e:
            logger.error(f"Location processing error: {str(e)}")
            return {"raw": raw_location, "is_valid": False}

    def extract(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Main extraction method with comprehensive error handling.

        Args:
            soup (BeautifulSoup): Parsed HTML content

        Returns:
            Dict with extracted listing data
        """
        logger.info(f"Starting extraction for {self.platform_name}")

        try:
            # Assign soup and set initial raw data
            self.soup = soup
            self.raw_data['html_length'] = len(str(soup))

            # Verify page content
            if not self._verify_page_content():
                logger.warning("Page content verification failed")
                self.raw_data['extraction_status'] = 'partial'

            # Add random delay to mimic human behavior
            time.sleep(random.uniform(0.5, 2.0))

            # Core data extraction with fallbacks
            core_fields = [
                {
                    'field': 'listing_name',
                    'methods': [
                        self.extract_listing_name,
                        lambda: f"Listing from {self.platform_name}",
                        lambda: f"Untitled {self.platform_name} Listing"
                    ]
                },
                {
                    'field': 'location',
                    'methods': [
                        self.extract_location,
                        lambda: f"Location Unknown"
                    ]
                },
                {
                    'field': 'price',
                    'methods': [
                        self.extract_price
                    ]
                },
                {
                    'field': 'acreage',
                    'methods': [
                        self.extract_acreage_info
                    ]
                },
                {
                    'field': 'listing_date',
                    'methods': [
                        lambda: extract_listing_date(
                            self.soup, self.platform_name)
                    ]
                }
            ]

            # Execute core extraction
            for field_config in core_fields:
                field = field_config['field']
                extracted_value = self.extract_with_fallbacks(
                    field_config['methods'],
                    default_value=self.data.get(field)
                )

                # Special handling for tuple values (price and acreage)
                if field in ['price', 'acreage'] and isinstance(extracted_value, tuple):
                    self.data[field] = extracted_value[0]
                    self.data[f'{field}_bucket'] = extracted_value[1]
                else:
                    self.data[field] = extracted_value

            # Process location with additional enrichment
            if self.data.get('location') and self.data.get('location') != "Location Unknown":
                location_data = self._process_location(self.data['location'])

                # Map location data to Notion schema fields
                location_mapping = {
                    'distance_to_portland': 'distance_to_portland',
                    'portland_distance_bucket': 'portland_distance_bucket',
                    'nearest_city': 'nearest_city',
                    'nearest_city_distance': 'nearest_city_distance',
                    'nearest_city_distance_bucket': 'nearest_city_distance_bucket',
                    'nearest_large_city': 'nearest_large_city',
                    'nearest_large_city_distance': 'nearest_large_city_distance',
                    'nearest_large_city_distance_bucket': 'nearest_large_city_distance_bucket',
                    'town_population': 'town_population',
                    'town_pop_bucket': 'town_pop_bucket',
                    'school_district': 'school_district',
                    'school_rating': 'school_rating',
                    'school_rating_cat': 'school_rating_cat',
                    'hospital_distance': 'hospital_distance',
                    'hospital_distance_bucket': 'hospital_distance_bucket',
                    'closest_hospital': 'closest_hospital',
                    'other_amenities': 'other_amenities'
                }

                # Transfer valid location data to main data structure
                for source_field, target_field in location_mapping.items():
                    if source_field in location_data and location_data[source_field]:
                        self.data[target_field] = location_data[source_field]

            # Determine property type from listing name and description
            property_text = f"{self.data.get('listing_name', '')} {self.data.get('notes', '')}"
            self.data['property_type'] = self.text_processor.extract_property_type(
                property_text)

            # Extract additional details
            self.extract_additional_data()

            # Final validation using PropertyListing model
            try:
                # Prepare data for validation
                validation_data = self.data.copy()

                # Convert raw date strings to datetime objects if needed
                if isinstance(validation_data.get('listing_date'), str):
                    try:
                        validation_data['listing_date'] = datetime.strptime(
                            validation_data['listing_date'], '%Y-%m-%d'
                        )
                    except (ValueError, TypeError):
                        validation_data.pop('listing_date', None)

                # Create PropertyListing instance for validation
                validated_data = PropertyListing(**validation_data)
                self.data = validated_data.dict()

                # Mark extraction as successful
                self.raw_data['extraction_status'] = 'success'

            except Exception as validation_error:
                logger.error(f"Data validation failed: {validation_error}")
                # We'll continue with unvalidated data but flag it
                self.raw_data['validation_error'] = str(validation_error)
                self.raw_data['extraction_status'] = 'partial'

            return self.data

        except Exception as e:
            # Comprehensive error handling
            stacktrace = traceback.format_exc()
            extraction_error = ExtractionError(
                message=f"Extraction failed for {self.platform_name}",
                extractor=self.platform_name,
                raw_data=self.raw_data,
                original_exception=e,
                stacktrace=stacktrace
            )

            # Log the detailed error
            logger.error(
                f"Extraction Error: {extraction_error}\n"
                f"URL: {self.url}\n"
                f"Original Exception: {str(e)}\n"
                f"Stacktrace: {stacktrace}"
            )

            # Return partial data with error indicators
            self.data.update({
                'extraction_error': str(e),
                'extraction_status': 'failed'
            })

            return self.data

    @abstractmethod
    def extract_listing_name(self) -> str:
        """Extract the listing name/title."""
        pass

    @abstractmethod
    def extract_location(self) -> str:
        """Extract the property location."""
        pass

    @abstractmethod
    def extract_price(self) -> Tuple[str, str]:
        """
        Extract price and price bucket.
        
        Returns:
            Tuple of (formatted price, price bucket)
        """
        pass

    @abstractmethod
    def extract_acreage_info(self) -> Tuple[str, str]:
        """
        Extract acreage and acreage bucket.
        
        Returns:
            Tuple of (formatted acreage, acreage bucket)
        """
        pass

    def extract_additional_data(self):
        """
        Extract additional property details.
        Can be overridden by platform-specific extractors.
        """
        try:
            # Common additional data extraction methods
            # House details
            house_details = self._extract_house_details()
            if house_details:
                self.data['house_details'] = house_details

            # Farm details
            farm_details = self._extract_farm_details()
            if farm_details:
                self.data['farm_details'] = farm_details

            # Notes or description
            description = self._extract_description()
            if description:
                self.data['notes'] = description

            # Try to extract restaurants and grocery stores nearby
            restaurants = self._extract_restaurants_nearby()
            if restaurants is not None:
                self.data['restaurants_nearby'] = restaurants

            grocery_stores = self._extract_grocery_stores_nearby()
            if grocery_stores is not None:
                self.data['grocery_stores_nearby'] = grocery_stores

        except Exception as e:
            logger.error(f"Error in additional data extraction: {str(e)}")
            self.raw_data['additional_data_extraction_error'] = str(e)

    def _extract_house_details(self) -> Optional[str]:
        """
        Extract house-specific details.
        To be potentially overridden by specific extractors.
        
        Returns:
            Optional string of house details
        """
        # Look for common house detail patterns
        house_detail_patterns = [
            r'(\d+)\s*bedrooms?',
            r'(\d+)\s*bathrooms?',
            r'(\d+)\s*sq\s*ft',
            r'(\d+)\s*square\s*feet',
        ]

        details = []
        page_text = self.soup.get_text()

        for pattern in house_detail_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                details.append(match.group(0))

        if details:
            return " | ".join(details)

        return None

    def _extract_farm_details(self) -> Optional[str]:
        """
        Extract farm-specific details.
        To be potentially overridden by specific extractors.
        
        Returns:
            Optional string of farm details
        """
        # Look for common farm detail patterns
        farm_detail_patterns = [
            r'(\d+)\s*acres? tillable',
            r'(\d+)\s*acres? pasture',
            r'(\d+)\s*acres? woodland',
            r'barn',
            r'stable',
            r'silo',
            r'farmhouse',
            r'irrigation',
            r'fencing',
            r'grazing',
            r'livestock',
            r'organic',
            r'certified'
        ]

        details = []
        page_text = self.soup.get_text().lower()

        for pattern in farm_detail_patterns:
            if re.search(pattern, page_text, re.I):
                # Extract the full context
                context_match = re.search(
                    r'[^.!?]*' + pattern + r'[^.!?]*', page_text, re.I)
                if context_match:
                    details.append(self.text_processor.clean_html_text(
                        context_match.group(0)))

        if details:
            # Limit to 3 details for conciseness
            return " | ".join(details[:3])

        return None

    def _extract_description(self) -> Optional[str]:
        """
        Extract property description.
        To be potentially overridden by specific extractors.
        
        Returns:
            Optional string of description
        """
        # Common description selectors
        description_selectors = [
            {'class_': 'property-description'},
            {'class_': 'description'},
            {'class_': 'listing-description'},
            {'class_': 'details'},
            {'id': 'property-description'},
            {'id': 'description'}
        ]

        # Try each selector
        for selector in description_selectors:
            description_elem = self.soup.find(attrs=selector)
            if description_elem:
                description_text = self.text_processor.clean_html_text(
                    description_elem.get_text())
                # Minimum meaningful length
                if description_text and len(description_text) > 20:
                    return description_text

        return None

    def _extract_restaurants_nearby(self) -> Optional[int]:
        """
        Extract number of restaurants nearby.
        To be potentially overridden by specific extractors.
        
        Returns:
            Optional integer count of restaurants
        """
        # This is often provided through location enrichment
        # Default implementation returns None
        return None

    def _extract_grocery_stores_nearby(self) -> Optional[int]:
        """
        Extract number of grocery stores nearby.
        To be potentially overridden by specific extractors.
        
        Returns:
            Optional integer count of grocery stores
        """
        # This is often provided through location enrichment
        # Default implementation returns None
        return None
