"""
Date extraction and parsing utilities for New England Listings.
"""

from datetime import datetime, timedelta
import re
import logging
from typing import Optional, List, Tuple, Dict, Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Common date patterns with their corresponding format strings
DATE_PATTERNS = [
    # Month day, year
    (r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})', '%B %d %Y'),
    # Abbreviated month day, year
    (r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})', '%b %d %Y'),
    # MM/DD/YYYY
    (r'(\d{1,2})/(\d{1,2})/(\d{4})', '%m/%d/%Y'),
    # YYYY-MM-DD
    (r'(\d{4})-(\d{1,2})-(\d{1,2})', '%Y-%m-%d'),
    # MM-DD-YYYY
    (r'(\d{1,2})-(\d{1,2})-(\d{4})', '%m-%d-%Y'),
    # DD-MM-YYYY (European)
    (r'(\d{1,2})\.(\d{1,2})\.(\d{4})', '%d.%m.%Y')
]


class DateExtractor:
    """
    Utility class for extracting and parsing dates from various sources.
    Provides more robust date extraction with multiple fallback strategies.
    """

    @staticmethod
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
                ("div", {"class": "listing-date"}),
                ("span", {"class": "date"}),
                ("div", {"class": "property-date"})
            ],
            "Realtor.com": [
                ("div", {"data-testid": "listing-date"}),
                ("span", {"data-testid": "property-date"}),
                ("div", {"class": "list-date"})
            ],
            "Maine Farmland Trust": [
                ("div", {"class": "date"}),
                ("span", {"class": "post-date"}),
                ("div", {"class": "listing-date"})
            ],
            "LandSearch": [
                ("div", {"class": "listing-date"}),
                ("span", {"class": "date-posted"}),
                ("time", {})
            ],
            "New England Farmland Finder": [
                ("span", {"class": "date-display-single"}),
                ("div", {"class": "field-name-post-date"}),
                ("time", {})
            ]
        }

        # Try platform-specific selectors first
        if platform in platform_selectors:
            for tag, attrs in platform_selectors[platform]:
                try:
                    elem = soup.find(tag, **attrs)
                    if elem:
                        date_text = elem.text.strip()
                        logger.debug(
                            f"Found date using platform selector: {date_text}")
                        break
                except Exception as e:
                    logger.debug(
                        f"Error with selector {tag}, {attrs}: {str(e)}")

        # If no date found, try common patterns in text
        if not date_text:
            date_indicators = [
                r'Listed\s+on\s+',
                r'Posted\s+on\s+',
                r'Date\s+Listed:\s+',
                r'Added:\s+',
                r'Published:\s+',
                r'Date\s+Posted:\s+',
                r'Listed:\s+'
            ]

            for text in soup.stripped_strings:
                for indicator in date_indicators:
                    match = re.search(f"{indicator}([^\.]+)", text, re.I)
                    if match:
                        date_text = match.group(1).strip()
                        logger.debug(
                            f"Found date using text pattern: {date_text}")
                        break
                if date_text:
                    break

        # Generic date patterns
        if not date_text:
            # Try to find any elements with date-related classes
            date_classes = ['date', 'listing-date',
                            'post-date', 'published-date', 'time']
            for cls in date_classes:
                elem = soup.find(class_=cls)
                if elem:
                    date_text = elem.text.strip()
                    logger.debug(f"Found date using class: {date_text}")
                    break

            # Try looking for time elements
            if not date_text:
                time_elem = soup.find('time')
                if time_elem:
                    date_text = time_elem.text.strip()
                    if not date_text and time_elem.get('datetime'):
                        date_text = time_elem.get('datetime')
                    logger.debug(f"Found date using time element: {date_text}")

        if date_text:
            # Try to parse the date
            cleaned_date = DateExtractor.parse_date_string(date_text)
            if cleaned_date:
                return cleaned_date

        # Default to current date if no date found or couldn't parse
        logger.warning(
            f"Could not find listing date for {platform}, using current date")
        return datetime.now().strftime('%Y-%m-%d')

    @staticmethod
    def parse_date_string(date_text: str) -> Optional[str]:
        """
        Parse a date string using various formats with improved fallback.
        
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

        logger.debug(f"Parsing date text: {date_text}")

        # Try each date pattern
        for pattern, date_format in DATE_PATTERNS:
            match = re.search(pattern, date_text)
            if match:
                try:
                    if date_format.startswith('%B') or date_format.startswith('%b'):
                        # For month name patterns
                        month, day, year = match.groups()
                        # Handle 'Sept' specifically
                        if month.lower() == 'sept':
                            month = 'Sep'
                        date_str = f"{month} {day} {year}"
                    else:
                        # For numeric patterns
                        date_str = match.group(0)

                    parsed_date = datetime.strptime(date_str, date_format)
                    logger.debug(f"Successfully parsed date: {parsed_date}")
                    return parsed_date.strftime('%Y-%m-%d')

                except ValueError as e:
                    logger.debug(
                        f"Date format {date_format} failed for {date_str}: {str(e)}")
                    continue

        # Try dateutil parser as fallback
        dateutil_result = DateExtractor.parse_with_dateutil(date_text)
        if dateutil_result:
            return dateutil_result

        # Last resort: try direct datetime parsing
        try:
            # Try to parse ISO format dates
            parsed_date = datetime.fromisoformat(
                date_text.replace('Z', '+00:00'))
            return parsed_date.strftime('%Y-%m-%d')
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse date string: {date_text}")
            return None
    
    @staticmethod
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
        except ValueError as e:
            logger.warning(f"Error checking if listing is recent: {str(e)}")
            return False

    @staticmethod
    def format_date_for_display(date_str: str, format: str = '%b %d, %Y') -> str:
        """
        Format a date string for display.
        
        Args:
            date_str: Date string in YYYY-MM-DD format
            format: Output format
            
        Returns:
            Formatted date string
        """
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime(format)
        except ValueError as e:
            logger.warning(f"Error formatting date: {str(e)}")
            return date_str

    @staticmethod
    def get_current_date() -> str:
        """
        Get current date in YYYY-MM-DD format.
        
        Returns:
            Current date string
        """
        return datetime.now().strftime('%Y-%m-%d')

    @staticmethod
    def extract_date_from_text(text: str) -> Optional[str]:
        """
        Extract a date from arbitrary text.
        
        Args:
            text: Text that may contain a date
            
        Returns:
            Formatted date string (YYYY-MM-DD) or None if no date found
        """
        if not text:
            return None

        # Try each date pattern
        for pattern, date_format in DATE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                try:
                    if date_format.startswith('%B') or date_format.startswith('%b'):
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

    @staticmethod
    def parse_with_dateutil(date_text: str) -> Optional[str]:
        """
        Try to parse date using dateutil as a fallback.
        
        Args:
            date_text: Raw date string
            
        Returns:
            Formatted date string (YYYY-MM-DD) or None if parsing fails
        """
        if not date_text:
            return None

        try:
            # Use dateutil parser which handles many formats automatically
            from dateutil import parser
            parsed_date = parser.parse(date_text)
            return parsed_date.strftime('%Y-%m-%d')
        except (ImportError, ValueError, AttributeError):
            logger.warning(f"Could not parse date with dateutil: {date_text}")
            return None
    
# For backward compatibility, provide the old function names
# that reference the new static methods

def extract_listing_date(soup: BeautifulSoup, platform: str) -> str:
    """Backward compatibility wrapper for DateExtractor.extract_listing_date"""
    return DateExtractor.extract_listing_date(soup, platform)


def parse_date_string(date_text: str) -> Optional[str]:
    """Backward compatibility wrapper for DateExtractor.parse_date_string"""
    return DateExtractor.parse_date_string(date_text)


def is_recent_listing(date_str: str, days: int = 30) -> bool:
    """Backward compatibility wrapper for DateExtractor.is_recent_listing"""
    return DateExtractor.is_recent_listing(date_str, days)
