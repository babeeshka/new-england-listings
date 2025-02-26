# src/new_england_listings/config/settings.py
import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class ConfigurationError(Exception):
    """Custom exception for configuration errors."""
    pass


@dataclass
class NotionConfig:
    api_key: str
    database_id: str

    @classmethod
    def from_env(cls):
        api_key = os.getenv("NOTION_API_KEY")
        database_id = os.getenv("NOTION_DATABASE_ID")

        if not api_key:
            api_key = "default-key-for-development"
        if not database_id:
            database_id = "default-db-for-development"

        return cls(api_key=api_key, database_id=database_id)


@dataclass
class SeleniumConfig:
    headless: bool = True
    disable_gpu: bool = True
    no_sandbox: bool = True
    disable_dev_shm_usage: bool = True
    window_size: tuple = (1920, 1080)
    implicit_wait: int = 10


@dataclass
class CacheConfig:
    enabled: bool = True
    duration: int = 3600  # 1 hour in seconds
    max_size: int = 1000


@dataclass
class RateLimitConfig:
    max_requests: int = 100
    per_seconds: int = 3600


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: str = "new_england_listings.log"


@dataclass
class RetryConfig:
    max_retries: int = 3
    backoff_factor: int = 2
    retry_statuses: tuple = (500, 502, 503, 504)


class Settings:
    """Settings manager for the application."""

    def __init__(self, env: Optional[str] = None):
        self.env = env or os.getenv("APP_ENV", "development")
        self.config_dir = Path(__file__).parent.parent / "config"

        # Load base settings
        self.notion = NotionConfig.from_env()
        self.selenium = SeleniumConfig()
        self.cache = CacheConfig()
        self.rate_limit = RateLimitConfig()
        self.logging = LoggingConfig()
        self.retry = RetryConfig()

        # Load environment-specific settings
        self._load_env_settings()

    def _load_env_settings(self):
        """Load environment-specific settings from file."""
        config_file = self.config_dir / f"{self.env}.yaml"

        if config_file.exists():
            with open(config_file) as f:
                config = yaml.safe_load(f)

            # Update configurations based on YAML
            if "selenium" in config:
                self.selenium = SeleniumConfig(**config["selenium"])
            if "cache" in config:
                self.cache = CacheConfig(**config["cache"])
            if "rate_limit" in config:
                self.rate_limit = RateLimitConfig(**config["rate_limit"])
            if "logging" in config:
                self.logging = LoggingConfig(**config["logging"])
            if "retry" in config:
                self.retry = RetryConfig(**config["retry"])


# Create global settings instance
settings = Settings()

# Export settings values that are used elsewhere
NOTION_API_KEY = settings.notion.api_key
NOTION_DATABASE_ID = settings.notion.database_id
DEFAULT_TIMEOUT = 30
MAX_RETRIES = settings.retry.max_retries
RATE_LIMIT = settings.rate_limit.__dict__

# Export settings instance


def get_settings(env: Optional[str] = None) -> Settings:
    """Get settings instance."""
    global settings
    if env and env != settings.env:
        settings = Settings(env)
    return settings


def get_fresh_settings(force_reload=False):
    """Get settings with a forced environment reload."""
    if force_reload:
        # Force reload .env file
        from dotenv import load_dotenv
        load_dotenv(override=True)

        # Reset the settings instance
        global settings
        settings = Settings()

    return settings


# Then update how NOTION_DATABASE_ID is defined:
NOTION_DATABASE_ID = get_fresh_settings(force_reload=True).notion.database_id
