# ./src/new_england_listings/extractors/utils.py
"""Utility functions for property listing extractors."""

from typing import Optional, Type
from urllib.parse import urlparse
from .base import BaseExtractor
from .realtor import RealtorExtractor
from .landandfarm import LandAndFarmExtractor
from .farmland import FarmlandExtractor
import logging

logger = logging.getLogger(__name__)


def get_extractor_for_url(url: str) -> Optional[Type[BaseExtractor]]:
    """
    Get the appropriate extractor class for a given URL.
    
    Args:
        url: The listing URL
        
    Returns:
        Extractor class appropriate for the URL, or None if no match
    """
    domain = urlparse(url).netloc.lower()

    # Map domains to extractors
    EXTRACTORS = {
        "realtor.com": RealtorExtractor,
        "landandfarm.com": LandAndFarmExtractor,
        "mainefarmlandtrust.org": FarmlandExtractor,
        "newenglandfarmlandfinder.org": FarmlandExtractor
    }

    # Find the matching extractor
    for domain_pattern, extractor_class in EXTRACTORS.items():
        if domain_pattern in domain:
            logger.info(
                f"Using {extractor_class.__name__} for domain: {domain}")
            return extractor_class

    logger.warning(f"No matching extractor found for domain: {domain}")
    return None


def validate_url(url: str) -> bool:
    """
    Validate if a URL is supported by any of our extractors.
    
    Args:
        url: The URL to validate
        
    Returns:
        bool: True if URL is supported, False otherwise
    """
    return get_extractor_for_url(url) is not None


def get_domain_type(url: str) -> str:
    """
    Get the type of domain (realtor, farm, land, etc.).
    
    Args:
        url: The URL to analyze
        
    Returns:
        str: Domain type or 'unknown'
    """
    domain = urlparse(url).netloc.lower()

    DOMAIN_TYPES = {
        "realtor": ["realtor.com", "zillow.com", "trulia.com"],
        "farm": ["mainefarmlandtrust.org", "newenglandfarmlandfinder.org"],
        "land": ["landandfarm.com", "landsearch.com", "landwatch.com"],
        "local": ["maine.gov", "vermont.gov", "nh.gov"]
    }

    for domain_type, patterns in DOMAIN_TYPES.items():
        if any(pattern in domain for pattern in patterns):
            return domain_type

    return "unknown"


def clean_url(url: str) -> str:
    """
    Clean a URL by removing tracking parameters and normalizing format.
    
    Args:
        url: The URL to clean
        
    Returns:
        str: Cleaned URL
    """
    parsed = urlparse(url)

    # List of parameters to preserve
    KEEP_PARAMS = [
        'id',
        'listingId',
        'propertyId',
        'mls',
        'farm-id'
    ]

    # Remove fragments
    cleaned = parsed._replace(fragment='')

    # Keep only essential query parameters
    if parsed.query:
        from urllib.parse import parse_qs, urlencode
        params = parse_qs(parsed.query)
        essential_params = {
            k: v[0] for k, v in params.items()
            if k.lower() in KEEP_PARAMS
        }
        cleaned = cleaned._replace(query=urlencode(essential_params))

    return cleaned.geturl()


def extract_listing_id(url: str) -> Optional[str]:
    """
    Extract a unique listing ID from the URL if possible.
    
    Args:
        url: The listing URL
        
    Returns:
        Optional[str]: Listing ID if found, None otherwise
    """
    parsed = urlparse(url)
    path = parsed.path

    # Check for common ID patterns in the path
    id_patterns = [
        r'(?:property|listing|home)[/-](\w+)/?$',  # general pattern
        r'farm-id-(\d+)',  # farmland pattern
        r'MLS-(\w+)',      # MLS pattern
        r'_(\w+)_[A-Z]{2}'  # realtor.com pattern
    ]

    for pattern in id_patterns:
        import re
        match = re.search(pattern, path, re.I)
        if match:
            return match.group(1)

    # Check query parameters for IDs
    if parsed.query:
        from urllib.parse import parse_qs
        params = parse_qs(parsed.query)
        for key in ['id', 'listingId', 'propertyId', 'farm-id']:
            if key in params:
                return params[key][0]

    return None
