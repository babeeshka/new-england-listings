# src/new_england_listings/extractors/landandfarm.py
from typing import Dict, Any, Tuple
from bs4 import BeautifulSoup
import re
import logging
from .base import BaseExtractor
from ..utils.text import clean_price, extract_acreage
from ..utils.dates import extract_listing_date
from ..utils.geocoding import parse_location_from_url

logger = logging.getLogger(__name__)


class LandAndFarmExtractor(BaseExtractor):
    """Extractor for Land and Farm listings."""

    @property
    def platform_name(self) -> str:
        return "Land and Farm"

    def extract_listing_name(self) -> str:
        """Extract the listing name using multiple selectors."""
        title_selectors = [
            ("h1", {"class_": "title"}),
            ("h1", {"class_": "property-title"}),
            ("div", {"class_": "title"}),
            ("h1", {})
        ]

        for tag, attrs in title_selectors:
            title_elem = self.soup.find(tag, **attrs)
            if title_elem and title_elem.text.strip():
                return title_elem.text.strip()

        # Generate fallback name
        location = self.extract_location()
        acreage = self.extract_acreage_info()[0]
        if acreage and location != "Location Unknown":
            return f"{acreage} in {location}"
        return "Untitled Listing"

    def extract_price(self) -> Tuple[str, str]:
        """Extract price and determine price bucket."""
        price_elem = self.soup.find(class_="price")
        if price_elem:
            return clean_price(price_elem.text.strip())
        return "Contact for Price", "N/A"

    def extract_location(self) -> str:
        """Extract location information."""
        # Try page elements first
        location_elem = self.soup.find("div", class_="location") or \
            self.soup.find("p", class_="location")
        if location_elem:
            return location_elem.text.strip()

        # Try URL parsing
        url_location = parse_location_from_url(self.url)
        if url_location:
            return url_location

        return "Location Unknown"

    def extract_acreage_info(self) -> Tuple[str, str]:
        """Extract acreage and determine bucket."""
        details_section = self.soup.find("div", class_="details-info") or \
            self.soup.find("div", class_="property-details")

        if details_section:
            for item in details_section.find_all(['li', 'div', 'p']):
                text = item.get_text(strip=True)
                if 'acre' in text.lower():
                    return extract_acreage(text)

        # Look through all text if not found in details
        for text in self.soup.stripped_strings:
            if 'acre' in text.lower():
                return extract_acreage(text)

        return "Not specified", "Unknown"

    def extract_additional_data(self):
        """Extract additional platform-specific data."""
        # Add property type
        self.data["property_type"] = "Farm"

        # Extract farm-specific details
        if "mainefarmlandtrust.org" in self.url:
                # Maine Farmland Trust specific details
                farm_attributes = [
                    "soil-quality",
                    "water-resources",
                    "existing-infrastructure",
                    "farming-history",
                    "lease-terms",
                    "equipment-included"
                ]

                for attr in farm_attributes:
                    elem = self.soup.find(class_=attr) or self.soup.find(id=attr)
                    if elem:
                        self.data[attr.replace(
                            "-", "_")] = clean_html_text(elem.text)

                # Look for specific farm features
                farm_features = []
                features_section = self.soup.find(class_="farm-features")
                if features_section:
                    for feature in features_section.find_all("li"):
                        farm_features.append(clean_html_text(feature.text))
                if farm_features:
                    self.data["farm_features"] = farm_features

        # Extract acreage information
        acreage, acreage_bucket = self.extract_acreage_info()
        self.data["acreage"] = acreage
        self.data["acreage_bucket"] = acreage_bucket

        # Extract listing date
        self.data["listing_date"] = extract_listing_date(
            self.soup, self.platform_name
        )
