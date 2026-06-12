# 🕌 Halal Guide Singapore

A mobile-friendly web app to discover halal and Muslim-friendly food establishments near you in Singapore. It pairs **OpenStreetMap** for fast geographic discovery with an **AI agent** that researches each place and classifies its halal status.

## Features

- 📍 **GPS or pick-on-map location** — find places near you or anywhere you tap
- 🗺️ **Mapbox map** — Mapbox Streets basemap (data still from OpenStreetMap)
- 🤖 **AI halal research** — each place is researched and classified live: Halal Certified, Muslim Owned, No Pork No Lard, Halal Friendly, Vegetarian, Vegan, or Unverified
- ✨ **Progressive results** — cards appear as each place is verified; pork-serving spots are filtered out
- 📱 **Mobile first** — responsive card-based UI
- 🧭 **Directions** — one-tap navigation via Google Maps

## Tech Stack

| Layer       | Technology                                              |
|-------------|---------------------------------------------------------|
| Web app     | Node.js + Express (serves UI, OSM proxy, SSE proxy)     |
| AI agent    | Python + FastAPI (`agent-service/`)                     |
| LLM         | DeepSeek (`deepseek-chat`, OpenAI-compatible API)       |
| Web search  | Self-hosted SearXNG                                     |
| Map data    | OpenStreetMap via the Overpass API                      |
| Map tiles   | Mapbox Streets (Leaflet.js)                             |
| Geocoding   | Nominatim (OpenStreetMap)                               |
| Deploy      | Docker Compose                                          |

## How It Works

1. User opens the app → grants GPS or picks a spot on the map
2. The app queries OpenStreetMap's **Overpass API** for nearby food places (real coordinates)
3. For each place, the **AI agent** searches the web (SearXNG), scrapes pages, checks the **MUIS** halal directory, and classifies its halal status with an LLM
4. Cards appear progressively with a halal badge as each place is verified; places with pork evidence are excluded
5. Tap a card → an AI-written summary plus details and directions

## Run Locally

**Node.js app only (OSM map + search, no AI):**
```bash
npm install
npm start          # http://localhost:3000
```

**Full stack (with the AI agent):**
```bash
cp .env.example .env          # set DEEPSEEK_API_KEY and MAPBOX_TOKEN
docker network create server-net   # one-time, external network
docker compose up -d          # app + agent + searxng
```

> Without `MAPBOX_TOKEN` the map falls back to plain OpenStreetMap tiles. Without `DEEPSEEK_API_KEY` the AI research calls will fail.

## Deploy

Deployment to the server is handled by:
```bash
sudo bash server-setup/scripts/deploy-ai.sh
```
It runs preflight checks, pulls, builds the Docker stack, reloads nginx, and runs health/integration checks. See [`CLAUDE.md`](./CLAUDE.md) for the full architecture and operational notes.

## Data Sources

- **OpenStreetMap / Overpass API** — establishment discovery (cuisine, `diet:halal`/`halal` tags, names)
- **MUIS** (`halal.muis.gov.sg`) — official halal certification lookup
- **Web search + scraping** (SearXNG) — menus, reviews, halal directories, evidence for classification

> 💡 **Tip:** Contribute to OpenStreetMap to improve halal data coverage in Singapore!

## License

MIT
