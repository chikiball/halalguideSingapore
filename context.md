# Halal Guide Singapore — Project Context

> Last updated: 2026-04-29
> Repo: `https://github.com/chikiball/halalguideSingapore.git`
> Local: `/Users/nandha_handharu/Documents/Nandha/GitHub/halalguideSingapore`
> Server: `/home/nandha/server/sites/halalguideSingapore` (Ubuntu home server)
> Live: **https://halal.nandharu.uk**

---

## 1. What This Is

A mobile-friendly web app that helps users discover halal and Muslim-friendly food establishments near them in Singapore. Features **two search modes**:

- **Quick Search (OSM)** — fast, uses OpenStreetMap Overpass API (~2s)
- **AI Search (LLM)** — uses a local AI agent (Ollama llama3.1 + SearXNG) to search the web, research each restaurant, classify halal status, and write articles (~30s-2min)

---

## 2. Key Features

| Feature | Description |
|---|---|
| 📍 GPS Location | Browser Geolocation API, falls back to Singapore center |
| 🗺️ Pick on Map | Tap map to drop a draggable pin (no GPS needed) |
| 🔍 Quick Search (OSM) | Overpass API → fetch all food places → server-side halal filter |
| 🤖 AI Search (LLM) | SearXNG web search → Ollama llama3.1 → classify + write articles |
| 🃏 Card Results | Sorted by distance, progressive rendering via SSE streaming |
| 📰 Detail Modal | Tap card → shimmer loading → AI-written article + image gallery |
| ☪️ 7 Halal Categories | Certified, Muslim Owned, No Pork No Lard, Halal Friendly, Vegetarian, Vegan, Unverified |
| 🧭 Directions | One-tap Google Maps navigation |
| 💾 Caching | In-memory cache per phase (no re-search/re-research on 2nd tap) |

---

## 3. Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML/CSS/JS — `index.html` + `ai-search.js` |
| Backend (web) | Node.js + Express |
| Backend (AI) | Python + FastAPI + LangChain |
| LLM | Ollama running llama3.1:latest (8B, shared from chatui stack) |
| Search Engine | SearXNG (self-hosted, aggregates Google/Bing/DuckDuckGo) |
| Map | Leaflet.js + OpenStreetMap tiles (free, no API key) |
| OSM Data | Overpass API with 3 mirror fallback |
| Geocoding | Nominatim (free, OpenStreetMap) |
| Web Crawling | httpx + BeautifulSoup (Python) / cheerio (Node.js legacy) |
| Deploy | Docker Compose (3 containers) + Nginx + Cloudflare Tunnel |

---

## 4. File Structure

```
halalguideSingapore/
├── server.js              # Express app: /api/halal + /api/place/details
├── ai-routes.js           # Express routes: /api/ai/* → proxy SSE to agent
├── crawler.js             # Legacy web crawler (Wikipedia, DuckDuckGo, cheerio)
├── public/
│   ├── index.html         # Main frontend: map, cards, modal, pick-on-map
│   └── ai-search.js       # AI search module: SSE streaming, AI cards, badges
│
├── agent-service/         # ← Python AI agent microservice
│   ├── main.py            # FastAPI: /search (SSE), /place/details (SSE), /health
│   ├── agent.py           # HalalAgent: 3-phase pipeline (550 lines)
│   ├── tools/
│   │   ├── search.py      # SearXNG web + image search (249 lines)
│   │   ├── scraper.py     # Web scraper + MUIS checker (348 lines)
│   │   ├── geocoder.py    # Nominatim geocoder with rate limiting (219 lines)
│   │   ├── image_finder.py # Image search + website extraction (300 lines)
│   │   └── halal_classifier.py # 7 halal categories + badge config (79 lines)
│   ├── prompts/
│   │   ├── discovery.txt  # System prompt for Phase 1 (find restaurants)
│   │   ├── research.txt   # System prompt for Phase 2 (classify halal)
│   │   └── article.txt    # System prompt for Phase 3 (write articles)
│   ├── searxng/
│   │   ├── settings.yml   # SearXNG config (Google, Bing, DDG, port 8080)
│   │   └── limiter.toml   # Disable rate limiting (internal use)
│   ├── Dockerfile         # python:3.11-slim, non-root, PYTHONUNBUFFERED=1
│   ├── requirements.txt   # langchain, fastapi, httpx, bs4, sse-starlette
│   └── .dockerignore
│
├── server-setup/
│   ├── nginx/
│   │   └── halalguideSingapore.conf  # Nginx: SSE proxy (no buffering, 180s timeout)
│   └── scripts/
│       ├── deploy-ai.sh              # Full deployment: preflight → build → test
│       └── update-deploy-files.sh    # Updates Dockerfile, fly.toml, .dockerignore
│
├── setup-agent-service.sh # Creates agent-service stubs (run once, first time only)
├── setup-step10.sh        # Patches server.js + index.html for AI routes
│
├── docker-compose.yml     # 3 services: app + agent + searxng
├── Dockerfile             # node:18-alpine, non-root, curl healthcheck
├── package.json           # express, node-fetch, cheerio
├── fly.toml               # Fly.io: sin region, 512MB (backup deploy)
├── .gitignore
├── README.md
└── context.md             # ← this file
```

---

## 5. API Endpoints

### Node.js (server.js + ai-routes.js)

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serves `public/index.html` |
| GET | `/api/halal?lat=&lng=&radius=` | OSM search via Overpass API |
| POST | `/api/place/details` | Legacy web crawl (cheerio) |
| POST | `/api/ai/search` | AI search → SSE stream of places |
| POST | `/api/ai/place/details` | AI research + article → SSE stream |
| GET | `/api/ai/health` | Agent service health check |

### Python Agent (main.py)

| Method | Path | Description |
|---|---|---|
| POST | `/search` | Phase 1: discover places (SSE) |
| POST | `/place/details` | Phase 2+3: research + article (SSE) |
| GET | `/health` | Health check + config info |

---

## 6. AI Agent — 3-Phase Pipeline

### Phase 1: Discovery (~30s)

```
reverse_geocode(lat, lng) → "Bugis"
    ↓
12 parallel SearXNG searches:
  - halal certified, halal, Muslim owned, Muslim friendly
  - no pork no lard, vegetarian/vegan
  - Malay/Indonesian, Middle Eastern/Arab/Turkish, Indian/Pakistani
  - area-specific queries using geocoded area name
    ↓
LLM (llama3.1) extracts restaurant names + addresses from search results
  (fallback: regex extraction if LLM fails)
    ↓
Multi-strategy geocoding per restaurant:
  1. Clean address (strip Blk, #unit, No.)
  2. Postal code only ("Singapore 208859")
  3. Street name + Singapore
  4. Restaurant name + Singapore
    ↓
Filter by radius → deduplicate → return places
```

### Phase 2: Research (~15s per restaurant)

```
7 targeted SearXNG searches per restaurant:
  general, halal cert, pork/lard, Muslim owned, menu, reviews, vegan
    ↓
Scrape top 8 URLs (parallel, 5 concurrent max)
    ↓
Check MUIS halal certification directory
    ↓
LLM classifies halal status (7 categories) with confidence level
    ↓
Extract: cuisine, price range, dishes, hours, phone, website
```

### Phase 3: Article (~5s)

```
LLM writes 150-250 word article grounded in Phase 2 evidence only
    ↓
Returns: {title, article, tags, images, classification}
```

---

## 7. Halal Classification Categories (AI mode)

| Status | Label | Icon | Badge Color | Criteria |
|---|---|---|---|---|
| `halal_certified` | Halal Certified | ☪️ | Green | MUIS certificate evidence found |
| `muslim_owned` | Muslim Owned | 🟢 | Green | Owner confirmed Muslim, no cert |
| `no_pork_no_lard` | No Pork No Lard | 🚫🐷 | Blue | Explicitly stated, not certified |
| `halal_friendly` | Halal Friendly | 🔵 | Blue | Offers halal options, not fully halal |
| `vegetarian` | Vegetarian | 🌿 | Teal | No meat at all |
| `vegan` | Vegan | 🌱 | Teal | No animal products at all |
| `unverified` | Unverified | ⚪ | Gray | Insufficient evidence |

Confidence levels: `high` (MUIS cert found), `medium` (consistent mentions), `low` (1-2 mentions)

---

## 8. Halal Detection Logic (OSM mode, legacy)

### Data source: Overpass API (OpenStreetMap)

Fetches ALL food establishments within radius, filters server-side:

- **Explicit tags:** `diet:halal = yes | only | limited`, `halal = yes`
- **Cuisine match:** halal, malay, indonesian, middle_eastern, arab, turkish, etc.
- **Name match:** halal, muslim, nasi, mee, roti, prata, murtabak, satay, etc.

Badge system: ☪ Halal ✓ (tagged) or 🟢 Muslim-Friendly (inferred)

---

## 9. Docker Architecture (3 containers + shared Ollama)

```
Visitor → https://halal.nandharu.uk
    │
    ▼
┌──────────────────────────────┐
│  Cloudflare Edge (SIN)       │
└──────────┬───────────────────┘
           │  tunnel
┌──────────▼───────────────────┐
│  nginx-gateway               │
│  ├─ /          → app:3000    │
│  ├─ /api/halal → app:3000   │ (30s timeout)
│  ├─ /api/ai/*  → app:3000   │ (180s, no buffering, SSE)
│  └─ /api/place → app:3000   │ (30s timeout)
└──────────┬───────────────────┘
           │
    ┌──────┼──────────┐
    │      │          │
┌───▼──┐ ┌─▼────┐ ┌──▼─────┐ ┌────────┐
│ app  │→│agent │→│searxng │ │ ollama │ ← from chatui stack
│:3000 │ │:5000 │ │:8080   │ │:11434  │
│512MB │ │1GB   │ │512MB   │ │8GB     │
└──────┘ └──────┘ └────────┘ └────────┘
         all on server-net (Docker)
```

### Key config details

| Service | Container Name | Port | Memory | CPU |
|---|---|---|---|---|
| app (Node.js) | halalguideSingapore | 3000 | 512MB | 0.5 |
| agent (Python) | halal-agent | 5000 | 1GB | 1.0 |
| searxng | searxng | 8080 | 512MB | 0.5 |
| ollama | ollama | 11434 | 8GB | 4.0 |

- **Ollama is NOT in this docker-compose** — it runs in the chatui stack (`/home/nandha/server/sites/chatui/`) on the shared `server-net`
- Agent reaches Ollama via `http://ollama:11434` (same Docker network)
- Model: `llama3.1:latest` (8B, Q4_K_M, ~4.7GB)
- All services: `read_only: true`, `no-new-privileges`, resource limits
- `PYTHONUNBUFFERED=1` on agent for real-time Docker logging
- Startup order: searxng (healthy) → agent (healthy) → app

---

## 10. Frontend

### Two search modes (toggle bar)

| Mode | Button | Speed | Source |
|---|---|---|---|
| 🗺️ Quick Search | Default, active | ~2s | OpenStreetMap Overpass API |
| 🤖 AI Search | Toggle | ~30s-2min | SearXNG → Ollama llama3.1 |

### AI search UX flow

1. User picks location + toggles to 🤖 AI Search + taps Search
2. Status bar: spinner + "Discovering — Searching for halal restaurants..."
3. Cards appear progressively as each place is geocoded (SSE streaming)
4. Cards show "🤖 AI powered — tap for details"
5. Tap a card → modal opens with shimmer → "Researching..." → "Writing..."
6. Modal renders: image gallery + article + halal assessment + details

### Files

- `index.html` — main app (map, OSM search, modal, pick-on-map)
- `ai-search.js` — AI module (injected at runtime, overrides searchHalal())
  - Adds search mode toggle bar
  - Consumes SSE streams via ReadableStream API
  - Renders AI-specific cards with 7 badge types
  - AI modal with research results, confidence levels, reasoning

### Design

- Font: Inter (Google Fonts)
- Primary: `#1a6b4a` (green)
- Mobile-first, responsive grid (1/2/3 columns)
- Card radius: 16px, bottom-sheet modal
- Shimmer loading animation

---

## 11. Deployment

### Full AI stack deployment (single command)

```bash
# Server:
cd /home/nandha/server/sites/halalguideSingapore
sudo git pull origin main
sudo bash server-setup/scripts/deploy-ai.sh
```

The `deploy-ai.sh` script:
1. Pre-flight checks: Docker, Compose, Ollama container, llama3.1 model, server-net
2. Git pull latest code
3. Runs setup scripts (agent scaffold, AI routes patch, deploy files)
4. Copies nginx config + reload
5. `docker compose up -d --build` (3 containers)
6. Waits for health checks (searxng → agent → app)
7. Runs 5 integration tests
8. Prints container status summary

### Manual deployment

```bash
cd /home/nandha/server/sites/halalguideSingapore
sudo git pull origin main
sudo docker compose up -d --build
sudo cp server-setup/nginx/halalguideSingapore.conf /home/nandha/server/nginx/conf.d/
sudo docker exec nginx-gateway nginx -s reload
```

### Useful commands

| Task | Command |
|---|---|
| Full deploy | `sudo bash .../deploy-ai.sh` |
| Rebuild agent only | `sudo docker compose up -d --build agent` |
| Agent logs | `sudo docker logs halal-agent -f --tail 20` |
| App logs | `sudo docker logs halalguideSingapore -f --tail 20` |
| SearXNG logs | `sudo docker logs searxng --tail 10` |
| Test agent | `sudo docker exec halal-agent curl -s http://localhost:5000/health` |
| Test SearXNG | `sudo docker exec searxng wget -qO- "http://localhost:8080/healthz"` |
| Test Ollama | `sudo docker exec halal-agent curl -s http://ollama:11434/api/tags` |
| Restart all | `sudo docker compose restart` |
| Force rebuild all | `sudo docker compose up -d --build --force-recreate` |
| Status dashboard | `sudo bash /home/nandha/server/scripts/status.sh` |

### Cloudflare tunnel config

| Field | Value |
|---|---|
| Subdomain | `halal` |
| Domain | `nandharu.uk` |
| Type | `HTTP` |
| URL | `nginx-gateway:80` |

---

## 12. Security (5 layers)

| Layer | Component | What it does |
|---|---|---|
| 1. Cloudflare | Edge | DDoS, WAF, SSL, IP hiding, caching |
| 2. OS | UFW + Fail2Ban | Deny all inbound, SSH hardening |
| 3. Nginx | Rate limits | 10 req/s general, 5 req/s API, SSE: no buffering, 180s timeout |
| 4. Docker | Isolation | Non-root, read-only fs, no-new-privileges, resource limits |
| 5. App | Minimal surface | No DB, no uploads, no secrets |

---

## 13. Memory Budget (32GB server)

| Service | RAM |
|---|---|
| Ollama llama3.1:latest | ~8 GB |
| SearXNG | ~200 MB |
| Agent service | ~500 MB |
| Node.js app | ~200 MB |
| Open WebUI (chatui) | ~1 GB |
| nginx + tunnel | ~100 MB |
| aidatajakarta | ~300 MB |
| **Total** | **~10.3 GB** (leaves ~22 GB for OS) |

---

## 14. Known Limitations & Future Ideas

### Current limitations
- **LLM extraction quality:** llama3.1:8b sometimes extracts blog titles instead of restaurant names
- **Geocoding rate limit:** Nominatim allows 1 req/sec, so 20 restaurants = ~20s
- **SG address format:** "Blk" prefix and unit numbers confuse Nominatim (partially fixed with regex stripping)
- **No persistent cache:** AI results reset on container restart
- **OSM data coverage:** Many SG halal places don't have `diet:halal` tag
- **Single hawker center issue:** LLM may list all stalls in one food court with same address

### Future improvements
- **Better LLM prompts:** More examples, stricter name-only extraction
- **Upgrade to llama3.1:70b:** Better extraction quality (needs ~48GB RAM)
- **Redis cache:** Persist AI results across restarts
- **Pre-crawl popular areas:** Cache results for Bugis, Kampong Glam, Geylang Serai
- **MUIS API integration:** Direct halal certification verification
- **Prayer time API:** Show nearby mosques with prayer times
- **User contributions:** "Suggest a place" feature
- **Offline mode:** Service worker for cached results
- **Image quality:** SearXNG image search for real restaurant photos

### Setup scripts warning
⚠️ `setup-agent-service.sh` creates STUB files. Do NOT run it after implementations exist — it overwrites real code with empty stubs. Only run once on first setup.
