# src/new_england_listings/utils/text.py
from typing import Tuple
import re
import logging
from ..config.constants import PRICE_BUCKETS, ACREAGE_BUCKETS

logger = logging.getLogger(__name__)


def get_range_bucket(value: float, buckets: dict) -> str:
    """
    Get the appropriate bucket for a numeric value where buckets represent ranges.
    The bucket key represents the start of the range.
    """
    bucket_thresholds = sorted(buckets.keys())
    for i, threshold in enumerate(bucket_thresholds):
        # If this is the last threshold, use it
        if i == len(bucket_thresholds) - 1:
            return buckets[threshold]
        # If value is less than the next threshold, use current bucket
        if value < bucket_thresholds[i + 1]:
            return buckets[threshold]
    return list(buckets.values())[-1]


def clean_price(price_text: str) -> Tuple[str, str]:
    """
    Clean price text and determine price bucket.
    
    Args:
        price_text: Raw price text from listing
        
    Returns:
        Tuple of (cleaned price string, price bucket)
    """
    if not price_text or "contact" in price_text.lower():
        return "Contact for Price", "N/A"

    try:
        # Clean the price text and extract numeric value
        numeric_text = re.sub(r'[^\d.]', '', price_text)
        if not numeric_text:
            return "Contact for Price", "N/A"

        numeric_price = float(numeric_text)
        price_bucket = get_range_bucket(numeric_price, PRICE_BUCKETS)

        # Format the price nicely
        if numeric_price >= 1000000:
            formatted_price = f"${numeric_price/1000000:.1f}M"
        else:
            formatted_price = f"${numeric_price:,.0f}"

        return formatted_price, price_bucket

    except (ValueError, TypeError) as e:
        logger.warning(f"Error cleaning price '{price_text}': {str(e)}")
        return "Contact for Price", "N/A"


def extract_acreage(text: str) -> Tuple[str, str]:
    """
    Extract acreage from text and determine bucket.
    
    Args:
        text: Text containing acreage information
        
    Returns:
        Tuple of (acreage string, acreage bucket)
    """
    if not text:
        return "Not specified", "Unknown"

    try:
        # Look for various acreage patterns
        patterns = [
            r'([\d,.]+)\s*acres?',
            r'([\d,.]+)\s*acre parcel',
            r'approximately\s*([\d,.]+)\s*acres?',
            r'about\s*([\d,.]+)\s*acres?',
            r'(\d+\.?\d*)\s*acres?'
        ]

        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                # Clean the matched number
                acres_str = match.group(1).replace(',', '')
                acres = float(acres_str)
                bucket = get_range_bucket(acres, ACREAGE_BUCKETS)

                # Always format with one decimal place for consistency
                formatted_acres = f"{acres:.1f} acres"
                return formatted_acres, bucket

        return "Not specified", "Unknown"

    except (ValueError, TypeError) as e:
        logger.warning(f"Error extracting acreage from '{text}': {str(e)}")
        return "Not specified", "Unknown"


def clean_html_text(text: str) -> str:
    """Clean text extracted from HTML."""
    if not text:
        return ""

    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Remove common HTML artifacts
    text = re.sub(r'[\r\n\t]', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    # Remove common special characters
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&quot;', '"')

    return text.strip()


def extract_property_type(text: str) -> str:
    """Extract property type from text description."""
    type_patterns = {
        'Single Family': r'single[\s-]?family|residential home',
        'Multi Family': r'multi[\s-]?family|duplex|triplex',
        'Farm': r'farm|ranch|agricultural',
        'Land': r'land|lot|acreage|vacant',
        'Commercial': r'commercial|business|retail|office',
    }

    text_lower = text.lower()
    for prop_type, pattern in type_patterns.items():
        if re.search(pattern, text_lower):
            return prop_type

    return "Other"
