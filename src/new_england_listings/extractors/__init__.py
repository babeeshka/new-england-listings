# src/new_england_listings/extractors/__init__.py

"""
Property listing extractors for New England Listings.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

from .base import BaseExtractor
from .realtor import RealtorExtractor
from .landandfarm import LandAndFarmExtractor
from .farmland import FarmlandExtractor
from .landsearch import LandSearchExtractor
from .farmlink import FarmLinkExtractor
from .landwatch import LandWatchExtractor
from .zillow import ZillowExtractor 

logger = logging.getLogger(__name__)


def get_extractor_for_url(url: str) -> Optional[BaseExtractor]:
    """
    Get the appropriate extractor for a URL.
    
    Args:
        url: The URL of the listing
        
    Returns:
        An instance of the appropriate extractor, or None if no matching extractor found
    """
    domain = urlparse(url).netloc.lower()

    logger.debug(f"Getting extractor for domain: {domain}")

    if "landsearch.com" in domain:
        return LandSearchExtractor(url)
    elif "landandfarm.com" in domain:
        return LandAndFarmExtractor(url)
    elif "farmlink.mainefarmlandtrust.org" in domain:
        return FarmLinkExtractor(url)
    elif "realtor.com" in domain:
        return RealtorExtractor(url)
    elif any(x in domain for x in ["mainefarmlandtrust.org", "newenglandfarmlandfinder.org"]):
        return FarmlandExtractor(url)
    elif "landwatch.com" in domain:
        return LandWatchExtractor(url)
    elif "zillow.com" in domain:
        return ZillowExtractor(url)

    logger.warning(f"No extractor available for domain: {domain}")
    return None


__all__ = [
    "BaseExtractor",
    "RealtorExtractor",
    "LandAndFarmExtractor",
    "FarmlandExtractor",
    "LandSearchExtractor",
    "FarmLinkExtractor",
    "LandWatchExtractor",
    "ZillowExtractor", 
    "get_extractor_for_url"
]
