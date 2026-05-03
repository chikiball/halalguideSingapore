# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running Locally

**Node.js app only (no AI):**
```bash
npm install
npm start          # http://localhost:3000
```

**Full stack (with AI agent):**
```bash
docker compose up -d
# Requires an external Docker network: docker network create server-net
# Requires Ollama running on server-net at ollama:11434 with llama3.1:latest pulled
```

**Agent logs (most useful for debugging):**
```bash
sudo docker logs halal-agent -f --tail 50
```

**Test agent health:**
```bash
sudo docker exec halal-agent curl -s http://localhost:5000/health
```

## Deploying to Server

```bash
sudo bash server-setup/scripts/deploy-ai.sh
```

This script handles: preflight checks → git pull → setup patches → nginx reload → docker build → health checks → integration tests.

For agent-only rebuilds: `sudo docker compose up -d --build agent`

## Architecture

### Two-Layer Backend

The Node.js app (`server.js` + `ai-routes.js`) is a thin proxy. All AI logic lives in the Python FastAPI microservice (`agent-service/`). Node.js SSE-proxies requests to Python verbatim — `ai-routes.js:_proxySSE()` pipes bytes directly with no buffering.

### Three-Phase Agent Pipeline (`agent-service/agent.py: HalalAgent`)

Every restaurant goes through these phases in sequence:

1. **Phase 1 — Discovery** (`discover_places`): SearXNG search → LLM extracts restaurant names → Nominatim geocodes them → radius filter. Only used when the frontend calls `/api/ai/search` (not the main hybrid flow).

2. **Phase 2 — Research** (`research_place`): 11 parallel SearXNG queries + scrape top 8 URLs + MUIS API check → compile evidence → **pork pre-filter** (regex, no LLM) → LLM classification → **image validation** (LLM, batched) → return result. This is the hot path called for every card.

3. **Phase 3 — Article** (`write_article`): Single LLM call using only the structured classification output (not raw evidence). Called immediately after Phase 2 in the SSE stream.

### Pork Pre-Filter (agent.py: `_has_pork_evidence`)

Runs **before** the LLM. Scans compiled evidence text for pork menu items (char siew, bak kut teh, pork belly, etc.). If found without denial language (no pork, halal certified, muis certified), returns `excluded: True` — the LLM is never called and the place is never shown. This saves ~15s per excluded place.

### Hold-Until-Verified Frontend (`public/ai-search.js`)

Cards are **not** rendered from OSM immediately. `currentPlaces` starts empty and is populated as each place passes research. `cardIndex` is assigned as `currentPlaces.length` at push time — the array only ever grows, so indices are permanently stable for card DOM IDs and map marker click handlers.

### SSE Streaming Pattern

Python agent yields Server-Sent Events in order: `status` → `research` → `status` → `article` → `done`. Frontend reads the stream in `researchPlace()` and splits on event type: `data.classification` → research result, `data.article || data.title` → article result. Both are cached in `aiResearchCache` keyed by `place.name + place.lat.toFixed(3)`.

### Image Validation (`_validate_images_with_llm`)

After classification, scraped `og_image` URLs are filtered in one batched LLM call. Passes URL path + page title + source domain per image. If all rejected, falls back to `ImageFinderTool.find_images()` (SearXNG image search), then cuisine-based Unsplash fallbacks. Fail-safe: if LLM response can't be parsed, original images are returned unchanged.

### MUIS Halal Check (`scraper.py: scrape_muis`)

Two-step: GET the MUIS directory page to extract CSRF token → POST to the JSON API. The old approach (scraping www.muis.gov.sg) always returned 403. Uses `halal.muis.gov.sg/api/halal/establishments`.

## Critical Warnings

- **`setup-agent-service.sh` creates stub files — NEVER re-run** after real implementations exist. It will overwrite `agent.py`, `main.py`, and all tools with empty stubs.
- **`setup-step10.sh` patches `index.html` and `server.js`** — it adds `ai-search.js`/`ai-debug.js` script tags and bridges `window.searchLat/searchLng`. It is idempotent and safe to re-run.
- **JS cache-busting**: after editing `ai-search.js` or `ai-debug.js`, bump the `?v=N` suffix in `index.html`: `sed -i 's/ai-search.js?v=[0-9]*/ai-search.js?v=N/' public/index.html`
- **Ollama is external** — it lives in the `chatui` Docker stack at container name `ollama` on `server-net`. It is not defined in this repo's `docker-compose.yml`.
- **No persistent cache** — all AI research results are in-memory and lost on container restart.

## Key Environment Variables (agent-service)

| Variable | Default | Notes |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Points to `http://ollama:11434` in Docker |
| `SEARXNG_URL` | `http://localhost:8888` | Points to `http://searxng:8080` in Docker |
| `OLLAMA_MODEL` | `llama3.1:latest` | 8B model — json_mode enabled for all classification calls |

## Debug Mode

Add `?debug=1` to the URL to activate the debug panel, which shows the full pipeline in real-time including raw LLM prompts and responses. The same data appears in Docker logs: `sudo docker logs halal-agent -f`.
