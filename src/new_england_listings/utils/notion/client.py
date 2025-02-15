# ./src/new_england_listings/utils/notion/client.py
"""Notion integration client for New England Listings."""

from typing import Dict, Any, Optional, List
import logging
import time
from datetime import datetime, timedelta
from notion_client import Client
from notion_client.errors import APIResponseError
from ...config.settings import NOTION_API_KEY, NOTION_DATABASE_ID, RATE_LIMIT

logger = logging.getLogger(__name__)


class NotionAPIError(Exception):
    """Custom exception for Notion API errors."""
    pass


class NotionClient:
    """Client for interacting with Notion API."""

    def __init__(self, api_key: Optional[str] = None, database_id: Optional[str] = None):
        """Initialize the Notion client."""
        self.api_key = api_key or NOTION_API_KEY
        self.database_id = database_id or NOTION_DATABASE_ID
        self.client = Client(auth=self.api_key)
        self._request_times: List[float] = []

    def _check_rate_limit(self):
        """Implement rate limiting based on settings."""
        now = time.time()
        window_start = now - RATE_LIMIT["per_seconds"]

        # Remove old requests from tracking
        self._request_times = [
            t for t in self._request_times if t > window_start]

        if len(self._request_times) >= RATE_LIMIT["max_requests"]:
            sleep_time = self._request_times[0] - window_start
            if sleep_time > 0:
                logger.warning(
                    f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)

        self._request_times.append(now)

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

    def create_entry(self, data: Dict[str, Any], update_if_exists: bool = True) -> Dict[str, Any]:
        """Create a new entry in the Notion database."""
        try:
            self._check_rate_limit()

            # Check for existing entry if URL is provided
            existing_id = None
            if "url" in data and update_if_exists:
                existing_id = self.find_existing_entry(data["url"])

            if existing_id and update_if_exists:
                logger.info(f"Updating existing entry: {existing_id}")
                return self.update_entry(existing_id, data)

            properties = self._format_properties(data)
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties
            )

            logger.info(f"Created Notion entry with ID: {response['id']}")
            return response

        except APIResponseError as e:
            logger.error(f"Notion API error: {str(e)}")
            raise NotionAPIError(str(e))
        except Exception as e:
            logger.error(f"Error creating Notion entry: {str(e)}")
            raise

    def update_entry(self, page_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing entry in the Notion database."""
        try:
            self._check_rate_limit()
            properties = self._format_properties(data)

            response = self.client.pages.update(
                page_id=page_id,
                properties=properties
            )

            logger.info(f"Updated Notion entry with ID: {page_id}")
            return response

        except APIResponseError as e:
            logger.error(f"Notion API error: {str(e)}")
            raise NotionAPIError(str(e))
        except Exception as e:
            logger.error(f"Error updating Notion entry: {str(e)}")
            raise

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

    def batch_create_entries(self, data_list: List[Dict[str, Any]],
                             update_if_exists: bool = True) -> List[Dict[str, Any]]:
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

        return {"successes": results, "errors": errors}

    def _format_properties(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format data into Notion properties structure."""
        properties = {}

        # [Previous property formatting code remains the same...]

        # Add last updated timestamp
        properties["Last Updated"] = {
            "date": {"start": datetime.now().isoformat()}
        }

        # URL
        if "url" in data:
            properties["URL"] = {"url": data["url"]}

        # Platform
        if "platform" in data:
            properties["Platform"] = {"select": {"name": data["platform"]}}

        # Listing Date
        if "listing_date" in data:
            properties["Listing Date"] = {
                "date": {"start": data["listing_date"]}
            }

        # Price and Price Bucket
        if "price" in data:
            properties["Price"] = {
                "rich_text": [{"text": {"content": data["price"]}}]
            }
        if "price_bucket" in data:
            properties["Price Bucket"] = {
                "select": {"name": data["price_bucket"]}
            }

        # Acreage and Acreage Bucket
        if "acreage" in data:
            properties["Acreage"] = {
                "rich_text": [{"text": {"content": data["acreage"]}}]
            }
        if "acreage_bucket" in data:
            properties["Acreage Bucket"] = {
                "select": {"name": data["acreage_bucket"]}
            }

        # Property Details
        if "property_type" in data:
            properties["Property Type"] = {
                "rich_text": [{"text": {"content": data["property_type"]}}]
            }
        if "house_details" in data:
            properties["House Details"] = {
                "rich_text": [{"text": {"content": data["house_details"]}}]
            }
        if "farm_details" in data:
            properties["Farm/Additional Details"] = {
                "rich_text": [{"text": {"content": data["farm_details"]}}]
            }

        # Location and Distance
        if "location" in data:
            properties["Location"] = {
                "rich_text": [{"text": {"content": data["location"]}}]
            }
        if "primary_city_distance" in data:
            properties["Distance to Portland (miles)"] = {
                "number": float(data["primary_city_distance"])
            }
        if "primary_city_distance_bucket" in data:
            properties["Distance Bucket"] = {
                "select": {"name": data["primary_city_distance_bucket"]}
            }

        # Additional Data
        if "town_population" in data:
            properties["Town Population"] = {
                "rich_text": [{"text": {"content": str(data["town_population"])}}]
            }
        if "town_population_bucket" in data:
            properties["Town Population Bucket"] = {
                "select": {"name": data["town_population_bucket"]}
            }

        # Last Updated
        properties["Last Updated"] = {
            "date": {"start": datetime.now().isoformat()}
        }

        return properties


# Create singleton instance AFTER the class definition
notion = NotionClient()


def create_notion_entry(data: Dict[str, Any], update_if_exists: bool = True) -> Dict[str, Any]:
    """
    Convenience function to create a Notion entry using the singleton client.
    
    Args:
        data: Dictionary containing the entry data
        update_if_exists: Whether to update existing entries with the same URL
        
    Returns:
        Dictionary containing the Notion API response
    """
    return notion.create_entry(data, update_if_exists=update_if_exists)
