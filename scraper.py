import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse

# Selenium-related imports for dynamic pages.
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
    parts = [part for part in domain.split('.') if part not in ["org", "com", "net"]]
    platform = " ".join(part.capitalize() for part in parts)
    return platform


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
    # Using BeautifulSoup's "string" argument instead of "text" to avoid deprecation warnings.
    acreage = "Unknown acreage"
    acreage_tag = soup.find(string=lambda s: s and "acre" in s.lower())
    if acreage_tag:
        acreage = acreage_tag.strip()
    
    # --- Derive bucket values for acreage ---
    acreage_bucket = "Large"
    try:
        number_match = re.search(r"([\d\.]+)", acreage)
        if number_match:
            acres = float(number_match.group(1))
            acreage_bucket = "Small" if acres < 1 else "Large"
    except Exception:
        pass
    
    price_bucket = "$300K - $600K"  # placeholder
    property_type = "Single-Family Residence"
    house_details = "Details not extracted"
    farm_details = "N/A"
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


def extract_listing_data_landwatch_selenium(url):
    """
    Extract data from Landwatch pages that require JavaScript rendering using Selenium.
    """
    # Set up headless Chrome options.
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/105.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
    except Exception as e:
        driver.quit()
        raise Exception("Error waiting for page to load with Selenium: " + str(e))
    
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
    price = price_tag.get_text(strip=True) if price_tag else "$500,000"
    
    # --- Extract the acreage ---
    # Try to find a string that contains "acre". Sometimes Landwatch includes JSON-LD data.
    acreage_value = "Unknown acreage"
    acreage_tag = soup.find(string=lambda s: s and "acre" in s.lower())
    if acreage_tag:
        try:
            parsed = json.loads(acreage_tag)
            if isinstance(parsed, dict) and "name" in parsed:
                acreage_value = parsed["name"]
            else:
                acreage_value = acreage_tag.strip()
        except json.JSONDecodeError:
            acreage_value = acreage_tag.strip()
    
    # --- Derive bucket values for acreage ---
    acreage_bucket = "Large"
    try:
        number_match = re.search(r"([\d\.]+)", acreage_value)
        if number_match:
            acres = float(number_match.group(1))
            acreage_bucket = "Small" if acres < 1 else "Large"
    except Exception:
        pass
    
    price_bucket = "$300K - $600K"
    property_type = "Single-Family Residence"
    house_details = "Details not extracted"
    farm_details = "N/A"
    
    # --- Extract location ---
    # Use URL hints or more sophisticated parsing as needed.
    if "reading-vt" in url:
        location = "Reading, VT"
    elif "east-randolph-vt" in url:
        location = "East Randolph, VT"
    elif "brunswick" in url or "bickford" in url:
        location = "Brunswick, ME"
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
        "acreage": acreage_value,
        "acreage_bucket": acreage_bucket,
        "property_type": property_type,
        "house_details": house_details,
        "farm_details": farm_details,
        "location": location,
        "distance": distance,
        "distance_bucket": distance_bucket,
    }
    
    return data


def extract_listing_data(url):
    """
    Routes the URL to the appropriate extraction method based on its domain.
    For Landwatch pages, use the Selenium-based extraction; for other sites, use the static method.
    """
    domain = urlparse(url).netloc.lower()
    if "landwatch" in domain:
        return extract_listing_data_landwatch_selenium(url)
    else:
        return extract_listing_data_static(url)


if __name__ == "__main__":
    test_url = input("Enter a listing URL: ")
    try:
        data = extract_listing_data(test_url)
        for key, value in data.items():
            print(f"{key}: {value}")
    except Exception as e:
        print("Error:", e)
