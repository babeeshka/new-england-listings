# New England Listings API

This repository contains a project for scraping property listing data from various websites (such as **New England Farmland Finder** and **Landwatch**) and storing the extracted information in a **Notion database**.

The project is built using **FastAPI** for the API endpoint, with a modular design that includes:

## 🏗 Project Structure

### 🔍 **Scraping**

The `scraper.py` file contains functions to extract listing data from a given URL. It supports:

- **Static pages**: Uses `requests` and `BeautifulSoup`
- **Dynamic pages**: Uses `Selenium` with headless Chrome (e.g., Landwatch)

### 📝 **Notion Integration**

The `notion_integration.py` file handles interactions with the **Notion API**, creating new entries in a **Notion database** with the following fields:

- Listing Name
- URL
- Platform
- Listing Date
- Price & Price Bucket
- Acreage & Acreage Bucket
- Property Type
- House & Farm Details
- Location & Distance

### 🚀 **API Endpoint**

The `main.py` file is a **FastAPI** application that exposes a **POST** endpoint:

- ``: Accepts a listing URL, scrapes the data, and creates a new entry in the Notion database.

---

## ✨ Features

✅ **Domain-Specific Scraping**: Automatically selects a scraping method (static vs. dynamic)\
✅ **Notion Database Integration**: Stores scraped data for easy comparison and review\
✅ **RESTful API**: Enables integration with other tools or workflows\
✅ **Selenium Support**: Handles JavaScript-rendered pages with headless Chrome

---

## ⚙️ Prerequisites

Ensure you have **Python 3.8 or higher** installed.

### 📦 **Required Python Packages**

Install the following dependencies:

```bash
pip install requests beautifulsoup4 notion-client fastapi uvicorn
```

### 🌐 **For Dynamic Pages (Landwatch)**

Additional requirements:

- Install `selenium`
- Download & install [ChromeDriver](https://chromedriver.chromium.org/downloads)\
  Ensure it is **added to your system's PATH**.

```bash
pip install selenium
```

---

## 🛠 Installation & Setup

1️⃣ **Clone the Repository**

```bash
git clone https://github.com/your_username/new-england-listings.git
cd new-england-listings
```

2️⃣ **(Optional) Create a Python Virtual Environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

