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
    # Maine Cities
    "Portland, ME": {
        "coordinates": (43.6591, -70.2568),
        "population": 66882,
        "amenities": ["Airport", "Seaport", "Universities", "Hospital", "Arts District"],
        "state": "ME",
        "school_rating": 7
    },
    "Augusta, ME": {
        "coordinates": (44.3107, -69.7795),
        "population": 18899,
        "amenities": ["State Capital", "Hospital", "Government Center"],
        "state": "ME",
        "school_rating": 6
    },
    "Bangor, ME": {
        "coordinates": (44.8016, -68.7712),
        "population": 31903,
        "amenities": ["Airport", "Hospital", "University", "Shopping Mall"],
        "state": "ME",
        "school_rating": 7
    },
    "Lewiston, ME": {
        "coordinates": (44.1003, -70.2147),
        "population": 36592,
        "amenities": ["Hospital", "Bates College", "Arts Center"],
        "state": "ME",
        "school_rating": 6
    },

    # New Hampshire Cities
    "Manchester, NH": {
        "coordinates": (42.9956, -71.4548),
        "population": 112673,
        "amenities": ["Airport", "Hospital", "Shopping Mall", "Universities"],
        "state": "NH",
        "school_rating": 7
    },
    "Concord, NH": {
        "coordinates": (43.2081, -71.5376),
        "population": 43976,
        "amenities": ["State Capital", "Hospital", "Cultural Center"],
        "state": "NH",
        "school_rating": 8
    },
    "Nashua, NH": {
        "coordinates": (42.7654, -71.4676),
        "population": 89355,
        "amenities": ["Hospital", "Shopping Centers", "Parks"],
        "state": "NH",
        "school_rating": 8
    },
    "Portsmouth, NH": {
        "coordinates": (43.0718, -70.7626),
        "population": 21956,
        "amenities": ["Seaport", "Historic District", "Hospital"],
        "state": "NH",
        "school_rating": 9
    },

    # Vermont Cities
    "Burlington, VT": {
        "coordinates": (44.4759, -73.2121),
        "population": 42819,
        "amenities": ["University", "Lake Champlain", "Hospital", "Airport"],
        "state": "VT",
        "school_rating": 8
    },
    "Montpelier, VT": {
        "coordinates": (44.2601, -72.5754),
        "population": 7855,
        "amenities": ["State Capital", "Hospital", "Arts Center"],
        "state": "VT",
        "school_rating": 8
    },
    "Rutland, VT": {
        "coordinates": (43.6106, -72.9726),
        "population": 15807,
        "amenities": ["Hospital", "Shopping Center", "Ski Areas Nearby"],
        "state": "VT",
        "school_rating": 7
    },
    "Brattleboro, VT": {
        "coordinates": (42.8509, -72.5579),
        "population": 11765,
        "amenities": ["Hospital", "Arts Community", "Farmers Market"],
        "state": "VT",
        "school_rating": 7
    },

    # Massachusetts Cities
    "Boston, MA": {
        "coordinates": (42.3601, -71.0589),
        "population": 675647,
        "amenities": ["Major Airport", "Universities", "Hospitals", "Seaport"],
        "state": "MA",
        "school_rating": 8
    },
    "Worcester, MA": {
        "coordinates": (42.2626, -71.8023),
        "population": 185428,
        "amenities": ["Universities", "Hospital", "Cultural Center"],
        "state": "MA",
        "school_rating": 7
    },
    "Springfield, MA": {
        "coordinates": (42.1015, -72.5898),
        "population": 155929,
        "amenities": ["Hospital", "Universities", "Museums"],
        "state": "MA",
        "school_rating": 6
    },
    "Pittsfield, MA": {
        "coordinates": (42.4501, -73.2567),
        "population": 42931,
        "amenities": ["Hospital", "Cultural District", "Berkshires"],
        "state": "MA",
        "school_rating": 7
    },

    # Additional Important Towns
    "Stowe, VT": {
        "coordinates": (44.4654, -72.6874),
        "population": 4314,
        "amenities": ["Ski Resort", "Tourist Destination", "Medical Center"],
        "state": "VT",
        "school_rating": 9
    },
    "North Conway, NH": {
        "coordinates": (44.0537, -71.1284),
        "population": 2349,
        "amenities": ["Ski Areas", "Shopping Outlets", "Medical Center"],
        "state": "NH",
        "school_rating": 7
    },
    "Bar Harbor, ME": {
        "coordinates": (44.3876, -68.2039),
        "population": 5515,
        "amenities": ["Acadia National Park", "Hospital", "Tourist Destination"],
        "state": "ME",
        "school_rating": 8
    },
    "Northampton, MA": {
        "coordinates": (42.3251, -72.6412),
        "population": 28451,
        "amenities": ["Smith College", "Arts Community", "Hospital"],
        "state": "MA",
        "school_rating": 8
    }
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
