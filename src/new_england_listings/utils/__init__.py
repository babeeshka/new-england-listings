"""
Utility functions and services for New England Listings.
"""

import logging

# Browser utilities
from .browser import get_page_content, get_stealth_driver

# Service classes
from .location_service import LocationService, TextProcessingService
from .text import TextProcessor
from .dates import DateExtractor

# Rate limiting
from .rate_limiting import rate_limiter, RateLimitExceeded

# Caching utilities
from .caching_utils import persistent_cache, memoize

# Create singleton instances of services for convenience
location_service = LocationService()
text_processor = TextProcessor()

__all__ = [
    # Browser utilities
    "get_page_content",
    "get_stealth_driver",

    # Service classes
    "LocationService",
    "TextProcessingService",
    "TextProcessor",
    "DateExtractor",

    # Service instances
    "location_service",
    "text_processor",

    # Rate limiting
    "rate_limiter",
    "RateLimitExceeded",

    # Caching
    "persistent_cache",
    "memoize"
]

logger = logging.getLogger(__name__)
