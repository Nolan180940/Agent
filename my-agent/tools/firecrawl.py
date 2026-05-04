"""
Web scraping tools using Firecrawl.
"""
import os
from typing import Any, Dict, List, Optional

from tools.base import tool


def _get_firecrawl_client(api_key: Optional[str] = None):
    """Create a Firecrawl client using the provided key or environment variable."""
    try:
        from firecrawl import Firecrawl
    except ImportError as exc:
        raise ImportError(
            "Firecrawl is not installed. Install it with `pip install firecrawl-py` (or the package required by your SDK version)."
        ) from exc

    resolved_key = api_key or os.getenv("FIRECRAWL_API_KEY")
    if not resolved_key:
        raise ValueError("FIRECRAWL_API_KEY is not set.")

    return Firecrawl(api_key=resolved_key)


def _normalize_response(data: Any) -> str:
    """Convert Firecrawl responses to a readable string."""
    if data is None:
        return ""

    if isinstance(data, str):
        return data

    if isinstance(data, dict):
        if "markdown" in data and isinstance(data["markdown"], str):
            return data["markdown"]
        if "content" in data and isinstance(data["content"], str):
            return data["content"]

    return str(data)


@tool(category="browser")
def firecrawl_scrape(
    url: str,
    only_main_content: bool = False,
    max_age: int = 172800000,
    parsers: Optional[List[str]] = None,
    formats: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> str:
    """
    Scrape a webpage with Firecrawl and return markdown or structured content.

    Args:
        url: Target URL to scrape.
        only_main_content: Whether to extract only the main content.
        max_age: Cache age in milliseconds.
        parsers: Optional parser list, e.g. ["pdf"].
        formats: Output formats to request, e.g. ["markdown"].
        api_key: Optional Firecrawl API key. If omitted, reads FIRECRAWL_API_KEY.

    Returns:
        Scraped page content as text.
    """
    try:
        client = _get_firecrawl_client(api_key)

        scrape_kwargs: Dict[str, Any] = {
            "only_main_content": only_main_content,
            "max_age": max_age,
        }

        if parsers is not None:
            scrape_kwargs["parsers"] = parsers
        if formats is not None:
            scrape_kwargs["formats"] = formats

        result = client.scrape(url, **scrape_kwargs)
        return _normalize_response(result)
    except Exception as exc:
        return f"Firecrawl scrape failed for {url}: {exc}"
