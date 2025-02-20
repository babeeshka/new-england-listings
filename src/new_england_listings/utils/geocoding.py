# src/new_england_listings/utils/geocoding.py
from functools import lru_cache
from typing import Optional, Tuple, Dict, List, Any, Union
from urllib.parse import urlparse
import re
import logging
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut
from ..config.constants import (
    MAJOR_CITIES,
    DISTANCE_BUCKETS,
    SCHOOL_RATING_BUCKETS,
    POPULATION_BUCKETS
)

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


def get_county_coordinates(county: str, state: str = "ME") -> Optional[Tuple[float, float]]:
    """Get coordinates for a county center."""
    geolocator = Nominatim(user_agent="new_england_listings", timeout=10)

    try:
        # Try different query formats
        queries = [
            f"{county} County, {state}, USA",
            f"{county} County, {state}",
            f"{county}, {state}, United States"
        ]

        for query in queries:
            try:
                logger.debug(f"Trying to geocode county with query: {query}")
                geocode_result = geolocator.geocode(
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


@lru_cache(maxsize=1000)
def get_location_coordinates(location: str) -> Optional[Tuple[float, float]]:
    """Get coordinates for a location using geocoding."""
    if not location or location == "Location Unknown":
        return None

    geolocator = Nominatim(user_agent="new_england_listings", timeout=10)
    logger.debug(f"Geocoding location: {location}")

    try:
        # Check if this is a county location
        county_match = re.match(r'(\w+)\s+County,\s*(\w{2})', location)
        if county_match:
            county, state = county_match.groups()
            coords = get_county_coordinates(county, state)
            if coords:
                return coords

        # Clean up the location string
        location = re.sub(r'\s+', ' ', location).strip()

        # If we already have a state code, try that first
        if re.search(r',\s*[A-Z]{2}\b', location):
            try:
                geocode_result = geolocator.geocode(
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
                geocode_result = geolocator.geocode(
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


def analyze_location_amenities(location: Union[str, Tuple[float, float]],
                               max_distance: int = 60) -> Dict[str, Any]:
    """
    Comprehensive analysis of location amenities and services.

    Args:
        location: Location string or coordinates
        max_distance: Maximum distance to consider (in miles)

    Returns:
        Dictionary containing detailed location analysis
    """
    try:
        # Get coordinates if location is a string
        if isinstance(location, str):
            coordinates = get_location_coordinates(location)
            if not coordinates:
                logger.error(f"Could not geocode location: {location}")
                return {}
        else:
            coordinates = location

        analysis = {}

        # Find and analyze nearby cities
        nearby_cities = find_nearest_cities(coordinates)
        if not nearby_cities:
            return {}

        # Medical Analysis
        hospitals = []
        for city in nearby_cities:
            city_info = MAJOR_CITIES[city["city"]]
            if "Hospital" in city_info.get("amenities", []):
                hospitals.append({
                    "name": f"{city['city']} Hospital",
                    "distance": city["distance"],
                    "distance_bucket": city["distance_bucket"]
                })
        if hospitals:
            closest_hospital = min(hospitals, key=lambda x: x["distance"])
            analysis.update({
                "hospital_distance": f"{closest_hospital['distance']:.1f}",
                "closest_hospital": closest_hospital["name"],
                "hospital_distance_bucket": closest_hospital["distance_bucket"]
            })

        # School Analysis
        schools = []
        for city in nearby_cities:
            city_info = MAJOR_CITIES[city["city"]]
            if "school_rating" in city_info:
                schools.append({
                    "district": city["city"],
                    "rating": city_info["school_rating"],
                    "distance": city["distance"]
                })
        if schools:
            best_school = max(schools, key=lambda x: x["rating"])
            closest_school = min(schools, key=lambda x: x["distance"])
            analysis.update({
                "school_district": closest_school["district"],
                "school_rating": f"{closest_school['rating']}/10",
                "school_rating_cat": get_bucket(closest_school["rating"], SCHOOL_RATING_BUCKETS),
                "best_nearby_district": best_school["district"] if best_school != closest_school else None
            })

        # Population Center Analysis
        population_centers = []
        for city in nearby_cities:
            city_info = MAJOR_CITIES[city["city"]]
            population_centers.append({
                "city": city["city"],
                "population": city_info["population"],
                "distance": city["distance"]
            })
        if population_centers:
            largest_city = max(population_centers,
                               key=lambda x: x["population"])
            analysis.update({
                "nearest_population_center": largest_city["city"],
                "town_population": str(largest_city["population"]),
                "town_pop_bucket": get_bucket(largest_city["population"], POPULATION_BUCKETS)
            })

        # Amenities Analysis
        amenities = []
        cultural_venues = []
        for city in nearby_cities[:3]:  # Look at 3 closest cities
            city_info = MAJOR_CITIES[city["city"]]
            amenities.extend(city_info.get("amenities", []))
            # Look for cultural amenities
            cultural = [a for a in city_info.get("amenities", [])
                        if any(word in a for word in ["Art", "Museum", "Theater", "University"])]
            if cultural:
                cultural_venues.append({
                    "city": city["city"],
                    "distance": city["distance"],
                    "venues": cultural
                })

        # Add amenities analysis
        if amenities:
            analysis["other_amenities"] = " | ".join(
                set(amenities[:5]))  # Top 5 unique amenities
        if cultural_venues:
            # Closest cultural venue
            analysis["cultural_venues"] = cultural_venues[0]

        return analysis

    except Exception as e:
        logger.error(f"Error in location analysis: {str(e)}")
        return {}


def get_comprehensive_location_info(location: str) -> Dict[str, Any]:
    """
    Get comprehensive information about a location.

    Args:
        location: Location string (e.g., "Portland, ME")

    Returns:
        Dictionary containing all location-related information
    """
    try:
        # Get coordinates
        coords = get_location_coordinates(location)
        if not coords:
            return {}

        # Get base analysis
        info = analyze_location_amenities(coords)

        # Add distance to Portland (as it's a major reference point)
        portland_coords = MAJOR_CITIES["Portland, ME"]["coordinates"]
        portland_distance = get_distance(coords, portland_coords)
        info.update({
            "distance_to_portland": f"{portland_distance:.1f}",
            "portland_distance_bucket": get_bucket(portland_distance, DISTANCE_BUCKETS)
        })

        return info

    except Exception as e:
        logger.error(f"Error getting comprehensive location info: {str(e)}")
        return {}
