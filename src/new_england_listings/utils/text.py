"""
Text processing utilities for New England Listings.
Includes both the new TextProcessor class and backward compatibility functions.
"""

from typing import Tuple, Dict, Optional, List, Any
import re
import logging
import html
from collections import Counter
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


class TextProcessor:
    """
    Utility class for processing and standardizing text in property listings.
    Provides robust text cleaning, extraction, and normalization.
    """

    @staticmethod
    def clean_html_text(text: str) -> str:
        """
        Enhanced HTML text cleaning.
        
        Args:
            text: Raw HTML text
        
        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text).strip()

        # Handle HTML entities
        text = html.unescape(text)

        # Remove non-printable characters
        text = ''.join(char for char in text if char.isprintable())

        return text.strip()

    @staticmethod
    def extract_text_after_label(text: str, label: str, max_words: int = 10) -> Optional[str]:
        """
        Extract text that follows a specific label.
        
        Args:
            text: Source text
            label: Label to find
            max_words: Maximum number of words to extract after the label
            
        Returns:
            Extracted text or None if not found
        """
        if not text or not label:
            return None

        pattern = fr'{re.escape(label)}[:\s]+([^\.!\?]+)'
        match = re.search(pattern, text, re.I)
        if match:
            extracted = match.group(1).strip()
            # Limit to max_words
            words = extracted.split()
            if len(words) > max_words:
                extracted = ' '.join(words[:max_words])
            return extracted

        return None

    @staticmethod
    def extract_numeric_value(text: str, default: Optional[float] = None) -> Optional[float]:
        """
        Extract the first numeric value from text.
        
        Args:
            text: Source text
            default: Default value if no numeric value found
            
        Returns:
            Extracted numeric value or default if not found
        """
        if not text:
            return default

        match = re.search(r'(\d+(?:\.\d+)?)', text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

        return default

    @staticmethod
    def standardize_price(price_text: str) -> Tuple[str, str]:
        """
        Standardize price processing with robust parsing.
        
        Args:
            price_text: Raw price text
        
        Returns:
            Tuple of (formatted price, price bucket)
        """
        # Import here to avoid circular imports
        from ..config.constants import PRICE_BUCKETS

        if not price_text or isinstance(price_text, str) and 'contact' in price_text.lower():
            return "Contact for Price", "N/A"

        try:
            # Remove non-numeric characters except decimal point
            numeric_text = re.sub(r'[^\d.]', '', price_text)

            if not numeric_text:
                return "Contact for Price", "N/A"

            # Convert to float
            price_value = float(numeric_text)

            # Determine price bucket
            price_bucket = next(
                (bucket for threshold, bucket in sorted(PRICE_BUCKETS.items())
                 if price_value < threshold),
                list(PRICE_BUCKETS.values())[-1]
            )

            # Format price
            if price_value >= 1_000_000:
                formatted_price = f"${price_value/1_000_000:.1f}M"
            else:
                formatted_price = f"${price_value:,.0f}"

            return formatted_price, price_bucket

        except (ValueError, TypeError) as e:
            logger.warning(f"Error processing price '{price_text}': {e}")
            return "Contact for Price", "N/A"

    @staticmethod
    def standardize_acreage(acreage_text: str) -> Tuple[str, str]:
        """
        Standardize acreage processing with multiple parsing strategies.
        
        Args:
            acreage_text: Raw acreage text
        
        Returns:
            Tuple of (formatted acreage, acreage bucket)
        """
        # Import here to avoid circular imports
        from ..config.constants import ACREAGE_BUCKETS

        if not acreage_text:
            return "Not specified", "Unknown"

        try:
            # Comprehensive acreage extraction patterns
            acreage_patterns = [
                r'(\d+(?:\.\d+)?)\s*acres?',
                r'approximately\s*(\d+(?:\.\d+)?)\s*acres?',
                r'about\s*(\d+(?:\.\d+)?)\s*acres?',
                r'(\d+(?:\.\d+)?)\s*acre\s*(?:lot|parcel)'
            ]

            for pattern in acreage_patterns:
                match = re.search(pattern, acreage_text.lower())
                if match:
                    # Clean and convert to float
                    acres_str = match.group(1).replace(',', '')
                    acres = float(acres_str)

                    # Determine acreage bucket
                    acreage_bucket = next(
                        (bucket for threshold, bucket in sorted(ACREAGE_BUCKETS.items())
                         if acres < threshold),
                        list(ACREAGE_BUCKETS.values())[-1]
                    )

                    # Format with one decimal place
                    formatted_acres = f"{acres:.1f} acres"
                    return formatted_acres, acreage_bucket

            # If no match found
            return "Not specified", "Unknown"

        except (ValueError, TypeError) as e:
            logger.warning(f"Error processing acreage '{acreage_text}': {e}")
            return "Not specified", "Unknown"

    @staticmethod
    def extract_property_type(text: str) -> str:
        """
        Enhanced property type extraction with more patterns.
        
        Args:
            text: Description text
        
        Returns:
            Standardized property type
        """
        # Expand property type detection patterns
        type_patterns = {
            'Single Family': [
                r'single[\s-]?family',
                r'residential\s*home?',
                r'\d+\s*bed',
                r'single[\s-]?story',
                r'residential\s*property'
            ],
            'Multi Family': [
                r'multi[\s-]?family',
                r'duplex',
                r'triplex',
                r'fourplex',
                r'apartment\s*building'
            ],
            'Farm': [
                r'farm',
                r'ranch',
                r'agricultural',
                r'farmland',
                r'pasture',
                r'crop\s*land'
            ],
            'Land': [
                r'undeveloped\s*land',
                r'vacant\s*lot',
                r'land\s*parcel',
                r'empty\s*lot',
                r'raw\s*land'
            ],
            'Commercial': [
                r'commercial',
                r'business',
                r'retail',
                r'office',
                r'industrial',
                r'investment\s*property'
            ]
        }

        # Normalize text
        text_lower = text.lower()

        # Check each property type
        for prop_type, patterns in type_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return prop_type

        return "Unknown"

    @staticmethod
    def extract_bed_bath_count(text: str) -> Dict[str, Optional[str]]:
        """
        Extract bedroom and bathroom counts from text.
        
        Args:
            text: Source text
            
        Returns:
            Dictionary with 'beds' and 'baths' keys
        """
        result = {'beds': None, 'baths': None}

        # Look for bedroom pattern
        bed_match = re.search(r'(\d+)\s*(?:bed|bedroom|BR)', text, re.I)
        if bed_match:
            result['beds'] = bed_match.group(1)

        # Look for bathroom pattern
        bath_match = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:bath|bathroom|BA)', text, re.I)
        if bath_match:
            result['baths'] = bath_match.group(1)

        return result

    @staticmethod
    def extract_keywords(text: str, min_word_length: int = 4, max_keywords: int = 10) -> List[str]:
        """
        Extract important keywords from text.
        
        Args:
            text: Source text
            min_word_length: Minimum word length to consider
            max_keywords: Maximum number of keywords to return
            
        Returns:
            List of extracted keywords
        """
        if not text:
            return []

        # Clean and normalize text
        text = TextProcessor.clean_html_text(text.lower())

        # Split into words and filter
        words = re.findall(r'\b[a-z]{' + str(min_word_length) + r',}\b', text)

        # Remove common stopwords
        stopwords = {'with', 'this', 'that', 'have', 'from', 'they', 'will', 'would', 'could',
                     'should', 'what', 'when', 'where', 'which', 'there', 'their', 'about'}
        words = [w for w in words if w not in stopwords]

        # Count word frequencies
        word_counts = Counter(words)

        # Return top keywords
        return [word for word, _ in word_counts.most_common(max_keywords)]

    @staticmethod
    def summarize_text(text: str, max_length: int = 200) -> str:
        """
        Generate a summary of text.
        
        Args:
            text: Source text
            max_length: Maximum length of summary
            
        Returns:
            Summarized text
        """
        if not text:
            return ""

        # Clean and normalize
        text = TextProcessor.clean_html_text(text)

        # If text is already short enough, return it
        if len(text) <= max_length:
            return text

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)

        # Start with first sentence
        summary = sentences[0]

        # Add sentences until we hit the max length
        i = 1
        while i < len(sentences) and len(summary) + len(sentences[i]) + 1 <= max_length:
            summary += " " + sentences[i]
            i += 1

        # If we have more sentences, add ellipsis
        if i < len(sentences):
            summary += "..."

        return summary

    @staticmethod
    def extract_from_soup(soup: BeautifulSoup, selectors: List[Dict[str, Any]]) -> Optional[str]:
        """
        Try multiple selectors to extract text from BeautifulSoup.
        
        Args:
            soup: BeautifulSoup object
            selectors: List of selector dictionaries
            
        Returns:
            Extracted text or None if not found
        """
        for selector in selectors:
            try:
                # Handle different selector types
                if 'class_' in selector:
                    elem = soup.find(class_=selector['class_'])
                elif 'id' in selector:
                    elem = soup.find(id=selector['id'])
                elif 'tag' in selector and 'attrs' in selector:
                    elem = soup.find(selector['tag'], attrs=selector['attrs'])
                elif 'tag' in selector:
                    elem = soup.find(selector['tag'])
                else:
                    # Skip invalid selectors
                    continue

                if elem:
                    return TextProcessor.clean_html_text(elem.text)
            except Exception as e:
                logger.debug(f"Error with selector {selector}: {str(e)}")

        return None


# Backward compatibility functions
def clean_html_text(text: str) -> str:
    """Backward compatibility wrapper for TextProcessor.clean_html_text"""
    return TextProcessor.clean_html_text(text)


def extract_property_type(text: str) -> str:
    """Backward compatibility wrapper for TextProcessor.extract_property_type"""
    return TextProcessor.extract_property_type(text)


def clean_price(price_text: str) -> Tuple[str, str]:
    """Backward compatibility wrapper for TextProcessor.standardize_price"""
    return TextProcessor.standardize_price(price_text)


def extract_acreage(acreage_text: str) -> Tuple[str, str]:
    """Backward compatibility wrapper for TextProcessor.standardize_acreage"""
    return TextProcessor.standardize_acreage(acreage_text)
