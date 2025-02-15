# tests/test_integration/test_scraper.py
import pytest
from new_england_listings import process_listing


@pytest.mark.integration  # Mark as integration test
def test_landandfarm_integration():
    url = "https://www.landandfarm.com/property/single-family-residence-cape-windham-me-36400823/"
    data = process_listing(url, use_notion=False)

    assert data["platform"] == "Land and Farm"
    assert "Windham" in data["location"]
    assert data.get("acreage") is not None


@pytest.mark.integration
def test_realtor_integration():
    url = "https://www.realtor.com/realestateandhomes-detail/28-Vanderwerf-Dr_West-Bath_ME_04530_M36122-24566"
    data = process_listing(url, use_notion=False)

    assert data["platform"] == "Realtor.com"
    assert "West Bath" in data["location"]
    assert data.get("price") is not None


@pytest.mark.integration
def test_farmland_integration():
    url = "https://farmlink.mainefarmlandtrust.org/individual-farm-listings/farm-id-3582"
    data = process_listing(url, use_notion=False)

    assert data["platform"] == "Maine Farmland Trust"
    assert data.get("farm_details") is not None
