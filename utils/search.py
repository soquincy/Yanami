# utils/search.py: Google Custom Search integration.

import os
import logging
import aiohttp

logger = logging.getLogger("FreesonaBot")

GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
SEARCH_ENGINE_ID      = os.getenv("SEARCH_ENGINE_ID")


async def web_search(query: str) -> str:
    if not GOOGLE_SEARCH_API_KEY or not SEARCH_ENGINE_ID:
        return "Search not configured."
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": GOOGLE_SEARCH_API_KEY, "cx": SEARCH_ENGINE_ID, "q": query, "num": 5}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        items = data.get("items", [])
        if not items:
            return "No results."
        return "\n".join(f"- {i['title']} ({i['link']})" for i in items)
    except Exception as e:
        logger.error(f"Search error: {e}")
        return "Search failed."