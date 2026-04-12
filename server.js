const express = require("express");
const fetch = require("node-fetch");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3000;

// Serve static files
app.use(express.static(path.join(__dirname, "public")));

// ─── Overpass API proxy ────────────────────────────────────────────────
// Searches OpenStreetMap for halal / Muslim-friendly food establishments
// within a radius of the user's current location.
app.get("/api/halal", async (req, res) => {
  const { lat, lng, radius = 1500 } = req.query;

  if (!lat || !lng) {
    return res.status(400).json({ error: "lat and lng are required" });
  }

  // Overpass QL – searches for:
  //   • diet:halal = yes / only / limited
  //   • halal = yes
  //   • cuisine containing "halal" or "malay" or "indonesian" or "middle_eastern" or "arab" or "turkish" or "indian"
  //   • name containing "halal" (case-insensitive)
  const overpassQuery = `
    [out:json][timeout:30];
    (
      node["amenity"~"restaurant|fast_food|cafe|food_court"]["diet:halal"~"yes|only|limited"](around:${radius},${lat},${lng});
      way["amenity"~"restaurant|fast_food|cafe|food_court"]["diet:halal"~"yes|only|limited"](around:${radius},${lat},${lng});
      node["amenity"~"restaurant|fast_food|cafe|food_court"]["halal"="yes"](around:${radius},${lat},${lng});
      way["amenity"~"restaurant|fast_food|cafe|food_court"]["halal"="yes"](around:${radius},${lat},${lng});
      node["amenity"~"restaurant|fast_food|cafe|food_court"]["cuisine"~"halal|malay|indonesian|middle_eastern|arab|turkish|indian|pakistani|muslim",i](around:${radius},${lat},${lng});
      way["amenity"~"restaurant|fast_food|cafe|food_court"]["cuisine"~"halal|malay|indonesian|middle_eastern|arab|turkish|indian|pakistani|muslim",i](around:${radius},${lat},${lng});
      node["amenity"~"restaurant|fast_food|cafe|food_court"]["name"~"halal|muslim",i](around:${radius},${lat},${lng});
      way["amenity"~"restaurant|fast_food|cafe|food_court"]["name"~"halal|muslim",i](around:${radius},${lat},${lng});
      node["shop"~"butcher|supermarket"]["diet:halal"~"yes|only"](around:${radius},${lat},${lng});
      way["shop"~"butcher|supermarket"]["diet:halal"~"yes|only"](around:${radius},${lat},${lng});
    );
    out center body;
  `;

  try {
    const response = await fetch("https://overpass-api.de/api/interpreter", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: `data=${encodeURIComponent(overpassQuery)}`,
    });

    if (!response.ok) {
      throw new Error(`Overpass API returned ${response.status}`);
    }

    const data = await response.json();

    // Normalise results into a clean format
    const places = data.elements.map((el) => {
      const tags = el.tags || {};
      const centerLat = el.lat || (el.center && el.center.lat);
      const centerLng = el.lon || (el.center && el.center.lon);

      return {
        id: el.id,
        name: tags.name || tags["name:en"] || "Unnamed Establishment",
        lat: centerLat,
        lng: centerLng,
        type: tags.amenity || tags.shop || "establishment",
        cuisine: tags.cuisine || "",
        halalStatus: tags["diet:halal"] || tags.halal || "listed",
        address: [tags["addr:street"], tags["addr:housenumber"], tags["addr:postcode"]]
          .filter(Boolean)
          .join(", ") || tags["addr:full"] || "",
        phone: tags.phone || tags["contact:phone"] || "",
        website: tags.website || tags["contact:website"] || "",
        openingHours: tags.opening_hours || "",
        operator: tags.operator || "",
        brand: tags.brand || "",
        description: tags.description || "",
      };
    });

    // Deduplicate by name + approximate location
    const seen = new Set();
    const unique = places.filter((p) => {
      const key = `${p.name.toLowerCase()}_${Math.round(p.lat * 1000)}_${Math.round(p.lng * 1000)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    res.json({ count: unique.length, places: unique });
  } catch (err) {
    console.error("Overpass error:", err.message);
    res.status(502).json({ error: "Failed to fetch data from OpenStreetMap", detail: err.message });
  }
});

// SPA fallback
app.get("*", (_req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

app.listen(PORT, () => {
  console.log(`🕌 Halal Guide Singapore running on http://localhost:${PORT}`);
});
