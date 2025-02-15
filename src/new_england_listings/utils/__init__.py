# ./src/new_england_listings/utils/__init__.py
"""Utility functions for New England Listings."""

import logging
from .browser import get_page_content, get_selenium_driver
from .dates import extract_listing_date, parse_date_string, is_recent_listing
from .geocoding import (
    get_location_coordinates,
    find_nearest_cities,
    parse_location_from_url
)
from .text import (
    clean_price,
    extract_acreage,
    clean_html_text,
    extract_property_type
)

__all__ = [
    "get_page_content",
    "get_selenium_driver",
    "extract_listing_date",
    "parse_date_string",
    "is_recent_listing",
    "get_location_coordinates",
    "find_nearest_cities",
    "parse_location_from_url",
    "clean_price",
    "extract_acreage",
    "clean_html_text",
    "extract_property_type"
]

logger = logging.getLogger(__name__)
