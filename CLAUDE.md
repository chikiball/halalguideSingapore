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
cp .env.example .env   # then fill in DEEPSEEK_API_KEY and MAPBOX_TOKEN
docker compose up -d
# Requires an external Docker network: docker network create server-net
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

This script handles: preflight (Docker, `DEEPSEEK_API_KEY` in `.env`, `server-net`) → `chown` + `git pull` **as `$REPO_OWNER`** (default `nandha`, not root) → setup patches → nginx config reload → docker build → **nginx reload again to re-resolve the app container's new IP** → health checks → integration tests (probed via `docker exec`, since the app is only `expose`d, not host-published).

For agent-only rebuilds: `sudo docker compose up -d --build agent`

## Architecture

### Two-Layer Backend

The Node.js app does two jobs: (1) it owns the **OSM/Overpass data layer** (`server.js` + `crawler.js`), and (2) it is a **thin SSE proxy** to the AI agent (`ai-routes.js`). All AI logic lives in the Python FastAPI microservice (`agent-service/`). Node.js SSE-proxies AI requests to Python verbatim — `ai-routes.js:_proxySSE()` pipes bytes directly with no buffering.

### OSM Discovery Layer (`server.js`) — the hybrid flow's real Phase 1

The "main hybrid flow" the frontend uses does **not** call the AI agent's Phase 1. Instead:

- **`GET /api/halal`** (`server.js`) queries the **Overpass API** with a 3-mirror fallback chain (`OVERPASS_ENDPOINTS`), fetches all food amenities in radius, then filters server-side with the `isHalalFriendly` heuristic (explicit `diet:halal`/`halal` tags, else cuisine/name regex `HALAL_CUISINE_RE`/`HALAL_NAME_RE`). Returns places with **real coordinates** — this is what gives the hybrid flow its geographic accuracy.
- The frontend (`public/ai-search.js`) takes those OSM places and calls the AI agent's `/api/ai/place/details` (Phase 2+3) per place to classify and write articles.

**Two endpoints named `place/details` — do not confuse them:**
- `POST /api/place/details` → `crawler.js` (non-AI web crawl, in-memory `detailCache`). Legacy/standalone detail fetch.
- `POST /api/ai/place/details` → proxies to Python agent (Phase 2+3 SSE). Used by the hybrid flow.

### AI Endpoints (`ai-routes.js` → `agent-service/main.py`)

- `POST /api/ai/search` → agent `/search` → Phase 1 Discovery (SSE). Standalone; not on the hybrid hot path.
- `POST /api/ai/place/details` → agent `/place/details` → Phase 2+3 (SSE).
- `GET /api/ai/health` → agent `/health`. Agent listens on port 5000 (`AGENT_URL`, default `http://localhost:5000`).

### Three-Phase Agent Pipeline (`agent-service/agent.py: HalalAgent`)

Every restaurant goes through these phases in sequence:

1. **Phase 1 — Discovery** (`discover_places`): SearXNG search → LLM extracts restaurant names → Nominatim geocodes them → radius filter. Only used by the standalone `/api/ai/search` endpoint — the main hybrid flow does discovery via the OSM layer above, not this.

2. **Phase 2 — Research** (`research_place`): 11 parallel SearXNG queries + scrape top 8 URLs + MUIS API check → compile evidence → **pork pre-filter** (regex, no LLM) → LLM classification → **image validation** (LLM, batched) → return result. This is the hot path called for every card.

3. **Phase 3 — Article** (`write_article`): Single LLM call using only the structured classification output (not raw evidence). Called immediately after Phase 2 in the SSE stream.

### Pork Pre-Filter (agent.py: `_has_pork_evidence`)

Runs **before** the LLM. Scans compiled evidence text for pork menu items (char siew, bak kut teh, pork belly, etc.). If found without denial language (no pork, halal certified, muis certified), returns `excluded: True` — the LLM is never called and the place is never shown. This saves ~15s per excluded place.

### Hold-Until-Verified Frontend (`public/ai-search.js`)

Cards are **not** rendered from OSM immediately. `currentPlaces` starts empty and is populated as each place passes research. `cardIndex` is assigned as `currentPlaces.length` at push time — the array only ever grows, so indices are permanently stable for card DOM IDs and map marker click handlers.

`searchHalal` can fire from several triggers (GPS auto-search, the main button, the map "Search here" popup), so each call bumps a module-level `searchToken`; the `await` continuations bail out when superseded. This prevents overlapping searches from sharing `currentPlaces`/the cards DOM and flashing a stale "No results found" over rendered cards.

### SSE Streaming Pattern

Python agent yields Server-Sent Events in order: `status` → `research` → `status` → `article` → `done`. Frontend reads the stream in `researchPlace()` and splits on event type: `data.classification` → research result, `data.article || data.title` → article result. Both are cached in `aiResearchCache` keyed by `place.name + place.lat.toFixed(3)`.

### Image Validation (`_validate_images_with_llm`)

After classification, scraped `og_image` URLs are filtered in one batched LLM call. Passes URL path + page title + source domain per image. If all rejected, falls back to `ImageFinderTool.find_images()` (SearXNG image search), then cuisine-based Unsplash fallbacks. Fail-safe: if LLM response can't be parsed, original images are returned unchanged.

### LLM Calls (`agent.py: _call_llm`)

A single chokepoint — `_call_llm()` — hand-rolls an httpx POST to **DeepSeek's OpenAI-compatible** `/chat/completions` (`Authorization: Bearer $DEEPSEEK_API_KEY`). Every phase (discovery, research classification, image validation, article) routes through it, so the provider lives in one place. `json_mode=True` sets `response_format: {"type":"json_object"}` — DeepSeek requires the word "json" in the prompt, which the existing prompts already satisfy. Responses are parsed from `choices[0].message.content`; the `_parse_json_object`/`_parse_json_array` helpers tolerate malformed output. `HalalClassifier.classify` is a stub and unused.

### Map (`public/index.html: initMap`)

Leaflet 1.9.4 with **Mapbox Streets raster tiles** (`mapbox/streets-v12`). The token comes from `window.MAPBOX_TOKEN`, served by `server.js` at `/config.js` (a blocking classic `<script>` loaded before the inline map script, so it's race-free and the token stays out of git). If `MAPBOX_TOKEN` is unset, `initMap` falls back to raw OSM tiles. Markers/pick-mode are still plain Leaflet (also in `ai-search.js`) — only the basemap changed.

### MUIS Halal Check (`scraper.py: scrape_muis`)

Two-step: GET the MUIS directory page to extract CSRF token → POST to the JSON API. The old approach (scraping www.muis.gov.sg) always returned 403. Uses `halal.muis.gov.sg/api/halal/establishments`.

## Critical Warnings

- **`setup-agent-service.sh` creates stub files — NEVER re-run** after real implementations exist. It will overwrite `agent.py`, `main.py`, and all tools with empty stubs.
- **`setup-step10.sh` patches are now folded into the committed source** (`server.js` AI routes + `?all=true`; `index.html` window bridge, `ai-search.js`/`ai-debug.js` tags, header/radius/Search-here tweaks). Its idempotency guards now all detect "already present", so on deploy it's effectively a no-op. It stays in the pipeline as a safety net — keep the source in sync with its guards so it doesn't re-dirty the tree.
- **JS cache-busting**: after editing `ai-search.js` or `ai-debug.js`, bump the `?v=N` suffix in `index.html` (currently `v=8`): `sed -i 's/ai-search.js?v=[0-9]*/ai-search.js?v=N/' public/index.html`
- **Editing `public/*` or `server.js` requires an app rebuild** — static files are baked into the image and the container is `read_only`. `sudo docker compose up -d --build app` (a plain restart/pull won't pick them up).
- **Never `sudo git` in the repo** — it leaves root-owned files that then block plain `git pull` ("unable to unlink … Permission denied"). The deploy script pulls as `$REPO_OWNER` and `chown`s the tree to keep it user-owned.
- **nginx caches the app container's IP** — `halalguideSingapore.conf` uses a static `proxy_pass` hostname with no `resolver`, so a container rebuild (new IP) causes **502** until `docker exec nginx-gateway nginx -s reload`. The deploy script reloads after the build for this reason.
- **DeepSeek is the LLM** — a hosted OpenAI-compatible API, not a local model. `DEEPSEEK_API_KEY` (and `MAPBOX_TOKEN`) live in a gitignored `.env`; see `.env.example`. There is no Ollama/local-model container anymore. To change the model, edit `DEEPSEEK_MODEL` in `.env` and rebuild the agent (note: `deepseek-reasoner` does **not** support `response_format` JSON mode, so it would need code changes in `_call_llm`).
- **No persistent cache** — all AI research results are in-memory and lost on container restart.

## Key Environment Variables

| Variable | Service | Default | Notes |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | agent | — | **Required.** Bearer token for DeepSeek; from `.env`. |
| `DEEPSEEK_BASE_URL` | agent | `https://api.deepseek.com` | POSTs to `{base}/chat/completions`. |
| `DEEPSEEK_MODEL` | agent | `deepseek-chat` | json_mode set via `response_format` for classification calls. |
| `SEARXNG_URL` | agent | `http://localhost:8888` | Points to `http://searxng:8080` in Docker. |
| `MAPBOX_TOKEN` | app | — | Public Mapbox token; served to the browser via `/config.js`. Empty → OSM tile fallback. |

## Debug Mode

Add `?debug=1` to the URL to activate the debug panel, which shows the full pipeline in real-time including raw LLM prompts and responses. The same data appears in Docker logs: `sudo docker logs halal-agent -f`.
