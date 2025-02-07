# notion_integration.py
from notion_client import Client

# Replace these with your actual integration token and database ID.
NOTION_API_KEY = "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"
DATABASE_ID = "1934ddf6dc1a8034bb36e2d9f751dc29"

# Initialize the Notion client.
notion = Client(auth=NOTION_API_KEY)

def create_notion_entry(data):
    """
    Create a new page in your Notion database using the provided data dictionary.
    The keys in the data dictionary should match the property mapping below.
    """
    new_page = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Listing Name": {
                "title": [{"text": {"content": data["listing_name"]}}]
            },
            "URL": {
                "url": data["url"]
            },
            "Platform": {
                "select": {"name": data["platform"]}
            },
            "Listing Date": {
                "rich_text": [{"text": {"content": data["listing_date"]}}]
            },
            "Price": {
                "rich_text": [{"text": {"content": data["price"]}}]
            },
            "Price Bucket": {
                "rich_text": [{"text": {"content": data["price_bucket"]}}]
            },
            "Acreage": {
                "rich_text": [{"text": {"content": data["acreage"]}}]
            },
            "Acreage Bucket": {
                "select": {"name": data["acreage_bucket"]}
            },
            "Property Type": {
                "rich_text": [{"text": {"content": data["property_type"]}}]
            },
            "House Details": {
                "rich_text": [{"text": {"content": data["house_details"]}}]
            },
            "Farm/Additional Details": {
                "rich_text": [{"text": {"content": data["farm_details"]}}]
            },
            "Location": {
                "rich_text": [{"text": {"content": data["location"]}}]
            },
            "Distance to Portland (miles)": {
                "rich_text": [{"text": {"content": str(data["distance"])}}]
            },
            # "Distance Bucket" is removed since it does not exist in your database.
        },
    }
    response = notion.pages.create(**new_page)
    return response

# For testing ad hoc:
if __name__ == "__main__":
    # Example data dictionary; in practice, pass in your scraped data.
    example_data = {
        "listing_name": "Test Listing",
        "url": "https://example.com/listing",
        "platform": "Example Platform",
        "listing_date": "2025-01-01",
        "price": "$500,000",
        "price_bucket": "$300K - $600K",
        "acreage": "2 acres",
        "acreage_bucket": "Tiny",
        "property_type": "Single-Family Residence",
        "house_details": "3 bed, 2 bath; modern design",
        "farm_details": "N/A",
        "location": "Example Town, ME",
        "distance": 25,
    }
    try:
        result = create_notion_entry(example_data)
        print("New Notion entry created with ID:", result.get("id"))
    except Exception as e:
        print("Error creating Notion entry:", e)
