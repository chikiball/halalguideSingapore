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
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:latest")

agent: Optional[HalalAgent] = None


@app.on_event("startup")
async def startup():
    global agent
    agent = HalalAgent(
        ollama_url=OLLAMA_URL,
        searxng_url=SEARXNG_URL,
        nominatim_url=NOMINATIM_URL,
        model=OLLAMA_MODEL,
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
            places = await agent.discover_places(req.lat, req.lng, req.radius, debug_emit=debug_queue.put)

            # Flush any remaining debug events
            while not debug_queue.empty():
                evt = debug_queue.get_nowait()
                yield {"event": "debug", "data": json.dumps(evt)}

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

            yield {"event": "status", "data": json.dumps({"phase": "writing", "message": f"Writing article for {req.name}..."})}

            article = await agent.write_article(req.dict(), research)
            yield {"event": "article", "data": json.dumps(article)}

            yield {"event": "done", "data": json.dumps({"name": req.name})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_stream())
