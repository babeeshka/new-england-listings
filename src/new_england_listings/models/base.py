# src/new_england_listings/models/base.py

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, validator, HttpUrl
from datetime import datetime
from enum import Enum


class PropertyType(str, Enum):
    SINGLE_FAMILY = "Single Family"
    FARM = "Farm"
    LAND = "Land"
    COMMERCIAL = "Commercial"
    UNKNOWN = "Unknown"


class PriceBucket(str, Enum):
    UNDER_300K = "Under $300K"
    TO_600K = "$300K - $600K"
    TO_900K = "$600K - $900K"
    TO_1_2M = "$900K - $1.2M"
    TO_1_5M = "$1.2M - $1.5M"
    TO_2M = "$1.5M - $2M"
    OVER_2M = "$2M+"
    NA = "N/A"


class AcreageBucket(str, Enum):
    TINY = "Tiny (Under 1 acre)"
    SMALL = "Small (1-5 acres)"
    MEDIUM = "Medium (5-20 acres)"
    LARGE = "Large (20-50 acres)"
    VERY_LARGE = "Very Large (50-100 acres)"
    EXTENSIVE = "Extensive (100+ acres)"
    UNKNOWN = "Unknown"


class DistanceBucket(str, Enum):
    UNDER_10 = "0-10"
    TO_20 = "11-20"
    TO_40 = "21-40"
    TO_60 = "41-60"
    TO_80 = "61-80"
    OVER_80 = "81+"


class SchoolRatingCategory(str, Enum):
    POOR = "Poor (0-3)"
    BELOW_AVERAGE = "Below Average (4-5)"
    AVERAGE = "Average (6-7)"
    ABOVE_AVERAGE = "Above Average (8-9)"
    EXCELLENT = "Excellent (10)"
    UNKNOWN = "Unknown"


class TownPopulationBucket(str, Enum):
    VERY_SMALL = "Very Small (Under 5K)"
    SMALL = "Small (5K-15K)"
    MEDIUM = "Medium (15K-50K)"
    LARGE = "Large (50K-100K)"
    VERY_LARGE = "Very Large (100K+)"
    UNKNOWN = "Unknown"


class PropertyListing(BaseModel):
    """Core property listing model with enhanced validation"""

    # Required fields
    url: HttpUrl
    platform: str
    listing_name: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)

    # Price information
    price: str = Field(..., min_length=1)
    price_bucket: PriceBucket

    # Property classification
    property_type: PropertyType = Field(default=PropertyType.UNKNOWN)

    # Size information
    acreage: str = Field(default="Not specified")
    acreage_bucket: AcreageBucket = Field(default=AcreageBucket.UNKNOWN)

    # Temporal information
    listing_date: Optional[datetime] = None
    last_updated: datetime = Field(default_factory=datetime.now)

    # Location metrics
    distance_to_portland: Optional[float] = Field(None, ge=0)
    portland_distance_bucket: Optional[DistanceBucket] = None
    town_population: Optional[int] = Field(None, ge=0)
    town_pop_bucket: Optional[TownPopulationBucket] = None

    # Educational metrics
    school_rating: Optional[float] = Field(None, ge=0, le=10)
    school_rating_cat: Optional[SchoolRatingCategory] = None
    school_district: Optional[str] = None

    # Healthcare metrics
    hospital_distance: Optional[float] = Field(None, ge=0)
    hospital_distance_bucket: Optional[DistanceBucket] = None
    closest_hospital: Optional[str] = None

    # Amenities
    restaurants_nearby: Optional[int] = Field(None, ge=0)
    grocery_stores_nearby: Optional[int] = Field(None, ge=0)
    other_amenities: Optional[str] = None

    # Property details
    house_details: Optional[str] = None
    farm_details: Optional[str] = None
    notes: Optional[str] = None

    # Raw data for debugging
    raw_data: Dict[str, Any] = Field(default_factory=dict)


    @field_validator('platform')
    def validate_platform(cls, v):
        valid_platforms = {
            "LandSearch",
            "Land and Farm",
            "Maine Farmland Trust",
            "New England Farmland Finder",
            "Realtor.com",
            "Zillow",  # Add Zillow as a valid platform
            "LandWatch"
        }
        if v not in valid_platforms:
            raise ValueError(f'Invalid platform: {v}')
        return v

    @field_validator('price')
    def validate_price(cls, v):
        if not v:
            return "Contact for Price"
        if v.lower() == "contact for price":
            return v
        if not any(c.isdigit() for c in v):
            raise ValueError(
                'Price must contain numbers or be "Contact for Price"')
        return v

    @field_validator('school_rating')
    def validate_school_rating(cls, v):
        if v is not None and (v < 0 or v > 10):
            raise ValueError('School rating must be between 0 and 10')
        return v

    @field_validator('distance_to_portland')
    def validate_distance(cls, v):
        if v is not None and v < 0:
            raise ValueError('Distance cannot be negative')
        return v

    class Config:
        use_enum_values = True
