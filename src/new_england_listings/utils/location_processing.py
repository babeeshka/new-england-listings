# utils/location_processing.py

from typing import Dict, Any, Optional
from ..utils.geocoding import (
    get_location_coordinates,
    get_distance,
    find_nearest_cities
)
import logging

logger = logging.getLogger(__name__)


def process_location_details(location: str) -> Dict[str, Any]:
    """
    Process comprehensive location details including nearest city, nearby restaurants, and contextual metrics.

    Args:
        location (str): The raw location string.

    Returns:
        Dict[str, Any]: Enriched location data.
    """
    location_details = {
        "location": location or "Location Unknown",
        "coordinates": None,
        "nearest_city": None,
        "distance_to_nearest_city": None,
        "nearby_restaurants": [],
        "nearest_hospital": None,
        "hospital_distance": None
    }

    try:
        # Get coordinates
        coordinates = get_location_coordinates(location)
        if not coordinates:
            logger.warning(f"Coordinates not found for location: {location}")
            return location_details

        location_details["coordinates"] = coordinates

        # Find nearest cities
        nearest_cities = find_nearest_cities(coordinates, limit=1)
        if nearest_cities:
            city_info = nearest_cities[0]
            location_details["nearest_city"] = city_info.get("name")
            location_details["distance_to_nearest_city"] = city_info.get(
                "distance")

        # Dummy data for nearby restaurants (Assuming integration with a real API in future)
        location_details["nearby_restaurants"] = [
            {"name": "Sample Diner", "distance_miles": 1.5},
            {"name": "Local Eatery", "distance_miles": 2.3}
        ]

        # Dummy data for nearest hospital (Assuming integration with a real API in future)
        location_details["nearest_hospital"] = "Regional Medical Center"
        location_details["hospital_distance"] = get_distance(
            coordinates, (43.6615, -70.2553))  # Example coords

    except Exception as e:
        logger.error(f"Error processing location details: {str(e)}")

    return location_details
