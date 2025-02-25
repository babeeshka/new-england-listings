"""
Unified location service for New England Listings.
This module consolidates functionality from location_parsing, location_processing,
location_analysis, and geocoding modules into a cohesive service.
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple, List, Union
from urllib.parse import urlparse
from datetime import datetime
from functools import lru_cache
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut

from .caching_utils import persistent_cache
from ..config.constants import (
    MAJOR_CITIES,
    DISTANCE_BUCKETS,
    SCHOOL_RATING_BUCKETS,
    POPULATION_BUCKETS,
    ACREAGE_BUCKETS,
    PRICE_BUCKETS
)

logger = logging.getLogger(__name__)


class LocationService:
    """
    Unified service for location data processing, including:
    - Location parsing
    - Geocoding
    - Distance calculations
    - Location enrichment
    """

    def __init__(self, cache_ttl: int = 86400, cache_size: int = 1000):
        """
        Initialize the location service.
        
        Args:
            cache_ttl: Time-to-live for cache entries (in seconds)
            cache_size: Maximum size of the cache
        """
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        self.geolocator = Nominatim(
            user_agent="new_england_listings",
            timeout=10
        )

    def parse_location(self, location_str: str) -> Dict[str, Any]:
        """
        Comprehensive location parsing with multiple strategies.
        
        Args:
            location_str: Raw location string
            
        Returns:
            Dictionary with parsed location data
        """
        # Create location parsing object
        location_data = {
            'original': location_str,
            'parsed_components': {},
            'standardized_name': None,
            'state': None,
            'country': 'United States',
            'is_valid': False
        }

        if not location_str or location_str.lower() == 'location unknown':
            return location_data

        # Define parsing strategies
        parsing_strategies = [
            # Strategy 1: Standard "City, State" format
            lambda loc: re.match(r'^([\w\s]+),\s*([A-Z]{2})$', loc),

            # Strategy 2: Standard "City, State ZIP" format
            lambda loc: re.match(r'^([\w\s]+),\s*([A-Z]{2})\s+(\d{5})$', loc),

            # Strategy 3: "Street Address City, State" format
            lambda loc: re.match(
                r'^.+\s([\w\s]+),\s*([A-Z]{2})(?:\s+\d{5})?$', loc),

            # Strategy 4: County-based parsing
            lambda loc: re.match(r'^([\w\s]+)\s+County,\s*([A-Z]{2})$', loc),

            # Strategy 5: City with implied state (New England states)
            lambda loc: next((
                (loc, state)
                for state in ['ME', 'NH', 'VT', 'MA', 'CT', 'RI']
                if state in loc.upper()
            ), None)
        ]

        # Apply parsing strategies
        for strategy in parsing_strategies:
            match = strategy(location_str)
            if match:
                # Unpack results based on strategy
                if isinstance(match, tuple):
                    city, state = match
                    zip_code = None
                elif len(match.groups()) == 3:  # With ZIP
                    city, state, zip_code = match.groups()
                else:  # Without ZIP
                    city, state = match.groups()
                    zip_code = None

                location_data.update({
                    'parsed_components': {
                        'city': city.strip().title(),
                        'state': state.strip().upper(),
                        'zip_code': zip_code.strip() if zip_code else None
                    },
                    'standardized_name': f"{city.strip().title()}, {state.strip().upper()}",
                    'state': state.strip().upper(),
                    'is_valid': True
                })
                break

        # Clean up and extract county if present
        if 'County' in location_str:
            county_match = re.search(r'(\w+)\s+County', location_str)
            if county_match:
                location_data['parsed_components']['county'] = county_match.group(
                    1).title()

        return location_data

    def parse_location_from_url(self, url: str) -> Optional[str]:
        """
        Extract location information from URL path with enhanced parsing.
        
        Args:
            url: URL to parse
            
        Returns:
            Parsed location string or None
        """
        try:
            path = urlparse(url).path
            parts = path.split('/')[-1].split('-')

            # Enhanced state and location detection
            state_identifiers = ['ME', 'VT', 'NH', 'MA', 'CT', 'RI']

            # Find state index
            state_index = next(
                (i for i, part in enumerate(parts)
                 if part.upper() in state_identifiers),
                None
            )

            if state_index is not None:
                # Intelligent city and state extraction
                property_type_keywords = [
                    'cape', 'farm', 'land', 'house', 'property']

                # Find start of location
                start_index = next(
                    (i for i in range(state_index)
                     if parts[i] not in property_type_keywords),
                    0
                )

                # Extract city parts
                city_parts = parts[start_index:state_index]
                city = ' '.join(word.title() for word in city_parts)
                state = parts[state_index].upper()

                # Optional ZIP code handling
                zip_code = (
                    parts[state_index + 1]
                    if state_index + 1 < len(parts) and parts[state_index + 1].isdigit()
                    else None
                )

                # Construct location string
                location = f"{city}, {state}"
                if zip_code:
                    location += f" {zip_code}"

                return location

        except Exception as e:
            logger.error(f"Error parsing location from URL: {str(e)}")

        return None

    @persistent_cache(max_size=1000, ttl=86400, disk_persistence=True)
    def get_location_coordinates(self, location: str) -> Optional[Tuple[float, float]]:
        """
        Get coordinates for a location using geocoding.
        
        Args:
            location: Location string to geocode
            
        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        if not location or location == "Location Unknown":
            return None

        logger.debug(f"Geocoding location: {location}")

        try:
            # Check if this is a county location
            county_match = re.match(r'(\w+)\s+County,\s*(\w{2})', location)
            if county_match:
                county, state = county_match.groups()
                coords = self._get_county_coordinates(county, state)
                if coords:
                    return coords

            # Clean up the location string
            location = re.sub(r'\s+', ' ', location).strip()

            # If we already have a state code, try that first
            if re.search(r',\s*[A-Z]{2}\b', location):
                try:
                    geocode_result = self.geolocator.geocode(
                        location,
                        exactly_one=True,
                        country_codes=["us"]
                    )
                    if geocode_result:
                        coords = (geocode_result.latitude,
                                  geocode_result.longitude)
                        logger.debug(f"Found coordinates: {coords}")
                        return coords
                except GeocoderTimedOut:
                    logger.warning(f"Timeout for location: {location}")

            # Try with different state contexts
            states = ["ME", "NH", "VT", "MA", "CT", "RI"]
            base_location = re.sub(r',\s*[A-Z]{2}.*$', '', location)

            for state in states:
                try:
                    location_with_state = f"{base_location}, {state}"
                    geocode_result = self.geolocator.geocode(
                        location_with_state,
                        exactly_one=True,
                        country_codes=["us"]
                    )
                    if geocode_result:
                        coords = (geocode_result.latitude,
                                  geocode_result.longitude)
                        logger.debug(
                            f"Found coordinates with state {state}: {coords}")
                        return coords
                except GeocoderTimedOut:
                    logger.warning(
                        f"Timeout for location with state: {location_with_state}")
                    continue

        except Exception as e:
            logger.error(f"Error geocoding location {location}: {str(e)}")

        return None

    def _get_county_coordinates(self, county: str, state: str = "ME") -> Optional[Tuple[float, float]]:
        """Get coordinates for a county center."""
        try:
            # Try different query formats
            queries = [
                f"{county} County, {state}, USA",
                f"{county} County, {state}",
                f"{county}, {state}, United States"
            ]

            for query in queries:
                try:
                    logger.debug(
                        f"Trying to geocode county with query: {query}")
                    geocode_result = self.geolocator.geocode(
                        query,
                        exactly_one=True,
                        country_codes=["us"],
                        featuretype=["county", "administrative"]
                    )
                    if geocode_result:
                        coords = (geocode_result.latitude,
                                  geocode_result.longitude)
                        logger.debug(f"Found county coordinates: {coords}")
                        return coords
                except GeocoderTimedOut:
                    logger.warning(f"Timeout for query: {query}")
                    continue

        except Exception as e:
            logger.error(f"Error geocoding county {county}, {state}: {str(e)}")

        return None

    def get_distance(self, point1: Union[Tuple[float, float], str],
                     point2: Union[Tuple[float, float], str]) -> float:
        """
        Calculate distance between two points.
        Points can be either coordinates (lat, lon) or location strings.

        Args:
            point1: First point (coordinates or location string)
            point2: Second point (coordinates or location string)

        Returns:
            Distance in miles
        """
        logger.debug(f"Calculating distance between {point1} and {point2}")

        try:
            # Convert string locations to coordinates if necessary
            if isinstance(point1, str):
                point1_coords = self.get_location_coordinates(point1)
                if not point1_coords:
                    raise ValueError(f"Could not geocode location: {point1}")
                point1 = point1_coords

            if isinstance(point2, str):
                point2_coords = self.get_location_coordinates(point2)
                if not point2_coords:
                    raise ValueError(f"Could not geocode location: {point2}")
                point2 = point2_coords

            # Calculate distance
            distance = geodesic(point1, point2).miles
            logger.debug(f"Calculated distance: {distance:.1f} miles")
            return distance

        except Exception as e:
            logger.error(f"Error calculating distance: {str(e)}")
            return 0.0

    def get_bucket(self, value: float, buckets: Dict[int, str], default_strategy: str = 'last') -> str:
        """
        Get the appropriate bucket for a numeric value with flexible default handling.

        Args:
            value: Numeric value to categorize
            buckets: Dictionary mapping thresholds to bucket names
            default_strategy: How to handle values outside defined buckets
                'first': Return the first bucket
                'last': Return the last bucket (default)
                'none': Return None if no bucket found

        Returns:
            Bucket name or None based on default_strategy
        """
        try:
            # Sort buckets by thresholds in ascending order
            sorted_buckets = sorted(buckets.items(), key=lambda x: x[0])

            # Find appropriate bucket
            for threshold, bucket in sorted_buckets:
                if value <= threshold:
                    return bucket

            # Handle default strategies for values exceeding all thresholds
            if default_strategy == 'first':
                return sorted_buckets[0][1]  # First bucket
            elif default_strategy == 'last':
                return sorted_buckets[-1][1]  # Last bucket
            else:
                return None  # No bucket found

        except Exception as e:
            logger.error(f"Error determining bucket: {str(e)}")

            # Fallback to first bucket in case of any error
            return list(buckets.values())[0] if buckets else None

    def find_nearest_cities(self, coordinates: Optional[Tuple[float, float]],
                            limit: int = 3) -> List[Dict[str, Any]]:
        """
        Find the nearest major cities and their distances.
        
        Args:
            coordinates: Location coordinates (latitude, longitude)
            limit: Maximum number of cities to return
            
        Returns:
            List of dictionaries with city information
        """
        if not coordinates:
            return []

        try:
            distances = []
            for city_name, city_info in MAJOR_CITIES.items():
                city_coords = city_info["coordinates"]
                distance = self.get_distance(coordinates, city_coords)
                distances.append({
                    "city": city_name,
                    "distance": round(distance, 1),
                    "distance_bucket": self.get_bucket(distance, DISTANCE_BUCKETS)
                })

            # Sort by distance and return top N
            return sorted(distances, key=lambda x: x["distance"])[:limit]

        except Exception as e:
            logger.error(f"Error finding nearest cities: {str(e)}")
            return []

    def get_comprehensive_location_info(self, location: str) -> Dict[str, Any]:
        """
        Get comprehensive location information including coordinates, 
        nearby cities, and distance metrics based on the property's actual location.
        
        Args:
            location: Location string
            
        Returns:
            Dictionary with enriched location information
        """
        result = {}

        try:
            # Parse location
            parsed_location = self.parse_location(location)

            # Add basic state info right away (ensure it's always present)
            if parsed_location.get('state'):
                result['state'] = parsed_location['state']

                # Add state-specific context
                state_full_names = {
                    'ME': 'Maine',
                    'NH': 'New Hampshire',
                    'VT': 'Vermont',
                    'MA': 'Massachusetts',
                    'CT': 'Connecticut',
                    'RI': 'Rhode Island'
                }

                result['state_full'] = state_full_names.get(
                    parsed_location['state'], parsed_location['state'])

            # Get coordinates
            coordinates = None
            if parsed_location.get('is_valid'):
                coordinates = self.get_location_coordinates(
                    parsed_location.get('standardized_name') or location
                )
            else:
                coordinates = self.get_location_coordinates(location)

            if coordinates:
                result.update({
                    'latitude': coordinates[0],
                    'longitude': coordinates[1]
                })

                # Find nearest cities
                nearest_cities = self.find_nearest_cities(
                    coordinates, limit=5)  # Increased limit

                if nearest_cities:
                    # Add nearest city info
                    nearest_city = nearest_cities[0]
                    result.update({
                        'nearest_city': nearest_city['city'],
                        'nearest_city_distance': nearest_city['distance'],
                        'nearest_city_distance_bucket': nearest_city['distance_bucket']
                    })

                    # Get property's state
                    property_state = parsed_location.get('state', '')
                    if not property_state and parsed_location.get('parsed_components', {}).get('state'):
                        property_state = parsed_location.get(
                            'parsed_components', {}).get('state')

                    # Find most relevant cities for this property
                    # First, prioritize cities in the same state
                    same_state_cities = [
                        city for city in nearest_cities
                        if property_state and city['city'].endswith(f", {property_state}")
                    ]

                    # Then find the largest city within a reasonable distance (50 miles)
                    nearby_cities = [
                        city for city in nearest_cities if city['distance'] <= 50]
                    largest_cities = sorted(
                        nearby_cities,
                        key=lambda x: MAJOR_CITIES.get(
                            x['city'], {}).get('population', 0),
                        reverse=True
                    )

                    if largest_cities:
                        largest_city = largest_cities[0]
                        city_info = MAJOR_CITIES.get(largest_city['city'], {})

                        result.update({
                            'nearest_large_city': largest_city['city'],
                            'nearest_large_city_distance': largest_city['distance'],
                            'nearest_large_city_distance_bucket': largest_city['distance_bucket'],
                            'major_city_population': city_info.get('population'),
                            'town_population': city_info.get('population'),
                            'town_pop_bucket': self.get_bucket(
                                city_info.get('population', 0),
                                POPULATION_BUCKETS
                            )
                        })

                    # Always calculate distance to Portland for consistency
                    portland_coords = MAJOR_CITIES.get(
                        'Portland, ME', {}).get('coordinates')
                    if portland_coords:
                        distance_to_portland = self.get_distance(
                            coordinates, portland_coords)
                        result.update({
                            'distance_to_portland': round(distance_to_portland, 1),
                            'portland_distance_bucket': self.get_bucket(
                                distance_to_portland,
                                DISTANCE_BUCKETS
                            )
                        })

                    # Add enhanced amenities info with proper error handling
                    self._add_enhanced_amenities_info(
                        result, nearest_cities, property_state)

            # Ensure regional context is always included
            if 'nearest_city' in result and 'nearest_city_distance' in result and 'regional_context' not in result:
                result['regional_context'] = f"Property is {result['nearest_city_distance']:.1f} miles from {result['nearest_city']}"

            # Always ensure restaurants and grocery store values are present
            if 'restaurants_nearby' not in result or result['restaurants_nearby'] is None:
                result['restaurants_nearby'] = 1

            if 'grocery_stores_nearby' not in result or result['grocery_stores_nearby'] is None:
                result['grocery_stores_nearby'] = 1

            return result

        except Exception as e:
            logger.error(
                f"Error getting comprehensive location info: {str(e)}")
            # Fill in essential fallback values even in error case
            if 'state' not in result and parsed_location and parsed_location.get('state'):
                result['state'] = parsed_location.get('state')
            if 'restaurants_nearby' not in result:
                result['restaurants_nearby'] = 1
            if 'grocery_stores_nearby' not in result:
                result['grocery_stores_nearby'] = 1
            return result

    def _add_amenities_info(self, result: Dict[str, Any], nearest_cities: List[Dict[str, Any]]):
        """Add amenities information to the location result."""
        try:
            # Check for hospitals
            hospitals = []
            for city_data in nearest_cities:
                city = city_data['city']
                city_info = MAJOR_CITIES.get(city, {})
                if 'Hospital' in city_info.get('amenities', []):
                    hospitals.append({
                        'name': f"{city} Hospital",
                        'distance': city_data['distance'],
                        'distance_bucket': city_data['distance_bucket']
                    })

            if hospitals:
                closest_hospital = min(hospitals, key=lambda x: x['distance'])
                result.update({
                    'hospital_distance': closest_hospital['distance'],
                    'closest_hospital': closest_hospital['name'],
                    'hospital_distance_bucket': closest_hospital['distance_bucket']
                })

            # Check for schools
            schools = []
            for city_data in nearest_cities:
                city = city_data['city']
                city_info = MAJOR_CITIES.get(city, {})
                if 'school_rating' in city_info:
                    schools.append({
                        'district': city,
                        'rating': city_info['school_rating'],
                        'distance': city_data['distance']
                    })

            if schools:
                best_school = max(schools, key=lambda x: x['rating'])
                closest_school = min(schools, key=lambda x: x['distance'])
                result.update({
                    'school_district': closest_school['district'],
                    'school_rating': closest_school['rating'],
                    'school_rating_cat': self.get_bucket(
                        closest_school['rating'],
                        SCHOOL_RATING_BUCKETS
                    ),
                    'best_nearby_district': best_school['district'] if best_school != closest_school else None
                })

            # Collect amenities from nearest cities
            all_amenities = []
            for city_data in nearest_cities[:3]:  # Look at 3 closest cities
                city = city_data['city']
                city_info = MAJOR_CITIES.get(city, {})
                all_amenities.extend(city_info.get('amenities', []))

            if all_amenities:
                result['other_amenities'] = " | ".join(set(all_amenities[:7]))

        except Exception as e:
            logger.error(f"Error adding amenities info: {str(e)}")

    def _add_enhanced_amenities_info(self, result: Dict[str, Any], nearest_cities: List[Dict[str, Any]], property_state: str = None):
        """Add enhanced amenities information to the location result with more geographic context and deduplication."""
        try:
            # Filter cities to prioritize those in the same state if specified
            prioritized_cities = nearest_cities
            if property_state:
                same_state_cities = [
                    city for city in nearest_cities if city['city'].endswith(f", {property_state}")]
                if same_state_cities:
                    prioritized_cities = same_state_cities + \
                        [city for city in nearest_cities if city not in same_state_cities]

            # Check for hospitals
            hospitals = []
            for city_data in prioritized_cities:
                city = city_data['city']
                city_info = MAJOR_CITIES.get(city, {})
                if 'Hospital' in city_info.get('amenities', []):
                    hospitals.append({
                        'name': f"{city} Hospital",
                        'distance': city_data['distance'],
                        'distance_bucket': city_data['distance_bucket']
                    })

            if hospitals:
                closest_hospital = min(hospitals, key=lambda x: x['distance'])
                result.update({
                    'hospital_distance': closest_hospital['distance'],
                    'closest_hospital': closest_hospital['name'],
                    'hospital_distance_bucket': closest_hospital['distance_bucket']
                })
            else:
                # Always provide hospital data (use nearest city if no specific hospital found)
                if 'nearest_city' in result and 'nearest_city_distance' in result:
                    result['hospital_distance'] = result['nearest_city_distance']
                    result['closest_hospital'] = f"{result['nearest_city']} Medical Center"
                    result['hospital_distance_bucket'] = result['nearest_city_distance_bucket']

            # Check for schools
            schools = []
            for city_data in prioritized_cities:
                city = city_data['city']
                city_info = MAJOR_CITIES.get(city, {})
                if 'school_rating' in city_info:
                    schools.append({
                        'district': city,
                        'rating': city_info['school_rating'],
                        'distance': city_data['distance']
                    })

            if schools:
                # Find school based on distance and rating
                # Prioritize closer schools but also consider rating
                for school in sorted(schools, key=lambda x: x['distance']):
                    if school['rating'] >= 6:  # Decent or better schools
                        result.update({
                            'school_district': school['district'],
                            'school_rating': school['rating'],
                            'school_rating_cat': self.get_bucket(
                                school['rating'],
                                SCHOOL_RATING_BUCKETS
                            )
                        })
                        break

                # If no good schools were found nearby, use the closest one
                if 'school_district' not in result and schools:
                    closest_school = min(schools, key=lambda x: x['distance'])
                    result.update({
                        'school_district': closest_school['district'],
                        'school_rating': closest_school['rating'],
                        'school_rating_cat': self.get_bucket(
                            closest_school['rating'],
                            SCHOOL_RATING_BUCKETS
                        )
                    })

                # Add info about best school in the area for comparison
                best_school = max(schools, key=lambda x: x['rating'])
                if best_school['district'] != result.get('school_district'):
                    result['best_nearby_school_district'] = best_school['district']
                    result['best_nearby_school_rating'] = best_school['rating']
            else:
                # Always provide school data (use nearest city with a default rating if no specific school found)
                if 'nearest_city' in result:
                    result['school_district'] = result['nearest_city']
                    result['school_rating'] = 6.0  # Default "average" rating
                    result['school_rating_cat'] = "Average (6-7)"

            # Collect amenities from nearest cities
            all_amenities = set()  # Use a set to automatically deduplicate
            grocery_count = 0
            restaurant_count = 0

            # Check closest 3 cities for amenities
            for i, city_data in enumerate(prioritized_cities[:3]):
                city = city_data['city']
                city_info = MAJOR_CITIES.get(city, {})
                city_amenities = city_info.get('amenities', [])
                population = city_info.get('population', 0)

                # Add unique amenities to the set (automatically deduplicates)
                all_amenities.update(city_amenities)

                # More comprehensive keyword matching for restaurants
                restaurant_keywords = ['restaurant', 'dining',
                                       'cafe', 'food', 'eatery', 'bistro', 'pub']
                for amenity in city_amenities:
                    if any(keyword in amenity.lower() for keyword in restaurant_keywords):
                        restaurant_count += 1
                        break

                # If no explicit restaurant mentions, estimate based on city size
                if restaurant_count == 0:
                    # Base estimate on population (larger cities have more restaurants)
                    if population > 50000:
                        restaurant_count += 5
                    elif population > 25000:
                        restaurant_count += 3
                    elif population > 10000:
                        restaurant_count += 2
                    elif population > 5000:
                        restaurant_count += 1

                # More comprehensive keyword matching for grocery stores
                grocery_keywords = ['grocery', 'market',
                                    'shopping', 'supermarket', 'store', 'mall']
                for amenity in city_amenities:
                    if any(keyword in amenity.lower() for keyword in grocery_keywords):
                        grocery_count += 1
                        break

                # If no explicit grocery mentions, estimate based on city size
                if grocery_count == 0:
                    # Base estimate on population (larger cities have more grocery stores)
                    if population > 50000:
                        grocery_count += 3
                    elif population > 25000:
                        grocery_count += 2
                    elif population > 5000:
                        grocery_count += 1

            # Always provide non-null values for restaurant and grocery counts
            # Even if detection failed, use city population as a fallback
            if restaurant_count == 0 and prioritized_cities:
                closest_city = prioritized_cities[0]
                city_info = MAJOR_CITIES.get(closest_city['city'], {})
                population = city_info.get('population', 0)

                if population > 50000:
                    restaurant_count = 5
                elif population > 25000:
                    restaurant_count = 3
                elif population > 10000:
                    restaurant_count = 2
                else:
                    restaurant_count = 1

            if grocery_count == 0 and prioritized_cities:
                closest_city = prioritized_cities[0]
                city_info = MAJOR_CITIES.get(closest_city['city'], {})
                population = city_info.get('population', 0)

                if population > 50000:
                    grocery_count = 3
                elif population > 25000:
                    grocery_count = 2
                else:
                    grocery_count = 1

            # Add counts to result (always non-null)
            result['restaurants_nearby'] = restaurant_count
            result['grocery_stores_nearby'] = grocery_count

            # Create a list of all unique amenities (already deduplicated by using a set)
            if all_amenities:
                # Convert set to list and limit to 7 amenities
                unique_amenities = list(all_amenities)
                result['other_amenities'] = " | ".join(unique_amenities[:7])

                # Add regional context
                if prioritized_cities and 'regional_context' not in result:
                    closest_city = prioritized_cities[0]
                    result['regional_context'] = f"Property is {closest_city['distance']:.1f} miles from {closest_city['city']}"

        except Exception as e:
            logger.error(f"Error adding enhanced amenities info: {str(e)}")
            # Even if an error occurs, provide default values
            if 'restaurants_nearby' not in result:
                result['restaurants_nearby'] = 1
            if 'grocery_stores_nearby' not in result:
                result['grocery_stores_nearby'] = 1

            # Provide basic regional context if missing
            if 'regional_context' not in result and 'nearest_city' in result:
                result['regional_context'] = f"Property near {result['nearest_city']}"

# Text processing utilities for property listings
class TextProcessingService:
    """Utilities for processing and standardizing text in property listings."""

    @staticmethod
    def standardize_price(price_text: str) -> Tuple[str, str]:
        """
        Standardize price processing with robust parsing.
        
        Args:
            price_text: Raw price text
            
        Returns:
            Tuple of (formatted price, price bucket)
        """
        if not price_text or isinstance(price_text, str) and 'contact' in price_text.lower():
            return "Contact for Price", "N/A"

        try:
            # Remove non-numeric characters except decimal point
            numeric_text = re.sub(r'[^\d.]', '', price_text)

            if not numeric_text:
                return "Contact for Price", "N/A"

            # Convert to float
            price_value = float(numeric_text)

            # Determine price bucket
            price_bucket = next(
                (bucket for threshold, bucket in sorted(PRICE_BUCKETS.items())
                 if price_value < threshold),
                list(PRICE_BUCKETS.values())[-1]
            )

            # Format price
            if price_value >= 1_000_000:
                formatted_price = f"${price_value/1_000_000:.1f}M"
            else:
                formatted_price = f"${price_value:,.0f}"

            return formatted_price, price_bucket

        except (ValueError, TypeError) as e:
            logger.warning(f"Error processing price '{price_text}': {e}")
            return "Contact for Price", "N/A"

    @staticmethod
    def standardize_acreage(acreage_text: str) -> Tuple[str, str]:
        """
        Standardize acreage processing with multiple parsing strategies.
        
        Args:
            acreage_text: Raw acreage text
            
        Returns:
            Tuple of (formatted acreage, acreage bucket)
        """
        if not acreage_text:
            return "Not specified", "Unknown"

        try:
            # Comprehensive acreage extraction patterns
            acreage_patterns = [
                r'(\d+(?:\.\d+)?)\s*acres?',
                r'approximately\s*(\d+(?:\.\d+)?)\s*acres?',
                r'about\s*(\d+(?:\.\d+)?)\s*acres?',
                r'(\d+(?:\.\d+)?)\s*acre\s*(?:lot|parcel)'
            ]

            for pattern in acreage_patterns:
                match = re.search(pattern, acreage_text.lower())
                if match:
                    # Clean and convert to float
                    acres_str = match.group(1).replace(',', '')
                    acres = float(acres_str)

                    # Determine acreage bucket
                    acreage_bucket = next(
                        (bucket for threshold, bucket in sorted(ACREAGE_BUCKETS.items())
                         if acres < threshold),
                        list(ACREAGE_BUCKETS.values())[-1]
                    )

                    # Format with one decimal place
                    formatted_acres = f"{acres:.1f} acres"
                    return formatted_acres, acreage_bucket

            # If no match found
            return "Not specified", "Unknown"

        except (ValueError, TypeError) as e:
            logger.warning(f"Error processing acreage '{acreage_text}': {e}")
            return "Not specified", "Unknown"

    @staticmethod
    def extract_property_type(text: str) -> str:
        """
        Enhanced property type extraction with more patterns.
        
        Args:
            text: Description text
            
        Returns:
            Standardized property type
        """
        # Expand property type detection patterns
        type_patterns = {
            'Single Family': [
                r'single[\s-]?family',
                r'residential\s*home?',
                r'\d+\s*bed',
                r'single[\s-]?story',
                r'residential\s*property'
            ],
            'Multi Family': [
                r'multi[\s-]?family',
                r'duplex',
                r'triplex',
                r'fourplex',
                r'apartment\s*building'
            ],
            'Farm': [
                r'farm',
                r'ranch',
                r'agricultural',
                r'farmland',
                r'pasture',
                r'crop\s*land'
            ],
            'Land': [
                r'undeveloped\s*land',
                r'vacant\s*lot',
                r'land\s*parcel',
                r'empty\s*lot',
                r'raw\s*land'
            ],
            'Commercial': [
                r'commercial',
                r'business',
                r'retail',
                r'office',
                r'industrial',
                r'investment\s*property'
            ]
        }

        # Normalize text
        text_lower = text.lower()

        # Check each property type
        for prop_type, patterns in type_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return prop_type

        return "Unknown"

    @staticmethod
    def clean_html_text(text: str) -> str:
        """
        Enhanced HTML text cleaning.
        
        Args:
            text: Raw HTML text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text).strip()

        # Remove HTML artifacts and special characters
        text = text.replace('&nbsp;', ' ') \
            .replace('&amp;', '&') \
            .replace('&quot;', '"') \
            .replace('&#39;', "'") \
            .replace('&lt;', '<') \
            .replace('&gt;', '>')

        # Remove non-printable characters
        text = ''.join(char for char in text if char.isprintable())

        return text.strip()
