# ./src/new_england_listings/extractors/utils.py
"""Utility functions for property listing extractors."""

from typing import Optional, Type
from urllib.parse import urlparse
from .base import BaseExtractor
from .realtor import RealtorExtractor
from .landandfarm import LandAndFarmExtractor
from .farmland import FarmlandExtractor
from .landsearch import LandSearchExtractor
from .farmlink import FarmLinkExtractor
import logging

logger = logging.getLogger(__name__)

def get_extractor_for_url(url: str) -> Optional[Type[BaseExtractor]]:
    """Get the appropriate extractor class for a given URL."""
    domain = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()

    # More specific URL patterns take precedence
    if "farmlink.mainefarmlandtrust.org" in domain:
        logger.info("Using FarmLinkExtractor for FarmLink listing")
        return FarmLinkExtractor
    elif "mainefarmlandtrust.org" in domain:
        logger.info("Using FarmlandExtractor for MFT listing")
        return FarmlandExtractor
    elif "landsearch.com" in domain:
        logger.info("Using LandSearchExtractor for LandSearch listing")
        return LandSearchExtractor
    elif "landandfarm.com" in domain:
        logger.info("Using LandAndFarmExtractor for Land and Farm listing")
        return LandAndFarmExtractor
    elif "realtor.com" in domain:
        logger.info("Using RealtorExtractor for Realtor.com listing")
        return RealtorExtractor
    elif "newenglandfarmlandfinder.org" in domain:
        logger.info("Using FarmlandExtractor for NEFF listing")
        return FarmlandExtractor

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
