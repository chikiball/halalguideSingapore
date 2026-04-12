var express = require("express");
var fetch = require("node-fetch");
var path = require("path");
var crawler = require("./crawler");

var app = express();
var PORT = process.env.PORT || 3000;

// Serve static files
app.use(express.static(path.join(__dirname, "public")));
app.use(express.json());

// ─── Overpass API mirrors (fallback chain) ─────────────────────────────
var OVERPASS_ENDPOINTS = [
  "https://overpass.kumi.systems/api/interpreter",
  "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
  "https://overpass-api.de/api/interpreter",
];

function queryOverpass(overpassQL) {
  var idx = 0;

  function tryNext() {
    if (idx >= OVERPASS_ENDPOINTS.length) {
      return Promise.reject(new Error("All Overpass mirrors failed"));
    }
    var endpoint = OVERPASS_ENDPOINTS[idx];
    idx++;
    console.log("  → Trying:", endpoint);

    return fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "data=" + encodeURIComponent(overpassQL),
      timeout: 25000,
    }).then(function (res) {
      if (res.ok) return res.json();
      console.warn("  ⚠️", endpoint, "returned", res.status);
      return tryNext();
    }).catch(function (err) {
      console.warn("  ⚠️", endpoint, "error:", err.message);
      return tryNext();
    });
  }

  return tryNext();
}

// ─── Halal / Muslim-friendly detection ─────────────────────────────────
// Singapore has limited diet:halal tagging, so we use a broad heuristic
var HALAL_CUISINE_RE = /halal|malay|indonesian|middle.?eastern|arab|turkish|pakistani|muslim|persian|afghan|bangladeshi|lebanese|egyptian|moroccan|yemeni|somali|indian|north.?indian|south.?indian|mughlai|biryani|kebab|shawarma|falafel|mediterranean/i;
var HALAL_NAME_RE = /halal|muslim|nasi|mee|roti|prata|briyani|biryani|murtabak|satay|rendang|ayam|kambing|padang|minang|warung|zam.?zam|mamak|tandoori|tikka|kebab|shawarma|naan|chapati|thosai|dosai|murukku|sup|soto|laksa|mee.?goreng|nasi.?goreng|nasi.?lemak|nasi.?padang|teh.?tarik|masjid|mosque|kampong|kampung/i;

function isHalalFriendly(tags) {
  if (!tags) return false;

  // Explicit halal tags
  if (tags["diet:halal"] === "yes" || tags["diet:halal"] === "only" || tags["diet:halal"] === "limited") return true;
  if (tags.halal === "yes") return true;

  // Explicitly NOT halal
  if (tags["diet:halal"] === "no" || tags.halal === "no") return false;

  // Cuisine-based
  if (tags.cuisine && HALAL_CUISINE_RE.test(tags.cuisine)) return true;

  // Name-based
  if (tags.name && HALAL_NAME_RE.test(tags.name)) return true;

  // Brand/operator hints
  if (tags.brand && HALAL_NAME_RE.test(tags.brand)) return true;
  if (tags.operator && HALAL_NAME_RE.test(tags.operator)) return true;

  return false;
}

function getHalalStatus(tags) {
  if (tags["diet:halal"] === "yes" || tags.halal === "yes") return "yes";
  if (tags["diet:halal"] === "only") return "only";
  if (tags["diet:halal"] === "limited") return "limited";
  // Inferred from cuisine/name
  return "likely";
}

// ─── Halal search API ──────────────────────────────────────────────────
app.get("/api/halal", function (req, res) {
  var lat = req.query.lat;
  var lng = req.query.lng;
  var radius = req.query.radius || 1500;

  if (!lat || !lng) {
    return res.status(400).json({ error: "lat and lng are required" });
  }

  console.log("🔍 Search: lat=" + lat + " lng=" + lng + " radius=" + radius + "m");

  // Fetch ALL food establishments, then filter server-side
  // This is much more reliable for Singapore's OSM data
  var overpassQuery = [
    "[out:json][timeout:25];",
    "(",
    '  node["amenity"~"restaurant|fast_food|cafe|food_court"](around:' + radius + "," + lat + "," + lng + ");",
    '  way["amenity"~"restaurant|fast_food|cafe|food_court"](around:' + radius + "," + lat + "," + lng + ");",
    '  node["shop"~"butcher|supermarket"]["diet:halal"~"yes|only"](around:' + radius + "," + lat + "," + lng + ");",
    ");",
    "out center body;",
  ].join("\n");

  queryOverpass(overpassQuery)
    .then(function (data) {
      // Filter for halal/Muslim-friendly places
      var halalPlaces = data.elements.filter(function (el) {
        return isHalalFriendly(el.tags);
      });

      // Normalise results
      var places = halalPlaces.map(function (el) {
        var tags = el.tags || {};
        var centerLat = el.lat || (el.center && el.center.lat);
        var centerLng = el.lon || (el.center && el.center.lon);

        return {
          id: el.id,
          name: tags.name || tags["name:en"] || "Unnamed Establishment",
          lat: centerLat,
          lng: centerLng,
          type: tags.amenity || tags.shop || "establishment",
          cuisine: tags.cuisine || "",
          halalStatus: getHalalStatus(tags),
          address:
            [tags["addr:street"], tags["addr:housenumber"], tags["addr:postcode"]]
              .filter(Boolean)
              .join(", ") ||
            tags["addr:full"] ||
            "",
          phone: tags.phone || tags["contact:phone"] || "",
          website: tags.website || tags["contact:website"] || "",
          openingHours: tags.opening_hours || "",
          operator: tags.operator || "",
          brand: tags.brand || "",
          description: tags.description || "",
        };
      });

      // Deduplicate by name + approximate location
      var seen = {};
      var unique = places.filter(function (p) {
        var key = p.name.toLowerCase() + "_" + Math.round(p.lat * 1000) + "_" + Math.round(p.lng * 1000);
        if (seen[key]) return false;
        seen[key] = true;
        return true;
      });

      console.log("✅ Found " + unique.length + " halal places (from " + data.elements.length + " total)");
      res.json({ count: unique.length, places: unique });
    })
    .catch(function (err) {
      console.error("❌ Overpass error:", err.message);
      res.status(502).json({
        error: "Failed to fetch data from OpenStreetMap",
        detail: err.message,
      });
    });
});

// ─── Place detail crawling API ─────────────────────────────────────────
// Simple in-memory cache to avoid re-crawling the same place
var detailCache = {};

app.post("/api/place/details", function (req, res) {
  var place = req.body;
  if (!place || !place.name) {
    return res.status(400).json({ error: "Place data is required" });
  }

  // Cache key: name + approximate lat/lng
  var cacheKey =
    place.name.toLowerCase() +
    "_" +
    Math.round((place.lat || 0) * 1000) +
    "_" +
    Math.round((place.lng || 0) * 1000);

  if (detailCache[cacheKey]) {
    console.log("📦 Cache hit:", place.name);
    return res.json(detailCache[cacheKey]);
  }

  crawler
    .fetchPlaceDetails(place)
    .then(function (details) {
      detailCache[cacheKey] = details;
      res.json(details);
    })
    .catch(function (err) {
      console.error("❌ Crawl error:", err.message);
      res.status(500).json({ error: "Failed to fetch details", detail: err.message });
    });
});

// SPA fallback
app.get("*", function (_req, res) {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

app.listen(PORT, function () {
  console.log("🕌 Halal Guide Singapore running on http://localhost:" + PORT);
});
