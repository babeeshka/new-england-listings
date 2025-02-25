"""
New England Listings - Property data extraction for New England real estate.

This package provides tools to extract and analyze real estate listings 
from various platforms focusing on the New England region.
"""

from .main import process_listing, process_listings, get_extractor_for_url
from .utils import LocationService, TextProcessor, DateExtractor, rate_limiter
from .extractors import (
    BaseExtractor,
    RealtorExtractor,
    LandAndFarmExtractor,
    FarmlandExtractor,
    LandSearchExtractor,
    FarmLinkExtractor
)

__version__ = "0.2.0"

__all__ = [
    # Main processing functions
    "process_listing",
    "process_listings",
    "get_extractor_for_url",

    # Service classes
    "LocationService",
    "TextProcessor",
    "DateExtractor",

    # Rate limiting
    "rate_limiter",

    # Extractor classes
    "BaseExtractor",
    "RealtorExtractor",
    "LandAndFarmExtractor",
    "FarmlandExtractor",
    "LandSearchExtractor",
    "FarmLinkExtractor",

    # Version
    "__version__"
]
