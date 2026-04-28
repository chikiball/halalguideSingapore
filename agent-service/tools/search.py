"""SearXNG web search tool — Step 3."""
import httpx
from typing import List, Dict


class SearchTool:
    def __init__(self, searxng_url: str):
        self.base_url = searxng_url.rstrip("/")
        print(f"  🔍 SearchTool ready | {searxng_url}")

    async def search(self, query: str, categories: str = "general", num_results: int = 10) -> List[Dict]:
        """Perform a web search via SearXNG. Returns list of {title, url, snippet}."""
        # TODO: Implement in Step 3
        return []

    async def search_images(self, query: str, num_results: int = 5) -> List[Dict]:
        """Search for images via SearXNG. Returns list of {url, title, source}."""
        # TODO: Implement in Step 9
        return []
