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

    def _extract_region(self, location: str) -> Optional[str]:
        """Extract region from location string for all New England states."""
        if not location or location == "Location Unknown":
            return None

        # Extract state
        state_match = re.search(r',\s*([A-Z]{2})', location)
        if not state_match:
            return None

        state = state_match.group(1)

        # Define regions for all New England states
        regions = {
            "ME": {
                "Southern Maine": ["Portland", "Biddeford", "Saco", "York", "Kennebunk", "Kittery", "Wells", "Cumberland"],
                "Central Maine": ["Augusta", "Lewiston", "Auburn", "Turner", "Waterville", "Farmington"],
                "Coastal Maine": ["Brunswick", "Bath", "Rockland", "Camden", "Boothbay", "Bar Harbor", "Phippsburg"],
                "Western Maine": ["Bethel", "Rumford", "Norway", "Fryeburg", "Bridgton"],
                "Northern Maine": ["Bangor", "Orono", "Presque Isle", "Caribou", "Houlton"]
            },
            "NH": {
                "Seacoast NH": ["Portsmouth", "Dover", "Durham", "Hampton", "Exeter", "Rye"],
                "White Mountains": ["North Conway", "Jackson", "Bartlett", "Lincoln", "Franconia"],
                "Lakes Region NH": ["Laconia", "Meredith", "Wolfeboro", "Alton", "Gilford"],
                "Southern NH": ["Nashua", "Manchester", "Concord", "Salem", "Bedford", "Derry"]
            },
            "VT": {
                "Northeast Kingdom": ["St. Johnsbury", "Newport", "Lyndonville", "Burke"],
                "Central Vermont": ["Montpelier", "Barre", "Waterbury", "Stowe", "Middlebury"],
                "Southern Vermont": ["Brattleboro", "Bennington", "Manchester", "Rutland"],
                "Northwest Vermont": ["Burlington", "Essex", "St. Albans", "Colchester"]
            },
            "MA": {
                "Boston Area": ["Boston", "Cambridge", "Somerville", "Brookline", "Newton"],
                "South Shore MA": ["Quincy", "Braintree", "Hingham", "Plymouth", "Duxbury"],
                "North Shore MA": ["Salem", "Beverly", "Gloucester", "Newburyport", "Ipswich"],
                "Western MA": ["Springfield", "Northampton", "Amherst", "Pittsfield", "Great Barrington"],
                "Cape Cod": ["Barnstable", "Falmouth", "Chatham", "Provincetown", "Hyannis"]
            },
            "CT": {
                "Fairfield County": ["Stamford", "Greenwich", "Norwalk", "Bridgeport", "Westport"],
                "New Haven Area": ["New Haven", "Hamden", "Guilford", "Madison", "Branford"],
                "Hartford Area": ["Hartford", "West Hartford", "Glastonbury", "Farmington"],
                "Eastern CT": ["Mystic", "New London", "Stonington", "Norwich", "Groton"]
            },
            "RI": {
                "Providence Area": ["Providence", "Cranston", "Warwick", "East Providence"],
                "South County": ["Narragansett", "South Kingstown", "Westerly", "Charlestown"],
                "East Bay": ["Newport", "Bristol", "Barrington", "Middletown"],
                "Northern RI": ["Woonsocket", "Cumberland", "Lincoln", "Smithfield"]
            }
        }

        if state in regions:
            for region, cities in regions[state].items():
                if any(city in location for city in cities):
                    return region

        # Default regions by state
        state_regions = {
            "ME": "Maine",
            "NH": "New Hampshire",
            "VT": "Vermont",
            "MA": "Massachusetts",
            "CT": "Connecticut",
            "RI": "Rhode Island"
        }
        return state_regions.get(state)

    def _format_properties(self, data: Union[Dict[str, Any], PropertyListing]) -> Dict[str, Any]:
        """Format validated data to match the Notion database with select fields."""
        if isinstance(data, dict):
            validated_data = self._validate_data(data)
        else:
            validated_data = data

        # Ensure all values have fallbacks for None
        def safe_str(value):
            """Safely convert value to string, handling None values."""
            return str(value) if value is not None else ""

        properties = {
            # Basic Information - preserving title for listing name
            "Listing Name": {
                "title": [{"text": {"content": truncate_text(validated_data.listing_name, 2000)}}]
            },
            "URL": {"url": str(validated_data.url)},

            # Use select for categorization fields (previously rich_text)
            "Platform": {
                "select": {
                    "name": safe_str(validated_data.platform)
                }
            },
            "Location": {
                "rich_text": [{"text": {"content": truncate_text(safe_str(validated_data.location), 2000)}}]
            },

            # Price Information
            "Price": {
                "number": parse_price_to_number(validated_data.price)
            },
            "Price Bucket": {
                "select": {
                    "name": safe_str(validated_data.price_bucket)
                }
            },

            # Property Classification - using select
            "Property Type": {
                "select": {
                    "name": safe_str(validated_data.property_type)
                }
            },
            "Acreage": {
                "number": parse_acreage_to_number(validated_data.acreage)
            },
            "Acreage Bucket": {
                "select": {
                    "name": safe_str(validated_data.acreage_bucket)
                }
            },

            # Dates - using rich_text for Last Updated as expected by database
            "Last Updated": {
                "rich_text": [{"text": {"content": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}}]
            }
        }

        # Optional fields with proper typing
        if validated_data.listing_date:
            # Format date as text since we're using rich_text for dates
            if isinstance(validated_data.listing_date, datetime):
                date_str = validated_data.listing_date.strftime("%Y-%m-%d")
            else:
                date_str = safe_str(validated_data.listing_date)

            properties["Listing Date"] = {
                "rich_text": [{"text": {"content": date_str}}]
            }

        # Location Metrics (as numbers)
        if validated_data.distance_to_portland is not None:
            properties["Distance to Portland (miles)"] = {
                "number": float(validated_data.distance_to_portland)
            }
            properties["Portland Distance Bucket"] = {
                "select": {  # Changed from rich_text to select
                    "name": safe_str(validated_data.portland_distance_bucket)
                }
            }

        if validated_data.town_population is not None:
            properties["Town Population"] = {
                "number": int(validated_data.town_population)
            }
            properties["Town Pop. Bucket"] = {
                "select": {  # Changed from rich_text to select
                    "name": safe_str(validated_data.town_pop_bucket)
                }
            }

        # Educational Metrics
        if validated_data.school_rating is not None:
            properties["School Rating"] = {
                "number": float(validated_data.school_rating)
            }
            properties["School Rating Cat."] = {
                "select": {  # Changed from rich_text to select
                    "name": safe_str(validated_data.school_rating_cat)
                }
            }
        if validated_data.school_district:
            properties["School District"] = {
                "rich_text": [{"text": {"content": truncate_text(safe_str(validated_data.school_district), 2000)}}]
            }

        # Healthcare Metrics
        if validated_data.hospital_distance is not None:
            properties["Hospital Distance (miles)"] = {
                "number": float(validated_data.hospital_distance)
            }
            properties["Hospital Distance Bucket"] = {
                "select": {  # Changed from rich_text to select
                    "name": safe_str(validated_data.hospital_distance_bucket)
                }
            }
        if validated_data.closest_hospital:
            properties["Closest Hospital"] = {
                "rich_text": [{"text": {"content": truncate_text(safe_str(validated_data.closest_hospital), 2000)}}]
            }

        # Fix for Other Amenities - using multi_select as expected by database
        if validated_data.other_amenities:
            # Split by pipe and create multi-select options
            amenities_list = [a.strip() for a in safe_str(
                validated_data.other_amenities).split('|') if a.strip()]
            properties["Other Amenities"] = {
                "multi_select": [{"name": amenity} for amenity in amenities_list[:100]]
            }

        # Use number type for numeric amenities
        if validated_data.restaurants_nearby is not None:
            properties["Restaurants Nearby"] = {
                "number": int(validated_data.restaurants_nearby)
            }
        if validated_data.grocery_stores_nearby is not None:
            properties["Grocery Stores Nearby"] = {
                "number": int(validated_data.grocery_stores_nearby)
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
                    "rich_text": [{"text": {"content": truncate_text(safe_str(value), 2000)}}]
                }

        # Add optional status, region, and favorite fields if they exist in your database
        # Include these only if you've added them to your Notion database
        try:
            # Extract region
            region = self._extract_region(validated_data.location)
            if region:
                properties["Region"] = {
                    "select": {
                        "name": region
                    }
                }

            # Set default status for new entries
            properties["Status"] = {
                "select": {
                    "name": "New"
                }
            }

            # Set default favorite status
            properties["Favorite"] = {
                "checkbox": False
            }
        except Exception as e:
            # If these properties don't exist, we'll just ignore them
            logger.debug(f"Optional properties not set: {str(e)}")

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
    """Convert price text to number with enhanced parsing."""
    if not price_text or isinstance(price_text, str) and price_text.lower() in ["contact for price", "n/a"]:
        return None

    try:
        # Handle K notation
        if 'K' in price_text:
            clean_price = price_text.replace(
                '$', '').replace(',', '').replace('K', '')
            return float(clean_price) * 1000

        # Handle million notation
        if 'M' in price_text:
            clean_price = price_text.replace(
                '$', '').replace(',', '').replace('M', '')
            return float(clean_price) * 1000000

        # Remove $ and commas
        clean_price = price_text.replace('$', '').replace(',', '')

        # Try to convert to float
        try:
            return float(clean_price)
        except ValueError:
            # Additional fallback for numeric extraction
            match = re.search(r'(\d+(?:\.\d+)?)', clean_price)
            if match:
                return float(match.group(1))
            return None
    except Exception as e:
        logger.warning(f"Error parsing price '{price_text}': {e}")
        return None


def parse_acreage_to_number(acreage_text: str) -> Optional[float]:
    """Convert acreage text to number with enhanced parsing."""
    if not acreage_text or acreage_text.lower() in ["not specified", "unknown"]:
        return None

    try:
        # Handle common patterns
        acre_match = re.search(
            r'(\d+(?:\.\d+)?)\s*acres?', acreage_text.lower())
        if acre_match:
            return float(acre_match.group(1))

        # Fallback to any numeric extraction
        match = re.search(r'(\d+(?:\.\d+)?)', acreage_text)
        if match:
            return float(match.group(1))

        return None
    except Exception as e:
        logger.warning(f"Error parsing acreage '{acreage_text}': {e}")
        return None


def format_notion_date(dt=None):
    """Format a datetime for Notion API with timezone adjustment for Eastern Time."""
    if dt is None:
        dt = datetime.now()

    # Convert to Eastern Time
    eastern = ZoneInfo("America/New_York")
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
