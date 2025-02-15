# ./src/new_england_listings/config/__init__.py
"""Configuration module for New England Listings."""

from .constants import (
    PRICE_BUCKETS,
    ACREAGE_BUCKETS,
    DISTANCE_BUCKETS,
    POPULATION_BUCKETS,
    MAJOR_CITIES,
    PLATFORMS
)
from .settings import (
    NOTION_API_KEY,
    NOTION_DATABASE_ID,
    DEFAULT_TIMEOUT,
    MAX_RETRIES
)

__all__ = [
    "PRICE_BUCKETS",
    "ACREAGE_BUCKETS",
    "DISTANCE_BUCKETS",
    "POPULATION_BUCKETS",
    "MAJOR_CITIES",
    "PLATFORMS",
    "NOTION_API_KEY",
    "NOTION_DATABASE_ID",
    "DEFAULT_TIMEOUT",
    "MAX_RETRIES"
]
