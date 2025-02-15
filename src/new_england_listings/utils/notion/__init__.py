# ./src/new_england_listings/utils/notion/__init__.py
"""Notion integration module for New England Listings."""

from .client import NotionClient, create_notion_entry

__all__ = ["NotionClient", "create_notion_entry"]
