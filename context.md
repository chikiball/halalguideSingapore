# Halal Guide Singapore — Project Context

> Last updated: 2026-04-28
> Repo: `https://github.com/chikiball/halalguideSingapore.git`
> Local: `/Users/nandha_handharu/Documents/Nandha/GitHub/halalguideSingapore`
> Server: `/home/nandha/server/sites/halalguideSingapore` (Ubuntu home server)
> Live: **https://halal.nandharu.uk**

---

## 1. What This Is

A mobile-friendly web app that helps users discover halal and Muslim-friendly food establishments near them in Singapore. Uses GPS or tap-to-pick location, queries OpenStreetMap via Overpass API for nearby food places, filters for halal/Muslim-friendly matches, and provides detailed info with web-crawled articles and images when a place is tapped.

---

## 2. Key Features

| Feature | Description |
|---|---|
| 📍 GPS Location | Browser Geolocation API, falls back to Singapore center |
| 🗺️ Pick on Map | Tap map to drop a draggable pin (no GPS needed) |
| 🔍 Halal Search | Overpass API → fetch all food places → server-side halal filter |
| 🃏 Card Results | Sorted by distance, badges for certified vs Muslim-friendly |
| 📰 Detail Modal | Tap card → shimmer loading → crawled article + image gallery |
| 🧭 Directions | One-tap Google Maps navigation |
| 💾 Caching | In-memory cache for crawled details (no re-crawl on 2nd tap) |

---

## 3. Tech Stack

| Layer | Technology |
|---|---|
| Backend | Node.js + Express (ES5 syntax for Node 12+ compat) |
| Frontend | Vanilla HTML/CSS/JS — single file (`public/index.html`) |
| Map | Leaflet.js + OpenStreetMap tiles (free, no API key) |
| Data | Overpass API (OpenStreetMap) with 3 mirror fallback |
| Crawling | Wikipedia API + DuckDuckGo + website scraping (cheerio) |
| Deploy (primary) | Home server: Docker + Nginx + Cloudflare Tunnel |
| Deploy (backup) | fly.io (Singapore `sin` region) |

---

## 4. File Structure

```
halalguideSingapore/
├── server.js              # Express app: /api/halal + /api/place/details routes
├── crawler.js             # Web crawler: Wikipedia, DuckDuckGo, website scraping
├── public/
│   └── index.html         # Single-page frontend: map, cards, modal, pick-on-map
├── server-setup/          # ← deployment configs for self-hosted Ubuntu server
│   ├── nginx/
│   │   └── halalguideSingapore.conf  # Reverse proxy: proxy_pass :3000
│   └── scripts/
│       └── update-deploy-files.sh    # Updates Dockerfile + fly.toml + .dockerignore
├── .github/
│   └── workflows/
│       └── fly-deploy.yml # GitHub Actions CI for Fly.io
├── package.json           # express, node-fetch, cheerio
├── package-lock.json
├── Dockerfile             # node:18-alpine, non-root appuser, curl healthcheck
├── docker-compose.yml     # App container (joins server-net, exposes 3000 internally)
├── fly.toml               # Fly.io config: sin region, 512 MB, auto-stop
├── .dockerignore
├── .gitignore             # ignores node_modules, .env, .DS_Store
├── README.md
└── context.md             # ← this file
```

---

## 5. API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serves `public/index.html` |
| GET | `/api/halal?lat=&lng=&radius=` | Search halal places via Overpass API |
| POST | `/api/place/details` | Crawl web for details, images, compose article |

---

## 6. Halal Detection Logic

### Data source: Overpass API (OpenStreetMap)

The app fetches ALL food establishments within radius, then filters server-side using these heuristics:

### Explicit tags (confirmed halal)
- `diet:halal = yes | only | limited`
- `halal = yes`

### Inferred (Muslim-friendly)
- **Cuisine match:** halal, malay, indonesian, middle_eastern, arab, turkish, pakistani, persian, afghan, bangladeshi, lebanese, indian, kebab, shawarma, falafel, mediterranean
- **Name match:** halal, muslim, nasi, mee, roti, prata, briyani, biryani, murtabak, satay, rendang, ayam, kambing, padang, warung, mamak, tandoori, kebab, shawarma, naan, soto, laksa, mee goreng, nasi lemak, teh tarik
- **Brand/operator match:** same keywords

### Badge system
| Status | Badge | Meaning |
|---|---|---|
| `yes` / `only` | ☪ Halal ✓ (green) | OSM tagged as halal |
| `likely` | 🟢 Muslim-Friendly (blue) | Inferred from cuisine/name |

---

## 7. Overpass API Mirrors (Fallback Chain)

The primary `overpass-api.de` frequently returns 504. The server tries in order:

1. `https://overpass.kumi.systems/api/interpreter`
2. `https://maps.mail.ru/osm/tools/overpass/api/interpreter`
3. `https://overpass-api.de/api/interpreter`

Each mirror gets 25s timeout before failing to the next.

---

## 8. Web Crawler (`crawler.js`)

### Sources (all free, no API keys)

| Source | What it fetches | Timeout |
|---|---|---|
| Wikipedia API | Article summary + thumbnail image | 8s |
| DuckDuckGo Instant Answer | Abstract, image, related topics | 8s |
| Website scrape (if URL in OSM) | og:image, meta description, hero images | 6s |
| DuckDuckGo HTML search | Review snippets from web results | 8s |

All 4 sources run in **parallel** (Promise.all).

### Article composer

Generates a warm, inviting write-up from crawled data:
1. Random warm opening referencing the place name
2. Cuisine description (if available)
3. Halal status note (certified vs inferred)
4. "What People Say" section (best 3 web snippets as blockquotes)
5. Address + hours
6. Random warm closing

### Image priority
1. Website og:image / hero images
2. Wikipedia thumbnail / original image
3. DuckDuckGo image
4. **Fallback:** Cuisine-based Unsplash photo (malay, indian, turkish, etc.)

### Caching
In-memory object, keyed by `name_lat_lng`. No TTL — lasts until server restart.

---

## 9. Frontend (`public/index.html`)

### Single-page app, 3 states:

| State | What's shown |
|---|---|
| **Landing** | "Use My Location" + "Choose on Map" buttons |
| **Main** | Map + location toggle + radius selector + cards |
| **Detail modal** | Header → gallery → quick info → article → sources → actions |

### Location modes
- **GPS mode:** Blue dot marker, uses browser geolocation
- **Pick mode:** Crosshair cursor, tap to place draggable red pin, banner hint

### Design
- Font: Inter (Google Fonts)
- Primary: `#1a6b4a` (green)
- Mobile-first, responsive grid (1/2/3 columns)
- Card radius: 16px, bottom-sheet modal
- Shimmer animation while crawling

---

## 10. Deployment

### 10A. Self-Hosted Ubuntu Server (primary)

- **Server:** Ubuntu home server at `/home/nandha/server/`
- **Domain:** `nandharu.uk` (Cloudflare)
- **Live URL:** https://halal.nandharu.uk
- **Architecture:** Cloudflare Tunnel → Nginx → Docker containers

#### Traffic flow

```
Visitor → https://halal.nandharu.uk
    │
    ▼
┌──────────────────────────────┐
│  Cloudflare Edge (SIN)       │  HTTPS termination, DDoS, WAF
└──────────┬───────────────────┘
           │  encrypted tunnel
           ▼
┌──────────────────────────────┐
│  cloudflare-tunnel           │  cloudflare/cloudflared:latest
│  network: server-net         │  shared with aidatajakarta
└──────────┬───────────────────┘
           │  http://nginx-gateway:80
           ▼
┌──────────────────────────────┐
│  nginx-gateway               │  nginx:alpine
│  server_name halal.nandharu.uk │  rate limiting, gzip
└──────────┬───────────────────┘
           │  http://halalguideSingapore:3000
           ▼
┌──────────────────────────────┐
│  halalguideSingapore         │  node:18-alpine, non-root
│  network: server-net         │  expose 3000 (internal only)
│  read_only: true             │  512 MB RAM, 0.5 CPU
└──────────────────────────────┘
```

#### docker-compose.yml (in repo root)

```yaml
services:
  app:
    build: .
    container_name: halalguideSingapore
    restart: unless-stopped
    expose:
      - "3000"
    environment:
      - PORT=3000
      - NODE_ENV=production
    networks:
      - server-net
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          memory: 512m
          cpus: '0.5'
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:3000/"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s

networks:
  server-net:
    external: true
```

#### Useful commands

| Task | Command |
|---|---|
| Deploy / redeploy | `sudo bash /home/nandha/server/scripts/deploy-site.sh halalguideSingapore` |
| View logs | `cd /home/nandha/server/sites/halalguideSingapore && sudo docker compose logs -f --tail 50` |
| Restart | `cd /home/nandha/server/sites/halalguideSingapore && sudo docker compose restart` |
| Force rebuild | `cd /home/nandha/server/sites/halalguideSingapore && sudo docker compose up -d --build --force-recreate` |
| Reload nginx | `sudo docker exec nginx-gateway nginx -s reload` |
| Status dashboard | `sudo bash /home/nandha/server/scripts/status.sh` |

#### Cloudflare tunnel config

| Field | Value |
|---|---|
| Subdomain | `halal` |
| Domain | `nandharu.uk` |
| Type | `HTTP` |
| URL | `nginx-gateway:80` |

Same tunnel + token as `jakarta.nandharu.uk` — just add another public hostname.

---

### 10B. Fly.io (backup / alternative)

```bash
fly auth login
fly launch        # accept existing fly.toml
fly deploy
fly open
```

- Region: `sin` (Singapore)
- VM: shared-cpu-1x, 512 MB
- Auto-stop when idle, auto-start on request

---

### 10C. Security (5 layers, same as aidatajakarta)

| Layer | Component | What it does |
|---|---|---|
| 1. Cloudflare | Edge | DDoS, WAF, SSL, IP hiding, caching |
| 2. OS | UFW + Fail2Ban | Deny all inbound, SSH hardening |
| 3. Nginx | Rate limits | 10 req/s general, 5 req/s API, security headers |
| 4. Docker | Isolation | Non-root, read-only fs, no-new-privileges, 512MB limit |
| 5. App | Minimal surface | No DB, no uploads, no secrets, 2 GET + 1 POST |

---

## 11. Deploy Playbook (New Setup)

### On local machine:
```bash
cd ~/Documents/Nandha/GitHub/halalguideSingapore
bash server-setup/scripts/update-deploy-files.sh
git add -A && git commit -m "Deploy configs" && git push origin main
```

### On server:
```bash
# Clone
sudo git clone https://github.com/chikiball/halalguideSingapore.git /home/nandha/server/sites/halalguideSingapore

# Copy nginx config
sudo cp /home/nandha/server/sites/halalguideSingapore/server-setup/nginx/halalguideSingapore.conf /home/nandha/server/nginx/conf.d/

# Build & start
cd /home/nandha/server/sites/halalguideSingapore
sudo docker compose up -d --build

# Reload nginx
sudo docker exec nginx-gateway nginx -s reload

# Verify
curl -sI https://halal.nandharu.uk | head -5
```

### In Cloudflare:
1. Zero Trust → Networks → Connectors → `home-server`
2. Public Hostname → Add: `halal.nandharu.uk` → HTTP → `nginx-gateway:80`

---

## 12. Known Limitations & Future Ideas

- **OSM data coverage:** Many SG halal places don't have `diet:halal` tag — relies on name/cuisine inference
- **Wikipedia false matches:** Generic "Singapore" articles may appear for unnamed places
- **No persistent cache:** Article cache resets on container restart — could add Redis or file cache
- **Crawl latency:** ~2-4s per place on first tap — could pre-crawl popular places
- **No user contributions:** Could add a "Suggest a place" feature
- **No MUIS verification:** Could integrate with Singapore MUIS halal certification database if API available
- **Image quality:** Fallback Unsplash images are generic — could improve with cuisine-specific search
- **Consider:** Adding prayer time API integration for nearby mosques
- **Consider:** Offline mode with service worker for cached results
