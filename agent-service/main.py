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

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888")
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org")

agent: Optional[HalalAgent] = None


@app.on_event("startup")
async def startup():
    global agent
    if not DEEPSEEK_API_KEY:
        print("⚠️ DEEPSEEK_API_KEY is not set — LLM calls will fail (401).")
    agent = HalalAgent(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        searxng_url=SEARXNG_URL,
        nominatim_url=NOMINATIM_URL,
        model=DEEPSEEK_MODEL,
    )
    print(f"🤖 Agent ready | DeepSeek: {DEEPSEEK_BASE_URL} ({DEEPSEEK_MODEL}) | SearXNG: {SEARXNG_URL}")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "provider": "deepseek",
        "base_url": DEEPSEEK_BASE_URL,
        "searxng_url": SEARXNG_URL,
        "model": DEEPSEEK_MODEL,
        "api_key_set": bool(DEEPSEEK_API_KEY),
    }


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
    """Phase 1: Discover halal places near coordinates. Returns SSE stream with debug events."""
    if not agent:
        raise HTTPException(503, "Agent not initialized")

    # Collect debug events from the agent via a queue
    import asyncio
    debug_queue = asyncio.Queue()

    async def event_stream():
        try:
            yield {"event": "status", "data": json.dumps({"phase": "discovery", "message": "Searching for halal restaurants..."})}

            # Run discovery with debug callback
            async def emit_debug(evt):
                # Send debug events INLINE as they happen (not queued)
                # Use a special "debug" flag so the browser can distinguish them
                evt["debug"] = True
                yield_data = json.dumps(evt)
                # We can't yield from inside the callback, so we queue
                await debug_queue.put(evt)

            places = await agent.discover_places(req.lat, req.lng, req.radius, debug_emit=debug_queue.put)

            # Flush debug events collected during discovery
            while not debug_queue.empty():
                evt = debug_queue.get_nowait()
                # Send as status event with debug flag — browser can parse this
                yield {"event": "status", "data": json.dumps({"phase": "debug", "debug": True, **evt})}

            for place in places:
                yield {"event": "place", "data": json.dumps(place)}

            yield {"event": "done", "data": json.dumps({"count": len(places)})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    # Start a background task that drains debug_queue and yields events
    # But SSE generators can't be mixed easily, so we use a simpler approach:
    # The agent emits debug events into the queue, and we drain after discovery completes.
    # For real-time streaming, we'll refactor agent to yield events directly.

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

            if research.get("excluded"):
                yield {"event": "done", "data": json.dumps({"name": req.name, "excluded": True})}
                return

            yield {"event": "status", "data": json.dumps({"phase": "writing", "message": f"Writing article for {req.name}..."})}

            article = await agent.write_article(req.dict(), research)
            yield {"event": "article", "data": json.dumps(article)}

            yield {"event": "done", "data": json.dumps({"name": req.name})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_stream())
