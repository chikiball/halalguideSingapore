#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Halal Guide SG — AI Agent Service Setup
# Run once: bash setup-agent-service.sh
# Creates the entire agent-service/ directory with all files
# ═══════════════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"
echo "📂 Setting up agent-service in: $(pwd)"

mkdir -p agent-service/{searxng,tools,prompts}

# ─── SearXNG Config ───────────────────────────────────────────────
cat > agent-service/searxng/settings.yml << 'SEOF'
use_default_settings: true

general:
  instance_name: "HalalGuideSG Search"
  debug: false
  privacypolicy_url: false
  donation_url: false
  enable_metrics: false

search:
  safe_search: 0
  autocomplete: ""
  default_lang: "en"
  formats:
    - html
    - json

server:
  secret_key: "halal-guide-sg-searxng-internal-2026"
  bind_address: "0.0.0.0"
  port: 8888
  limiter: false
  image_proxy: true
  method: "GET"

ui:
  static_use_hash: true
  default_theme: simple

engines:
  - name: google
    engine: google
    shortcut: g
    disabled: false
  - name: bing
    engine: bing
    shortcut: b
    disabled: false
  - name: duckduckgo
    engine: duckduckgo
    shortcut: ddg
    disabled: false
  - name: wikipedia
    engine: wikipedia
    shortcut: wp
    disabled: false

outgoing:
  request_timeout: 10
  max_request_timeout: 15
  useragent_suffix: "HalalGuideSG/1.0"
  pool_connections: 100
  pool_maxsize: 20
SEOF

cat > agent-service/searxng/limiter.toml << 'SEOF'
[botdetection.ip_limit]
link_token = false
SEOF

# ─── Agent Service: requirements.txt ──────────────────────────────
cat > agent-service/requirements.txt << 'REOF'
langchain>=0.3.0
langchain-ollama>=0.2.0
langchain-community>=0.3.0
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
httpx>=0.27.0
beautifulsoup4>=4.12.0
pydantic>=2.0.0
sse-starlette>=2.0.0
REOF

# ─── Agent Service: Dockerfile ────────────────────────────────────
cat > agent-service/Dockerfile << 'DEOF'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=30s \
  CMD curl -sf http://localhost:5000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
DEOF

# ─── Agent Service: main.py (FastAPI app) ─────────────────────────
cat > agent-service/main.py << 'MEOF'
"""
Halal Guide Singapore — AI Agent Service
FastAPI app that orchestrates LangChain agent with Ollama + SearXNG.
"""
import os
import json
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent import HalalAgent

app = FastAPI(title="Halal Guide SG Agent", version="1.0.0", docs_url="/docs")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888")
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org")

agent: Optional[HalalAgent] = None


@app.on_event("startup")
async def startup():
    global agent
    agent = HalalAgent(
        ollama_url=OLLAMA_URL,
        searxng_url=SEARXNG_URL,
        nominatim_url=NOMINATIM_URL,
        model="llama3.1:8b",
    )
    print(f"🤖 Agent ready | Ollama: {OLLAMA_URL} | SearXNG: {SEARXNG_URL}")


@app.get("/health")
async def health():
    return {"status": "ok", "ollama_url": OLLAMA_URL, "searxng_url": SEARXNG_URL, "model": "llama3.1:8b"}


class SearchRequest(BaseModel):
    lat: float
    lng: float
    radius: int = 1500


class DetailRequest(BaseModel):
    name: str
    lat: float
    lng: float
    type: str = "restaurant"
    cuisine: str = ""
    address: str = ""
    website: str = ""


@app.post("/search")
async def search_places(req: SearchRequest):
    """Phase 1: Discover halal places near coordinates. Returns SSE stream."""
    if not agent:
        raise HTTPException(503, "Agent not initialized")

    async def event_stream():
        try:
            yield {"event": "status", "data": json.dumps({"phase": "discovery", "message": "Searching for halal restaurants..."})}

            places = await agent.discover_places(req.lat, req.lng, req.radius)

            for place in places:
                yield {"event": "place", "data": json.dumps(place)}

            yield {"event": "done", "data": json.dumps({"count": len(places)})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_stream())


@app.post("/place/details")
async def place_details(req: DetailRequest):
    """Phase 2+3: Research place + write article. Returns SSE stream."""
    if not agent:
        raise HTTPException(503, "Agent not initialized")

    async def event_stream():
        try:
            yield {"event": "status", "data": json.dumps({"phase": "research", "message": f"Researching {req.name}..."})}

            research = await agent.research_place(req.dict())
            yield {"event": "research", "data": json.dumps(research)}

            yield {"event": "status", "data": json.dumps({"phase": "writing", "message": f"Writing article for {req.name}..."})}

            article = await agent.write_article(req.dict(), research)
            yield {"event": "article", "data": json.dumps(article)}

            yield {"event": "done", "data": json.dumps({"name": req.name})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_stream())
MEOF

# ─── Agent Service: agent.py (LangChain agent) ───────────────────
cat > agent-service/agent.py << 'AEOF'
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
AEOF

# ─── Tool stubs ───────────────────────────────────────────────────
cat > agent-service/tools/__init__.py << 'TEOF'
TEOF

cat > agent-service/tools/search.py << 'TEOF'
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
TEOF

cat > agent-service/tools/scraper.py << 'TEOF'
"""Web scraper tool — Step 4."""
import httpx
from typing import Dict, Optional


class ScraperTool:
    def __init__(self):
        print("  🌐 ScraperTool ready")

    async def scrape(self, url: str) -> Dict:
        """Scrape a URL for content. Returns {title, description, text, images, og_image}."""
        # TODO: Implement in Step 4
        return {}

    async def scrape_muis(self, restaurant_name: str) -> Dict:
        """Check MUIS halal certification directory for a restaurant."""
        # TODO: Implement in Step 4
        return {}
TEOF

cat > agent-service/tools/geocoder.py << 'TEOF'
"""Nominatim geocoding tool — Step 5."""
import httpx
import math
from typing import Dict, Optional


class GeocoderTool:
    def __init__(self, nominatim_url: str):
        self.base_url = nominatim_url.rstrip("/")
        print(f"  📍 GeocoderTool ready | {nominatim_url}")

    async def geocode(self, address: str, country: str = "sg") -> Optional[Dict]:
        """Convert address string to {lat, lng, display_name}."""
        # TODO: Implement in Step 5
        return None

    @staticmethod
    def distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Haversine distance in meters."""
        R = 6371e3
        d_lat = math.radians(lat2 - lat1)
        d_lng = math.radians(lng2 - lng1)
        a = math.sin(d_lat / 2) ** 2 + \
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
            math.sin(d_lng / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
TEOF

cat > agent-service/tools/image_finder.py << 'TEOF'
"""Image finder tool — Step 9."""
from typing import List, Dict


class ImageFinderTool:
    def __init__(self, searxng_url: str):
        self.searxng_url = searxng_url
        print("  🖼️  ImageFinderTool ready")

    async def find_images(self, name: str, cuisine: str = "") -> List[Dict]:
        """Find images for a restaurant. Returns list of {url, caption, source}."""
        # TODO: Implement in Step 9
        return []
TEOF

cat > agent-service/tools/halal_classifier.py << 'TEOF'
"""Halal classifier — Step 7."""
from typing import Dict


class HalalClassifier:
    def __init__(self, ollama_url: str, model: str):
        self.ollama_url = ollama_url
        self.model = model
        print(f"  ☪️  HalalClassifier ready | model={model}")

    async def classify(self, place: Dict, evidence: Dict) -> Dict:
        """
        Classify halal status based on evidence.
        Returns {status, confidence, reasoning, certificate}.
        """
        # TODO: Implement in Step 7
        return {"status": "unverified", "confidence": 0.0, "reasoning": "", "certificate": None}
TEOF

# ─── Prompts ──────────────────────────────────────────────────────
cat > agent-service/prompts/discovery.txt << 'PEOF'
You are a restaurant discovery assistant for Singapore.
Given coordinates (lat, lng) and a search radius, find halal and Muslim-friendly food establishments nearby.

For each restaurant found, extract:
- Name
- Address
- Type (restaurant, cafe, fast_food, food_court)
- Cuisine type
- Any mention of halal certification

Focus on:
1. Places explicitly mentioned as halal or Muslim-friendly
2. Malay, Indonesian, Middle Eastern, Indian, Turkish restaurants
3. Places in areas known for Muslim-friendly food (Kampong Glam, Geylang Serai, etc.)

Return results as a JSON array.
PEOF

cat > agent-service/prompts/research.txt << 'PEOF'
You are a halal food researcher for Singapore.
Given a restaurant name and location, analyze the gathered evidence to determine:

1. HALAL STATUS — classify as one of:
   - "certified": Has MUIS halal certificate (provide cert number if found)
   - "muslim_owned": Owner is Muslim, serves halal food, but no official cert
   - "halal_friendly": Offers halal options, not fully halal
   - "vegan": No meat products — safe for Muslim consumption
   - "unverified": Not enough evidence

2. KEY FACTS — extract:
   - Cuisine type
   - Price range
   - Popular dishes
   - Operating hours
   - Contact info

Be conservative — only classify as "certified" if you find actual certificate evidence.
Provide your reasoning step by step.
PEOF

cat > agent-service/prompts/article.txt << 'PEOF'
You are a warm, engaging food writer for a halal guide app in Singapore.
Write a short article (150-250 words) about the restaurant based on the research provided.

Guidelines:
- Start with a warm, inviting opening
- Mention the cuisine and signature dishes
- Note the halal status clearly and accurately
- Include practical info (location, price range)
- End with a friendly recommendation
- Use emoji sparingly (1-2 max)
- Be factual — only mention things from the research data
- Do NOT make up dishes, prices, or details not in the evidence

Return JSON:
{
  "title": "Short catchy title",
  "article": "The full article text with **bold** for emphasis",
  "tags": ["halal-certified", "malay", "budget-friendly"]
}
PEOF

# ─── .dockerignore for agent-service ──────────────────────────────
cat > agent-service/.dockerignore << 'DIEOF'
__pycache__
*.pyc
.git
.env
searxng/
DIEOF

# ─── Summary ─────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo "✅ Agent service scaffolded! Files created:"
echo "═══════════════════════════════════════════════════"
find agent-service -type f | sort | while read f; do
  echo "  📄 $f ($(wc -c < "$f" | tr -d ' ') bytes)"
done
echo ""
echo "Next: implement each tool step by step."
