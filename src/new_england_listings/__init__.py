# src/new_england_listings/__init__.py (Update)

"""
New England Listings - Property data extraction for New England real estate.

This package provides tools to extract and analyze real estate listings 
from various platforms focusing on the New England region.
"""

from .main import process_listing, process_listings, get_extractor_for_url
from .utils import LocationService, TextProcessor, DateExtractor, rate_limiter
from .utils.logging_config import configure_logging, get_logger
from .extractors import (
    BaseExtractor,
    RealtorExtractor,
    LandAndFarmExtractor,
    FarmlandExtractor,
    LandSearchExtractor,
    FarmLinkExtractor
)

__version__ = "0.2.0"

# Configure logging at package initialization
configure_logging(
    level="INFO",  # Can be overridden by environment variable
    log_dir="logs",
    app_name="new_england_listings",
    context={"version": __version__}
)

# Create package-level logger
logger = get_logger(__name__)
logger.info(f"New England Listings version {__version__} initialized")

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

    # Logging
    "configure_logging",
    "get_logger",

    # Version
    "__version__"
]
