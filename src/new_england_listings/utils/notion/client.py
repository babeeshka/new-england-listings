# src/new_england_listings/utils/notion/client.py

from typing import Dict, Any, Optional, List, Union
import logging
import time
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from notion_client import Client
from notion_client.errors import APIResponseError
from pydantic import ValidationError
from ...config.settings import NOTION_API_KEY, NOTION_DATABASE_ID, RATE_LIMIT
from ...models.base import PropertyListing

logger = logging.getLogger(__name__)


class NotionAPIError(Exception):
    """Custom exception for Notion API errors."""
    pass


class NotionClient:
    """Client for interacting with Notion API with enhanced data validation."""

    def __init__(self, api_key: Optional[str] = None, database_id: Optional[str] = None):
        self.api_key = api_key or NOTION_API_KEY
        self.database_id = database_id or NOTION_DATABASE_ID
        self.client = Client(auth=self.api_key)
        self._request_times: List[float] = []

    def _check_rate_limit(self):
        """Implement rate limiting based on settings."""
        now = time.time()
        window_start = now - RATE_LIMIT["per_seconds"]
        self._request_times = [
            t for t in self._request_times if t > window_start]

        if len(self._request_times) >= RATE_LIMIT["max_requests"]:
            sleep_time = self._request_times[0] - window_start
            if sleep_time > 0:
                logger.warning(
                    f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)

        self._request_times.append(now)

    def _validate_data(self, data: Dict[str, Any]) -> PropertyListing:
        """Validate data against PropertyListing model."""
        try:
            if isinstance(data, PropertyListing):
                return data
            return PropertyListing(**data)
        except ValidationError as e:
            logger.error(f"Data validation failed: {str(e)}")
            raise

    def _format_properties(self, data: Union[Dict[str, Any], PropertyListing]) -> Dict[str, Any]:
        """Format validated data into Notion properties structure with correct field types."""
        if isinstance(data, dict):
            validated_data = self._validate_data(data)
        else:
            validated_data = data

        properties = {
            # Basic Information
            "Listing Name": {
                "title": [{"text": {"content": truncate_text(validated_data.listing_name, 2000)}}]
            },
            "URL": {"url": str(validated_data.url)},
            "Platform": {"rich_text": [{"text": {"content": validated_data.platform}}]},
            "Location": {
                "rich_text": [{"text": {"content": truncate_text(validated_data.location, 2000)}}]
            },

            # Price Information
            "Price": {
                "number": parse_price_to_number(validated_data.price)
            },
            "Price Bucket": {
                "rich_text": [{"text": {"content": validated_data.price_bucket}}]
            },

            # Property Classification
            "Property Type": {
                "rich_text": [{"text": {"content": validated_data.property_type}}]
            },
            "Acreage": {
                "number": parse_acreage_to_number(validated_data.acreage)
            },
            "Acreage Bucket": {
                "rich_text": [{"text": {"content": validated_data.acreage_bucket}}]
            },

            # Dates
            "Last Updated": {
                "date": {"start": format_notion_date()}
            }
        }


        # Optional fields with proper typing
        if validated_data.listing_date:
            # Convert to the correct timezone before formatting
            eastern = ZoneInfo("America/New_York")
            listing_date_eastern = validated_data.listing_date.replace(
                tzinfo=timezone.utc).astimezone(eastern)
            properties["Listing Date"] = {
                "date": {"start": listing_date_eastern.isoformat()}
    }

        # Location Metrics (as numbers)
        if validated_data.distance_to_portland is not None:
            properties["Distance to Portland (miles)"] = {
                "number": float(validated_data.distance_to_portland)
            }
            properties["Portland Distance Bucket"] = {
                "rich_text": [{"text": {"content": validated_data.portland_distance_bucket}}]
            }

        if validated_data.town_population is not None:
            properties["Town Population"] = {
                "number": int(validated_data.town_population)
            }
            properties["Town Pop. Bucket"] = {
                "rich_text": [{"text": {"content": validated_data.town_pop_bucket}}]
            }

        # Educational Metrics
        if validated_data.school_rating is not None:
            properties["School Rating"] = {
                "number": float(validated_data.school_rating)
            }
            properties["School Rating Cat."] = {
                "rich_text": [{"text": {"content": validated_data.school_rating_cat}}]
            }
        if validated_data.school_district:
            properties["School District"] = {
                "rich_text": [{"text": {"content": truncate_text(validated_data.school_district, 2000)}}]
            }

        # Healthcare Metrics
        if validated_data.hospital_distance is not None:
            properties["Hospital Distance (miles)"] = {
                "number": float(validated_data.hospital_distance)
            }
            properties["Hospital Distance Bucket"] = {
                "rich_text": [{"text": {"content": validated_data.hospital_distance_bucket}}]
            }
        if validated_data.closest_hospital:
            properties["Closest Hospital"] = {
                "rich_text": [{"text": {"content": truncate_text(validated_data.closest_hospital, 2000)}}]
            }

        # Amenities (as numbers where appropriate)
        if validated_data.restaurants_nearby is not None:
            properties["Restaurants Nearby"] = {
                "number": int(validated_data.restaurants_nearby)
            }
        if validated_data.grocery_stores_nearby is not None:
            properties["Grocery Stores Nearby"] = {
                "number": int(validated_data.grocery_stores_nearby)
            }
        if validated_data.other_amenities:
            properties["Other Amenities"] = {
                "rich_text": [{"text": {"content": truncate_text(validated_data.other_amenities, 2000)}}]
            }

        # Property Details
        detail_fields = [
            ("house_details", "House Details"),
            ("farm_details", "Farm/Additional Details"),
            ("notes", "Notes")
        ]

        for field, notion_name in detail_fields:
            value = getattr(validated_data, field, None)
            if value:
                properties[notion_name] = {
                    "rich_text": [{"text": {"content": truncate_text(str(value), 2000)}}]
                }

        return properties

    def find_existing_entry(self, url: str) -> Optional[str]:
        """Find an existing entry by URL."""
        try:
            self._check_rate_limit()
            response = self.client.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "URL",
                    "url": {
                        "equals": url
                    }
                }
            )

            if response["results"]:
                return response["results"][0]["id"]
            return None

        except Exception as e:
            logger.error(f"Error searching for existing entry: {str(e)}")
            return None

    def create_entry(self, data: Union[Dict[str, Any], PropertyListing], update_if_exists: bool = True) -> Dict[str, Any]:
        """Create a new entry in the Notion database with validation."""
        try:
            self._check_rate_limit()

            # Validate data first
            validated_data = self._validate_data(
                data) if isinstance(data, dict) else data

            # Check for existing entry
            existing_id = None
            if update_if_exists:
                existing_id = self.find_existing_entry(str(validated_data.url))

            if existing_id and update_if_exists:
                logger.info(f"Updating existing entry: {existing_id}")
                return self.update_entry(existing_id, validated_data)

            properties = self._format_properties(validated_data)
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties
            )

            logger.info(f"Created Notion entry with ID: {response['id']}")
            return response

        except ValidationError as e:
            logger.error(f"Data validation error: {str(e)}")
            raise
        except APIResponseError as e:
            logger.error(f"Notion API error: {str(e)}")
            raise NotionAPIError(str(e))
        except Exception as e:
            logger.error(f"Error creating Notion entry: {str(e)}")
            raise

    def update_entry(self, page_id: str, data: Union[Dict[str, Any], PropertyListing]) -> Dict[str, Any]:
        """Update an existing entry with validation."""
        try:
            self._check_rate_limit()
            validated_data = self._validate_data(
                data) if isinstance(data, dict) else data
            properties = self._format_properties(validated_data)

            response = self.client.pages.update(
                page_id=page_id,
                properties=properties
            )

            logger.info(f"Updated Notion entry with ID: {page_id}")
            return response

        except ValidationError as e:
            logger.error(f"Data validation error: {str(e)}")
            raise
        except APIResponseError as e:
            logger.error(f"Notion API error: {str(e)}")
            raise NotionAPIError(str(e))
        except Exception as e:
            logger.error(f"Error updating Notion entry: {str(e)}")
            raise

    def batch_create_entries(self, data_list: List[Union[Dict[str, Any], PropertyListing]],
                             update_if_exists: bool = True) -> Dict[str, Any]:
        """Create multiple entries in batch."""
        results = []
        errors = []

        for data in data_list:
            try:
                result = self.create_entry(data, update_if_exists)
                results.append(result)
            except Exception as e:
                errors.append({"data": data, "error": str(e)})
                logger.error(f"Error in batch creation: {str(e)}")

        if errors:
            logger.warning(
                f"Batch creation completed with {len(errors)} errors")

        return {
            "successes": results,
            "errors": errors,
            "total_processed": len(data_list),
            "successful": len(results),
            "failed": len(errors)
        }

    def archive_entry(self, page_id: str) -> Dict[str, Any]:
        """Archive a Notion entry."""
        try:
            self._check_rate_limit()
            response = self.client.pages.update(
                page_id=page_id,
                archived=True
            )

            logger.info(f"Archived Notion entry with ID: {page_id}")
            return response

        except APIResponseError as e:
            logger.error(f"Notion API error: {str(e)}")
            raise NotionAPIError(str(e))
        except Exception as e:
            logger.error(f"Error archiving Notion entry: {str(e)}")
            raise


# Create singleton instance
notion = NotionClient()

def truncate_text(text: str, max_length: int = 2000) -> str:
    """Truncate text to max_length characters, adding ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def parse_price_to_number(price_text: str) -> Optional[float]:
    """Convert price text to number for Notion."""
    if not price_text or price_text in ["Contact for Price", "N/A"]:
        return None

    try:
        # Remove $ and commas
        clean_price = price_text.replace('$', '').replace(',', '')

        # Handle "1.5M" format
        if 'M' in clean_price:
            clean_price = clean_price.replace('M', '')
            return float(clean_price) * 1000000

        return float(clean_price)
    except (ValueError, TypeError):
        return None

def parse_acreage_to_number(acreage_text: str) -> Optional[float]:
    """Convert acreage text to number for Notion."""
    if not acreage_text or acreage_text in ["Not specified", "Unknown"]:
        return None

    try:
        # Extract number before "acres"
        match = re.search(r'([\d.]+)', acreage_text)
        if match:
            return float(match.group(1))
        return None
    except (ValueError, TypeError):
        return None

def format_notion_date(dt=None):
    """Format a datetime for Notion API with timezone adjustment for Eastern Time."""
    if dt is None:
        dt = datetime.now()

    # Convert to Eastern Time
    eastern = ZoneInfo("America/New_York")  # Florida is in Eastern Time
    dt_eastern = dt.astimezone(eastern)

    # Format for Notion (ISO format)
    return dt_eastern.isoformat()

async def create_notion_entry(data: Union[Dict[str, Any], PropertyListing], update_if_exists: bool = True) -> Dict[str, Any]:
    """
    Asynchronous convenience function to create a Notion entry using the singleton client.
    
    Args:
        data: Dictionary or PropertyListing containing the entry data
        update_if_exists: Whether to update existing entries with the same URL
        
    Returns:
        Dictionary containing the Notion API response
    """
    return notion.create_entry(data, update_if_exists=update_if_exists)

def create_notion_entry(data: Union[Dict[str, Any], PropertyListing], update_if_exists: bool = True) -> Dict[str, Any]:
    """
    Convenience function to create a Notion entry using the singleton client.
    
    Args:
        data: Dictionary or PropertyListing containing the entry data
        update_if_exists: Whether to update existing entries with the same URL
        
    Returns:
        Dictionary containing the Notion API response
    """
    return notion.create_entry(data, update_if_exists=update_if_exists)
