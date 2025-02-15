# tests/conftest.py
import pytest
import os
from new_england_listings.config.settings import Settings

@pytest.fixture
def test_settings():
    """Provide test settings."""
    os.environ["NOTION_API_KEY"] = "test-key"
    os.environ["NOTION_DATABASE_ID"] = "test-db"
    return Settings("test")
