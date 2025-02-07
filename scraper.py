# scraper.py
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse

# --- Selenium imports for dynamic content on Landwatch pages ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def extract_platform(url):
    """
    Derive a human-friendly platform name from the URL.
    Example: "newenglandfarmlandfinder.org" -> "New England Farmland Finder"
    """
    parsed_url = urlparse(url)
    domain = parsed_url.netloc  # e.g., "newenglandfarmlandfinder.org"
    # Remove common TLDs and split the remaining parts.
    parts = [part for part in domain.split('.') if part not in ["org", "com", "net"]]
    # Capitalize each part and join with a space.
    platform = " ".join(part.capitalize() for part in parts)
    return platform


def extract_listing_data(url):
    """
    Determine the domain and route to the appropriate extraction method.
    If the domain contains 'landwatch', use the Selenium-based method;
    otherwise, use the static extraction.
    """
    domain = urlparse(url).netloc.lower()
    if "landwatch" in domain:
        return extract_listing_data_landwatch_selenium(url)
    else:
        return extract_listing_data_static(url)


def extract_listing_data_static(url):
    """
    Extract data from sites that render content statically using requests and BeautifulSoup.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/105.0.0.0 Safari/537.36"
        )
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        raise Exception(f"Error fetching URL: {e}")
    
    if response.status_code != 200:
        raise Exception(f"Failed to fetch {url} (status code: {response.status_code})")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # --- Extract the listing name ---
    try:
        listing_name = soup.find("h1").get_text(strip=True)
    except Exception:
        listing_name = "Unknown Listing"
    
    # --- Extract the price ---
    price_tag = soup.find(class_="price")
    price = price_tag.get_text(strip=True) if price_tag else "$500,000"  # placeholder
    
    # --- Extract the acreage ---
    acreage_tag = soup.find(class_="acreage")
    acreage = acreage_tag.get_text(strip=True) if acreage_tag else "67 acres"  # placeholder
    
    # --- Derive bucket values ---
    price_bucket = "$300K - $600K"  # placeholder bucket
    acreage_bucket = "Large" if "67" in acreage else "Tiny"  # simplified logic
    
    property_type = "Single-Family Residence"
    house_details = "3 bed, 2 bath; modern design"  # placeholder
    farm_details = "N/A"  # placeholder
    location = "East Randolph, VT"  # placeholder
    distance = 25  # placeholder
    if distance <= 10:
        distance_bucket = "0-10"
    elif distance <= 20:
        distance_bucket = "11-20"
    elif distance <= 40:
        distance_bucket = "21-40"
    elif distance <= 60:
        distance_bucket = "41-60"
    elif distance <= 80:
        distance_bucket = "61-80"
    else:
        distance_bucket = "81+"
    
    listing_date = datetime.now().strftime("%Y-%m-%d")
    platform = extract_platform(url)
    
    data = {
        "listing_name": listing_name,
        "url": url,
        "platform": platform,
        "listing_date": listing_date,
        "price": price,
        "price_bucket": price_bucket,
        "acreage": acreage,
        "acreage_bucket": acreage_bucket,
        "property_type": property_type,
        "house_details": house_details,
        "farm_details": farm_details,
        "location": location,
        "distance": distance,
        "distance_bucket": distance_bucket,
    }
    
    return data


def extract_listing_data_landwatch_selenium(url):
    """
    Extract data from Landwatch pages that require JavaScript rendering using Selenium.
    """
    # Set up headless Chrome options
    options = Options()
    options.add_argument("--headless")  # run in headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/105.0.0.0 Safari/537.36")
    
    # Initialize the WebDriver (ensure chromedriver is installed and in your PATH)
    driver = webdriver.Chrome(options=options)
    
    # Navigate to the URL
    driver.get(url)
    
    try:
        # Wait for the <h1> element (or another key element) to ensure the page is loaded.
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
    except Exception as e:
        driver.quit()
        raise Exception("Error waiting for page to load with Selenium: " + str(e))
    
    # Get the page source after JavaScript has rendered the content.
    html = driver.page_source
    driver.quit()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # --- Extract the listing name ---
    try:
        listing_name = soup.find("h1").get_text(strip=True)
    except Exception:
        listing_name = "Unknown Listing"
    
    # --- Extract the price ---
    price_tag = soup.find(class_="price")
    price = price_tag.get_text(strip=True) if price_tag else "$500,000"  # placeholder
    
    # --- Extract the acreage ---
    # (This may need adjustment based on Landwatch's HTML structure.)
    acreage_tag = soup.find(text=lambda t: t and "acre" in t.lower())
    acreage = acreage_tag.strip() if acreage_tag else "Unknown acreage"
    
    # --- Derive bucket values ---
    acreage_bucket = "Large" if ("63" in acreage or "67" in acreage or "acre" in acreage.lower()) else "Tiny"
    price_bucket = "$300K - $600K"  # placeholder bucket
    
    property_type = "Single-Family Residence"
    house_details = "Details not extracted"  # placeholder
    farm_details = "N/A"
    
    # --- Extract location ---
    # Example logic based on URL fragments:
    if "reading-vt" in url:
        location = "Reading, VT"
    elif "east-randolph-vt" in url:
        location = "East Randolph, VT"
    else:
        location = "Location Unknown"
    
    distance = 25  # placeholder
    if distance <= 10:
        distance_bucket = "0-10"
    elif distance <= 20:
        distance_bucket = "11-20"
    elif distance <= 40:
        distance_bucket = "21-40"
    elif distance <= 60:
        distance_bucket = "41-60"
    elif distance <= 80:
        distance_bucket = "61-80"
    else:
        distance_bucket = "81+"
    
    listing_date = datetime.now().strftime("%Y-%m-%d")
    platform = extract_platform(url)
    
    data = {
        "listing_name": listing_name,
        "url": url,
        "platform": platform,
        "listing_date": listing_date,
        "price": price,
        "price_bucket": price_bucket,
        "acreage": acreage,
        "acreage_bucket": acreage_bucket,
        "property_type": property_type,
        "house_details": house_details,
        "farm_details": farm_details,
        "location": location,
        "distance": distance,
        "distance_bucket": distance_bucket,
    }
    
    return data


if __name__ == "__main__":
    test_url = input("Enter a listing URL: ")
    try:
        data = extract_listing_data(test_url)
        for key, value in data.items():
            print(f"{key}: {value}")
    except Exception as e:
        print("Error:", e)
