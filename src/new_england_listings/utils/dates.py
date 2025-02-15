# src/new_england_listings/utils/dates.py
from datetime import datetime
import re
import logging
from bs4 import BeautifulSoup
from typing import Optional
from ..config.constants import DATE_PATTERNS

logger = logging.getLogger(__name__)


def extract_listing_date(soup: BeautifulSoup, platform: str) -> str:
    """
    Extract the listing date from the page based on platform.
    
    Args:
        soup: BeautifulSoup object of the page
        platform: Platform name (e.g., "Realtor.com")
        
    Returns:
        Formatted date string (YYYY-MM-DD) or current date if not found
    """
    date_text = None

    # Platform-specific date selectors
    platform_selectors = {
        "Land and Farm": [
            ("div", {"class_": "listing-date"}),
            ("span", {"class_": "date"}),
            ("div", {"class_": "property-date"})
        ],
        "Realtor.com": [
            ("div", {"data-testid": "listing-date"}),
            ("span", {"data-testid": "property-date"}),
            ("div", {"class_": "listing-date"})
        ],
        "Maine Farmland Trust": [
            ("div", {"class_": "date"}),
            ("span", {"class_": "post-date"}),
            ("div", {"class_": "listing-date"})
        ]
    }

    # Try platform-specific selectors first
    if platform in platform_selectors:
        for tag, attrs in platform_selectors[platform]:
            elem = soup.find(tag, **attrs)
            if elem:
                date_text = elem.text.strip()
                break

    # If no date found, try common patterns in text
    if not date_text:
        date_indicators = [
            r'Listed\s+on\s+',
            r'Posted\s+on\s+',
            r'Date\s+Listed:\s+',
            r'Added:\s+',
            r'Published:\s+'
        ]

        for text in soup.stripped_strings:
            for indicator in date_indicators:
                match = re.search(f"{indicator}([^\.]+)", text, re.I)
                if match:
                    date_text = match.group(1).strip()
                    break
            if date_text:
                break

    if date_text:
        # Try to parse the date
        cleaned_date = parse_date_string(date_text)
        if cleaned_date:
            return cleaned_date

    # Default to current date if no date found or couldn't parse
    logger.warning(
        f"Could not find listing date for {platform}, using current date")
    return datetime.now().strftime('%Y-%m-%d')


def parse_date_string(date_text: str) -> Optional[str]:
    """
    Parse a date string using various formats.
    
    Args:
        date_text: Raw date string
        
    Returns:
        Formatted date string (YYYY-MM-DD) or None if parsing fails
    """
    if not date_text:
        return None

    # Clean up the date text
    date_text = re.sub(r'^(?:Listed|Posted|Added|Date Listed)(?:\s+on)?:\s+', '',
                       date_text,
                       flags=re.I)
    date_text = date_text.strip()

    # Try each date pattern
    for pattern, date_format in DATE_PATTERNS:
        match = re.search(pattern, date_text)
        if match:
            try:
                if date_format.startswith('%B'):
                    # For month name patterns
                    date_str = ' '.join(match.groups())
                else:
                    # For numeric patterns
                    date_str = match.group(0)

                parsed_date = datetime.strptime(date_str, date_format)
                return parsed_date.strftime('%Y-%m-%d')

            except ValueError:
                continue

    return None


def is_recent_listing(date_str: str, days: int = 30) -> bool:
    """
    Check if a listing is recent within specified days.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        days: Number of days to consider recent
        
    Returns:
        Boolean indicating if listing is recent
    """
    try:
        listing_date = datetime.strptime(date_str, '%Y-%m-%d')
        days_old = (datetime.now() - listing_date).days
        return days_old <= days
    except ValueError:
        return False
