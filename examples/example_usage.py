# examples/example_usage.py
import json
import logging
from new_england_listings import process_listing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def main():
    # Example URLs for different platforms
    example_urls = [
        # Realtor.com example
        "https://www.realtor.com/realestateandhomes-detail/28-Vanderwerf-Dr_West-Bath_ME_04530_M36122-24566",

        # Land and Farm example
        "https://www.landandfarm.com/property/single-family-residence-cape-windham-me-36400823/",

        # Maine Farmland Trust example
        "https://farmlink.mainefarmlandtrust.org/individual-farm-listings/farm-id-3582"
    ]

    # Process each URL
    results = []
    errors = []

    for url in example_urls:
        try:
            # Process the listing
            print(f"\nProcessing: {url}")
            data = process_listing(url, use_notion=True)

            # Print some key information
            print(f"Found listing: {data['listing_name']}")
            print(f"Location: {data['location']}")
            if 'price' in data:
                print(f"Price: {data['price']} ({data['price_bucket']})")
            if 'acreage' in data:
                print(f"Acreage: {data['acreage']} ({data['acreage_bucket']})")

            results.append(data)

        except Exception as e:
            print(f"Error processing {url}: {str(e)}")
            errors.append({"url": url, "error": str(e)})

    # Save results to file
    output = {
        "results": results,
        "errors": errors,
        "total": len(example_urls),
        "successful": len(results),
        "failed": len(errors)
    }

    with open("example_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nProcessed {len(results)} listings successfully")
    print(f"Results saved to example_results.json")


if __name__ == "__main__":
    main()
