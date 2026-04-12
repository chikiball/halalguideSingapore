# 🕌 Halal Guide Singapore

A mobile-friendly web app to discover halal and Muslim-friendly food establishments near you in Singapore.

## Features

- 📍 **GPS Location** — Requests your current location to find nearby halal places
- 🗺️ **Interactive Map** — Leaflet + OpenStreetMap (100% free, no API key needed)
- 🔍 **Smart Search** — Queries OpenStreetMap's Overpass API for halal-tagged establishments
- 📱 **Mobile First** — Responsive card-based UI optimized for phones
- 🧭 **Directions** — One-tap navigation via Google Maps
- 🚀 **Deployed on fly.io** — Singapore region (`sin`) for low latency

## Tech Stack

| Layer     | Technology                                |
|-----------|-------------------------------------------|
| Backend   | Node.js + Express                         |
| Frontend  | Vanilla HTML/CSS/JS (no framework needed) |
| Map       | Leaflet.js + OpenStreetMap tiles           |
| Data      | Overpass API (OpenStreetMap)               |
| Deploy    | fly.io (Docker, Singapore region)         |

## Run Locally

```bash
npm install
npm start
# → http://localhost:3000
```

## Deploy to fly.io

```bash
# Install flyctl if you haven't
brew install flyctl

# Login
fly auth login

# Launch (first time)
fly launch          # say yes to use existing fly.toml

# Deploy (subsequent)
fly deploy

# Open in browser
fly open
```

## How It Works

1. User opens the app → prompted for GPS location
2. Leaflet map renders with OpenStreetMap tiles (free)
3. User taps **Search** → backend queries Overpass API for halal-tagged establishments
4. Results displayed as cards sorted by distance
5. Tap a card → detail sheet with directions, phone, hours, website

## Data Sources

The app queries OpenStreetMap via the Overpass API for:
- `diet:halal = yes | only | limited`
- `halal = yes`
- Cuisine tags: `halal`, `malay`, `indonesian`, `middle_eastern`, `arab`, `turkish`, `indian`, `pakistani`, `muslim`
- Name containing "halal" or "muslim"

> 💡 **Tip:** Contribute to OpenStreetMap to improve halal data coverage in Singapore!

## License

MIT
