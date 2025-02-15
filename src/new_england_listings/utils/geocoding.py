# src/new_england_listings/utils/geocoding.py
from functools import lru_cache
from typing import Optional, Tuple, Dict, List, Any, Union
from urllib.parse import urlparse
import re
import logging
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut
from ..config.constants import MAJOR_CITIES, DISTANCE_BUCKETS

logger = logging.getLogger(__name__)


def get_distance(point1: Union[Tuple[float, float], str], point2: Union[Tuple[float, float], str]) -> float:
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
            point1_coords = get_location_coordinates(point1)
            if not point1_coords:
                raise ValueError(f"Could not geocode location: {point1}")
            point1 = point1_coords

        if isinstance(point2, str):
            point2_coords = get_location_coordinates(point2)
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


def get_bucket(value: float, buckets: Dict[int, str]) -> str:
    """
    Get the appropriate bucket for a numeric value.
    
    Args:
        value: Numeric value to categorize
        buckets: Dictionary mapping thresholds to bucket names
        
    Returns:
        Bucket name
    """
    try:
        for threshold, bucket in sorted(buckets.items()):
            if value <= threshold:
                return bucket
        return list(buckets.values())[-1]
    except Exception as e:
        logger.error(f"Error determining bucket: {str(e)}")
        return list(buckets.values())[0]  # Return first bucket as default


def parse_location_from_url(url: str) -> Optional[str]:
    """Extract location information from URL path."""
    try:
        path = urlparse(url).path
        # For URL pattern like "single-family-residence-cape-windham-me-36400823"
        parts = path.split('/')[-1].split('-')

        # Look for state identifier
        state_index = None
        for i, part in enumerate(parts):
            if part.upper() in ['ME', 'VT', 'NH', 'MA', 'CT', 'RI']:
                state_index = i
                break

        if state_index is not None:
            # Get city parts (everything between property type and state)
            property_type_end = next((i for i, part in enumerate(parts)
                                      if part in ['cape', 'farm', 'land']), 0)
            city_parts = parts[property_type_end + 1:state_index]
            city = ' '.join(word.title() for word in city_parts)
            state = parts[state_index].upper()

            # Include ZIP if available
            zip_code = None
            if state_index + 1 < len(parts) and parts[state_index + 1].isdigit():
                zip_code = parts[state_index + 1]

            location = f"{city}, {state}"
            if zip_code:
                location += f" {zip_code}"

            return location

    except Exception as e:
        logger.error(f"Error parsing location from URL: {str(e)}")

    return None


@lru_cache(maxsize=1000)
def get_location_coordinates(location: str) -> Optional[Tuple[float, float]]:
    """Get coordinates for a location using geocoding."""
    if not location or location == "Location Unknown":
        return None

    geolocator = Nominatim(user_agent="new_england_listings")
    logger.debug(f"Geocoding location: {location}")

    try:
        # Clean up the location string
        location = re.sub(r'\s+', ' ', location).strip()

        # If we already have a state code, try that first
        if re.search(r',\s*[A-Z]{2}\b', location):
            try:
                geocode_result = geolocator.geocode(location, exactly_one=True)
                if geocode_result:
                    coords = (geocode_result.latitude,
                              geocode_result.longitude)
                    logger.debug(f"Found coordinates: {coords}")
                    return coords
            except GeocoderTimedOut:
                pass

        # Try with different state contexts
        states = ["ME", "NH", "VT", "MA", "CT", "RI"]
        # Remove existing state if present
        base_location = re.sub(r',\s*[A-Z]{2}.*$', '', location)

        for state in states:
            try:
                location_with_state = f"{base_location}, {state}"
                geocode_result = geolocator.geocode(
                    location_with_state, exactly_one=True)
                if geocode_result:
                    coords = (geocode_result.latitude,
                              geocode_result.longitude)
                    logger.debug(
                        f"Found coordinates with state {state}: {coords}")
                    return coords
            except GeocoderTimedOut:
                continue

    except Exception as e:
        logger.error(f"Error geocoding location {location}: {str(e)}")

    return None


def find_nearest_cities(coordinates: Tuple[float, float], limit: int = 3) -> List[Dict[str, Any]]:
    """Find the nearest major cities and their distances."""
    if not coordinates:
        return []

    try:
        distances = []
        for city_name, city_info in MAJOR_CITIES.items():
            city_coords = city_info["coordinates"]
            distance = get_distance(coordinates, city_coords)
            distances.append({
                "city": city_name,
                "distance": round(distance, 1),
                "distance_bucket": get_bucket(distance, DISTANCE_BUCKETS)
            })

        # Sort by distance and return top N
        return sorted(distances, key=lambda x: x["distance"])[:limit]

    except Exception as e:
        logger.error(f"Error finding nearest cities: {str(e)}")
        return []
