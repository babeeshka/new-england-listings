# src/new_england_listings/config/constants.py

from typing import Dict, Tuple, List

# Price categorization with more granular buckets
PRICE_BUCKETS: Dict[int, str] = {
    0: "Under $300K",
    300000: "$300K - $600K",
    600000: "$600K - $900K",
    900000: "$900K - $1.2M",
    1200000: "$1.2M - $1.5M",
    1500000: "$1.5M - $2M",
    2000000: "$2M+"
}

# Acreage categorization with more specific ranges
ACREAGE_BUCKETS: Dict[float, str] = {
    0: "Tiny (Under 1 acre)",
    1: "Small (1-5 acres)",
    5: "Medium (5-20 acres)",
    20: "Large (20-50 acres)",
    50: "Very Large (50-100 acres)",
    100: "Extensive (100+ acres)"
}

# Distance categorization
DISTANCE_BUCKETS: Dict[int, str] = {
    0: "0-10",
    11: "11-20",
    21: "21-40",
    41: "41-60",
    61: "61-80",
    81: "81+"
}

# Population categorization
POPULATION_BUCKETS: Dict[int, str] = {
    0: "Very Small (Under 5K)",
    5000: "Small (5K-15K)",
    15000: "Medium (15K-50K)",
    50000: "Large (50K-100K)",
    100000: "Very Large (100K+)"
}

# School rating categorization
SCHOOL_RATING_BUCKETS: Dict[int, str] = {
    0: "Poor (0-3)",
    4: "Below Average (4-5)",
    6: "Average (6-7)",
    8: "Above Average (8-9)",
    10: "Excellent (10)"
}

# Major cities in New England with their coordinates and additional metadata
MAJOR_CITIES: Dict[str, Dict[str, any]] = {
    "Portland, ME": {
        "coordinates": (43.6591, -70.2568),
        "population": 66882,
        "amenities": ["Airport", "Seaport", "Universities"],
        "state": "ME"
    },
    "Augusta, ME": {
        "coordinates": (44.3107, -69.7795),
        "population": 18899,
        "amenities": ["State Capital", "Hospital"],
        "state": "ME"
    },
    "Burlington, VT": {
        "coordinates": (44.4759, -73.2121),
        "population": 42819,
        "amenities": ["University", "Lake Champlain"],
        "state": "VT"
    },
    # Add more cities with detailed information...
}

# Extended date patterns including relative dates
DATE_PATTERNS: List[Tuple[str, str]] = [
    # Standard date formats
    (r'(\d{1,2})/(\d{1,2})/(\d{4})', '%m/%d/%Y'),
    (r'(\d{4})-(\d{2})-(\d{2})', '%Y-%m-%d'),
    (r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', '%B %d %Y'),
    (r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', '%d %B %Y'),
    # Relative date patterns (handled separately in code)
    (r'(\d+)\s+days?\s+ago', '%d days ago'),
    (r'(\d+)\s+weeks?\s+ago', '%d weeks ago'),
    (r'(\d+)\s+months?\s+ago', '%d months ago'),
    (r'(\d+)\s+years?\s+ago', '%d years ago')
]

# Supported platforms and their domains
PLATFORMS: Dict[str, str] = {
    "realtor.com": "Realtor.com",
    "landsearch.com": "LandSearch",
    "landandfarm.com": "Land and Farm",
    "newenglandfarmlandfinder.org": "New England Farmland Finder",
    "mainefarmlandtrust.org": "Maine Farmland Trust"
}
