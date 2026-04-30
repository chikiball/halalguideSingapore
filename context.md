# Halal Guide Singapore — Project Context

> Last updated: 2026-04-29
> Repo: `https://github.com/chikiball/halalguideSingapore.git`
> Local: `/Users/nandha_handharu/Documents/Nandha/GitHub/halalguideSingapore`
> Server: `/home/nandha/server/sites/halalguideSingapore` (Ubuntu home server)
> Live: **https://halal.nandharu.uk**
> Debug: **https://halal.nandharu.uk/?debug=1**

---

## 1. What This Is

A mobile-friendly web app that helps users discover halal and Muslim-friendly food in Singapore. Uses a **hybrid approach**: OpenStreetMap for fast geographic discovery + AI agent (Ollama llama3.1 + SearXNG) for halal classification, research, and article writing.

### How It Works (Hybrid Pipeline)

```
User picks location (GPS or tap map)
    ↓ tap Search
✨ "AI is performing search for halal food..."
    ↓ ~2 seconds
OSM (Overpass API) finds ALL food places within radius
    ↓ instant
Cards + map markers appear immediately (⚪ Checking...)
    ↓ parallel, per restaurant (~15s each)
AI agent researches each place:
  SearXNG (11 queries) → scrape websites → check MUIS → scrape halaltag.com
    ↓
LLM (llama3.1) classifies halal status + extracts facts
    ↓ cards update one by one
Badges change: ⚪ → ☪️ Halal Certified / 🟢 Muslim Owned / etc.
    ↓ user taps card
LLM writes warm 150-250 word article + images shown in modal
```

---

## 2. Key Features

| Feature | Description |
|---|---|
| 📍 GPS Location | Browser Geolocation API, falls back to Singapore center |
| 🗺️ Pick on Map | Tap map to drop a draggable pin with "🔍 Search here" button |
| 🔍 Hybrid Search | OSM for geography + AI for halal intelligence |
| ✨ Pulsating Loading | "AI is performing search for halal food..." with animated ✨ |
| 🃏 Progressive Cards | Appear instantly from OSM, badges update as AI finishes |
| ☪️ 7 Halal Categories | Certified, Muslim Owned, No Pork No Lard, Halal Friendly, Vegetarian, Vegan, Unverified |
| 📰 AI Articles | LLM-written 150-250 word articles grounded in real evidence |
| 🖼️ Image Gallery | Website photos → SearXNG images → cuisine fallback |
| 🧭 Directions | One-tap Google Maps navigation |
| 💾 Caching | In-memory cache per phase (no re-research on 2nd tap) |
| 🐛 Debug Panel | Add `?debug=1` to URL — shows full pipeline in real-time |

---

## 3. Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML/CSS/JS — `index.html` + `ai-search.js` + `ai-debug.js` |
| Backend (web) | Node.js + Express |
| Backend (AI) | Python + FastAPI |
| LLM | Ollama llama3.1:latest (8B, shared from chatui stack) |
| Search Engine | SearXNG (self-hosted, aggregates Google/Bing/DuckDuckGo) |
| Map | Leaflet.js + OpenStreetMap tiles (free, no API key) |
| OSM Data | Overpass API with 3 mirror fallback |
| Geocoding | Nominatim (free, OpenStreetMap) |
| Web Scraping | httpx + BeautifulSoup (Python) |
| Deploy | Docker Compose (3 containers) + Nginx + Cloudflare Tunnel |

---

## 4. File Structure

```
halalguideSingapore/
├── server.js              # Express: /api/halal (OSM), /api/place/details (legacy crawl)
├── ai-routes.js           # Express: /api/ai/* → SSE proxy to Python agent
├── crawler.js             # Legacy web crawler (Wikipedia, DuckDuckGo, cheerio)
├── public/
│   ├── index.html         # Main frontend: map, cards, modal, pick-on-map
│   ├── ai-search.js       # Hybrid search: OSM discovery + AI research + progressive cards
│   └── ai-debug.js        # Debug panel (activate with ?debug=1)
│
├── agent-service/         # Python AI agent microservice
│   ├── main.py            # FastAPI: /search (SSE), /place/details (SSE), /health
│   ├── agent.py           # HalalAgent: 3-phase pipeline (600+ lines)
│   ├── tools/
│   │   ├── search.py      # SearXNG: 11 search categories per restaurant
│   │   ├── scraper.py     # Web scraper + MUIS checker + halaltag.com
│   │   ├── geocoder.py    # Nominatim geocoder with rate limiting
│   │   ├── image_finder.py # Image search + website extraction + fallback
│   │   └── halal_classifier.py # 7 halal categories + badge config
│   ├── prompts/
│   │   ├── discovery.txt  # System prompt for Phase 1
│   │   ├── research.txt   # System prompt for Phase 2 (classification rules)
│   │   └── article.txt    # System prompt for Phase 3
│   ├── searxng/
│   │   ├── settings.yml   # SearXNG config (Google, Bing, DDG, port 8080)
│   │   └── limiter.toml   # Disable rate limiting (internal use)
│   ├── Dockerfile         # python:3.11-slim, non-root, PYTHONUNBUFFERED=1
│   └── requirements.txt   # langchain, fastapi, httpx, bs4, sse-starlette
│
├── server-setup/
│   ├── nginx/
│   │   └── halalguideSingapore.conf  # Nginx: SSE proxy (no buffering, 180s timeout)
│   └── scripts/
│       ├── deploy-ai.sh              # Full deployment: preflight → build → test
│       └── update-deploy-files.sh    # Updates Dockerfile, fly.toml, .dockerignore
│
├── setup-agent-service.sh # Creates agent stubs (first time only — DO NOT re-run)
├── setup-step10.sh        # Patches server.js + index.html (idempotent)
│
├── docker-compose.yml     # 3 services: app + agent + searxng
├── Dockerfile             # node:18-alpine, non-root, curl healthcheck
├── package.json           # express, node-fetch, cheerio
├── fly.toml               # Fly.io: sin region, 512MB (backup deploy)
└── context.md             # ← this file
```

---

## 5. API Endpoints

### Node.js (server.js + ai-routes.js)

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serves frontend |
| GET | `/api/halal?lat=&lng=&radius=&all=true` | OSM search (all=true skips halal filter) |
| POST | `/api/place/details` | Legacy web crawl |
| POST | `/api/ai/search` | AI search → SSE stream |
| POST | `/api/ai/place/details` | AI research + article → SSE stream |
| GET | `/api/ai/health` | Agent health check |

### Python Agent (main.py)

| Method | Path | Description |
|---|---|---|
| POST | `/search` | Phase 1: discover places (SSE) |
| POST | `/place/details` | Phase 2+3: research + article (SSE) |
| GET | `/health` | Health + config info |

---

## 6. Hybrid Search Pipeline

### Step 1: OSM Geographic Discovery (~2 seconds)

- Node.js calls Overpass API with `?all=true` (returns ALL food places, no halal filter)
- 3 mirror fallback: kumi → mail.ru → overpass-api.de
- Returns restaurants, fast food, cafes, food courts within radius with real coordinates

### Step 2: Cards + Map Appear Instantly

- Cards rendered with "⚪ Checking..." badge and "✨ AI researching halal status..."
- Map markers placed at real OSM coordinates

### Step 3: AI Agent Researches Each Place (parallel, ~15s each)

For each restaurant, the Python agent runs:

#### 3a. SearXNG Web Search (11 parallel queries)

| # | Category | Query |
|---|---|---|
| 1 | general | `"{name}" Singapore restaurant` |
| 2 | halal | `"{name}" Singapore halal certificate MUIS certified` |
| 3 | pork_lard | `"{name}" Singapore no pork no lard` |
| 4 | muslim_owned | `"{name}" Singapore Muslim owned` |
| 5 | menu | `"{name}" Singapore menu prices food` |
| 6 | reviews | `"{name}" Singapore review rating` |
| 7 | vegan | `"{name}" Singapore vegetarian vegan plant-based` |
| 8 | halaltag | `site:halaltag.com {name} Singapore` |
| 9 | halaltrip | `site:halaltrip.com {name} Singapore` |
| 10 | sethlah | `site:sethlah.com {name}` |
| 11 | muis_dir | `site:muis.gov.sg {name} halal` |

#### 3b. Web Scraping

- Scrape top 8 URLs from search results
- Direct scrape halaltag.com and halaltrip.com search pages
- Extract: text, images, og:image, halal mentions, prices, phone, hours

#### 3c. MUIS Official API Check

**This is now a real-time query against the MUIS e-Service database** (not a scrape).

```
Step 1: GET halal.muis.gov.sg/halal/establishments
        → extract session cookie + CSRF token from hidden __RequestVerificationToken input

Step 2: POST halal.muis.gov.sg/api/halal/establishments
        Headers: X-CSRF-TOKEN, session cookie, X-Requested-With: XMLHttpRequest
        Body:    {"text": "restaurant name"}

Step 3: JSON response parsed → name matching → definitive result
```

Response format:
```json
{
  "totalRecords": 155,
  "data": [
    {
      "name": "McDonald's",
      "number": "EERN20020010957",
      "address": "6 RAFFLES BOULEVARD #02-156 MARINA SQUARE 039594",
      "schemeText": "Eating Establishment",
      "subSchemeText": "Restaurant"
    }
  ]
}
```

LLM evidence when certified:
```
MUIS CHECK: ✅ OFFICIALLY CERTIFIED
  Certificate Number: EERN20020010957
  Certified Name: McDonald's
  Address: 6 RAFFLES BOULEVARD #02-156 MARINA SQUARE
  Scheme: Eating Establishment — Restaurant
```

LLM evidence when not found:
```
MUIS CHECK: ❌ Not found in MUIS directory (searched 155 records)
  (MUIS result: McDonald's Tampines | EEFK20230000680 | 9 TAMPINES AVE 2)
```

**Why the old check always failed:** The previous implementation tried to scrape `www.muis.gov.sg/Halal/Halal-Certificates` which returns 403 (blocked by CloudFront) and uses JS rendering, so BeautifulSoup never saw any restaurant data.

#### 3d. LLM Classification (Ollama llama3.1)

All evidence sent to LLM with structured prompt. Returns:
- Status (7 categories), confidence (high/medium/low), reasoning
- Cuisine, price range, popular dishes, hours, phone, website

### Step 4: Cards Update Progressively

Badges change from "⚪ Checking..." to classification result. Status bar shows progress: "✨ Researching... 5/35 places done"

### Step 5: Article Writing (on card tap)

LLM writes 150-250 word warm article grounded in evidence. No hallucinated details.

---

## 7. Halal Classification Categories

| Status | Label | Icon | Badge | Criteria |
|---|---|---|---|---|
| `halal_certified` | Halal Certified | ☪️ | Green | MUIS certificate evidence |
| `muslim_owned` | Muslim Owned | 🟢 | Green | Owner confirmed Muslim |
| `no_pork_no_lard` | No Pork No Lard | 🚫🐷 | Blue | Explicitly stated |
| `halal_friendly` | Halal Friendly | 🔵 | Blue | Offers halal options |
| `vegetarian` | Vegetarian | 🌿 | Teal | No meat |
| `vegan` | Vegan | 🌱 | Teal | No animal products |
| `unverified` | Unverified | ⚪ | Gray | Insufficient evidence |

Confidence: `high` (MUIS cert) | `medium` (consistent mentions) | `low` (1-2 mentions)

---

## 8. Docker Architecture

```
Cloudflare → tunnel → nginx-gateway
    ↓
┌─────────────────┐  ┌──────────┐  ┌────────┐  ┌────────┐
│halalguideSingapore│→│halal-agent│→│searxng  │  │ollama  │
│Node.js :3000    │  │Python:5000│  │:8080   │  │:11434  │
│512MB, 0.5 CPU   │  │1GB, 1 CPU │  │512MB   │  │8GB     │
└─────────────────┘  └──────────┘  └────────┘  └────────┘
                     all on server-net Docker network
```

- **Ollama** runs in chatui stack (`/home/nandha/server/sites/chatui/`), shared via server-net
- Model: `llama3.1:latest` (8B, Q4_K_M, ~4.7GB)
- `PYTHONUNBUFFERED=1` for real-time logging
- Startup order: searxng (healthy) → agent (healthy) → app

---

## 9. Frontend

### Single search flow (no mode toggle)

1. User picks location (GPS or map tap)
2. Taps Search → pulsating ✨ "AI is performing search for halal food..."
3. Cards appear instantly from OSM (⚪ Checking...)
4. Cards update one-by-one as AI finishes (badge + confidence)
5. Tap card → modal: images + article + halal assessment + directions

### Files

- `index.html` — main app, patched by `setup-step10.sh` for:
  - `window.searchLat/searchLng` bridge (let → window)
  - ai-search.js + ai-debug.js script tags (with cache-bust `?v=N`)
  - Default radius 500m, max 3km (5km removed)
  - "🔍 Search here" button in map pin popup
  - Header: "✨AI powered - Find halal & Muslim-friendly food near you"
  - `?all=true` support in /api/halal (skip halal filter for hybrid mode)
- `ai-search.js` — hybrid search module (overrides searchHalal)
- `ai-debug.js` — debug panel (only active with `?debug=1`)

### Debug Panel (`?debug=1`)

Dark terminal panel at bottom showing real-time pipeline:
- All OSM results with distance + type + cuisine
- AI research progress per restaurant
- Classification results with confidence + reasoning
- **Full LLM prompts and responses** (system prompt + user prompt + response + duration)
- Copy all logs to clipboard

LLM prompts visible in debug panel (per restaurant tap):
```
[LLM] 📡 2 LLM call(s) made for this restaurant:
[LLM] ━━━ LLM Call #1 (12.4s, json=true) ━━━
[LLM] 📋 SYSTEM: You are a halal food researcher for Singapore...
[LLM] 📝 USER: Based on the following evidence about "McDonald's":
       MUIS CHECK: ✅ OFFICIALLY CERTIFIED
       Certificate Number: EERN20020010957...
[LLM] ✅ RESPONSE: {"status":"halal_certified","confidence":"high"...
```

Also viewable in Docker logs:
```bash
sudo docker logs halal-agent -f --tail 50
```

---

## 10. Deployment

### Deploy command

```bash
cd /home/nandha/server/sites/halalguideSingapore
sudo git pull origin main
sudo bash setup-step10.sh
sudo docker compose build --no-cache app agent
sudo docker compose up -d app agent
```

### Useful commands

| Task | Command |
|---|---|
| Full deploy | `sudo bash server-setup/scripts/deploy-ai.sh` |
| Rebuild agent | `sudo docker compose up -d --build agent` |
| Rebuild app | `sudo docker compose build --no-cache app && sudo docker compose up -d app` |
| Agent logs | `sudo docker logs halal-agent -f --tail 20` |
| App logs | `sudo docker logs halalguideSingapore -f --tail 20` |
| Test agent | `sudo docker exec halal-agent curl -s http://localhost:5000/health` |
| Test Ollama | `sudo docker exec halal-agent curl -s http://ollama:11434/api/tags` |
| Bust cache | `sudo sed -i 's/ai-search.js?v=[0-9]*/ai-search.js?v=N/' public/index.html` |

### Cloudflare tunnel

| Field | Value |
|---|---|
| Subdomain | `halal` |
| Domain | `nandharu.uk` |
| Type | HTTP |
| URL | `nginx-gateway:80` |

---

## 11. Security (5 layers)

| Layer | Component | Protection |
|---|---|---|
| 1 | Cloudflare | DDoS, WAF, SSL, IP hiding |
| 2 | OS | UFW, Fail2Ban, SSH hardening |
| 3 | Nginx | Rate limits, SSE: no buffering 180s |
| 4 | Docker | Non-root, read-only, no-new-privileges |
| 5 | App | No DB, no uploads, no secrets |

---

## 12. Memory Budget (32GB server)

| Service | RAM |
|---|---|
| Ollama llama3.1 | ~8 GB |
| SearXNG | ~200 MB |
| Agent service | ~500 MB |
| Node.js app | ~200 MB |
| Open WebUI (chatui) | ~1 GB |
| nginx + tunnel | ~100 MB |
| aidatajakarta | ~300 MB |
| **Total** | **~10.3 GB** (leaves ~22 GB for OS) |

---

## 13. Known Issues & Future Ideas

### Current issues
- **LLM extraction quality:** llama3.1:8b occasionally extracts wrong names from search results
- **Geocoding rate limit:** Nominatim 1 req/sec means batch geocoding is slow
- **SG address format:** "Blk" prefix partially fixed with regex, some addresses still fail
- **No persistent cache:** AI results reset on container restart
- **Browser caching:** JS files need manual cache-busting (`?v=N`) after updates
- **MUIS session:** CSRF token fetched per restaurant — adds ~2s per check (can be optimised with session caching)

### Fixed issues
- ~~**MUIS check always returned false**~~ → Fixed: now queries official MUIS API with CSRF auth, returns real cert numbers

### Future improvements
- **Redis/file cache** — persist AI results across restarts
- **MUIS session cache** — reuse session cookie across restaurants in same search batch
- **Pre-crawl popular areas** — cache Bugis, Kampong Glam, Geylang Serai
- **Upgrade to llama3.1:70b** — better classification (needs ~48GB RAM)
- **User contributions** — "Suggest a place" feature
- **Prayer times** — nearby mosque integration
- **Offline mode** — service worker
- **Rate limit AI research** — queue system for busy periods

### ⚠️ Setup scripts warning
- `setup-agent-service.sh` — creates STUB files. **NEVER** re-run after implementations exist
- `setup-step10.sh` — safe to re-run (idempotent patches)
- Always bump `?v=N` cache-bust after updating JS files
