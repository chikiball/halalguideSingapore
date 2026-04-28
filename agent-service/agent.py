"""
Halal Guide Singapore — LangChain Agent
Orchestrates tools for discovery, research, and article writing.
Built in Steps 3-8. This is the scaffold.
"""
import asyncio
import math
from typing import List, Dict, Any, Optional

from tools.search import SearchTool
from tools.scraper import ScraperTool
from tools.geocoder import GeocoderTool
from tools.image_finder import ImageFinderTool
from tools.halal_classifier import HalalClassifier


class HalalAgent:
    def __init__(self, ollama_url: str, searxng_url: str, nominatim_url: str, model: str = "llama3.1:8b"):
        self.ollama_url = ollama_url
        self.searxng_url = searxng_url
        self.nominatim_url = nominatim_url
        self.model = model

        self.search = SearchTool(searxng_url)
        self.scraper = ScraperTool()
        self.geocoder = GeocoderTool(nominatim_url)
        self.image_finder = ImageFinderTool(searxng_url)
        self.classifier = HalalClassifier(ollama_url, model)

        self._cache: Dict[str, Any] = {}
        print(f"🤖 HalalAgent initialized | model={model}")

    async def discover_places(self, lat: float, lng: float, radius: int) -> List[Dict]:
        """Phase 1: Search for restaurants near coordinates, geocode them."""
        # TODO: Step 6 — wire LangChain agent with search + geocode tools
        return []

    async def research_place(self, place: Dict) -> Dict:
        """Phase 2: Deep research — menu, halal cert, reviews, images."""
        # TODO: Step 7 — search + scrape + classify
        return {}

    async def write_article(self, place: Dict, research: Dict) -> Dict:
        """Phase 3: LLM writes warm article from research data."""
        # TODO: Step 8 — Ollama article generation
        return {}
