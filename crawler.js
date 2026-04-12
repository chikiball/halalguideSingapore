/**
 * Place Detail Crawler
 * Crawls multiple free sources to gather info + images for a food establishment.
 *
 * Sources (all free, no API keys):
 *  1. Wikipedia API — search for article, extract summary + images
 *  2. DuckDuckGo Instant Answers — quick snippet
 *  3. Establishment website — extract og:image, meta description, text
 *
 * Then composes a warm, inviting article from the gathered data.
 */

var fetch = require("node-fetch");
var cheerio = require("cheerio");

// ─── Timeouts ───────────────────────────────────────────────────────────
var CRAWL_TIMEOUT = 8000;

function fetchWithTimeout(url, opts) {
  opts = opts || {};
  opts.timeout = opts.timeout || CRAWL_TIMEOUT;
  opts.headers = opts.headers || {};
  opts.headers["User-Agent"] =
    "HalalGuideSG/1.0 (halal food guide; educational project)";
  return fetch(url, opts);
}

// ─── 1. Wikipedia API ───────────────────────────────────────────────────
async function searchWikipedia(placeName, cuisine) {
  var result = { summary: "", images: [], url: "" };
  try {
    // Search for the place
    var searchQ = placeName + " restaurant Singapore";
    var searchUrl =
      "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=" +
      encodeURIComponent(searchQ) +
      "&srlimit=3&format=json";
    var searchRes = await fetchWithTimeout(searchUrl);
    var searchData = await searchRes.json();

    var pages = (searchData.query && searchData.query.search) || [];
    if (pages.length === 0) return result;

    var pageTitle = pages[0].title;
    result.url = "https://en.wikipedia.org/wiki/" + encodeURIComponent(pageTitle);

    // Get page summary + images
    var summaryUrl =
      "https://en.wikipedia.org/api/rest_v1/page/summary/" +
      encodeURIComponent(pageTitle);
    var summaryRes = await fetchWithTimeout(summaryUrl);
    if (summaryRes.ok) {
      var summaryData = await summaryRes.json();
      result.summary = summaryData.extract || "";
      if (summaryData.thumbnail && summaryData.thumbnail.source) {
        result.images.push({
          url: summaryData.thumbnail.source,
          caption: summaryData.title || placeName,
          source: "Wikipedia",
        });
      }
      if (summaryData.originalimage && summaryData.originalimage.source) {
        result.images.push({
          url: summaryData.originalimage.source,
          caption: summaryData.title || placeName,
          source: "Wikipedia",
        });
      }
    }
  } catch (err) {
    console.warn("Wikipedia crawl failed:", err.message);
  }
  return result;
}

// ─── 2. DuckDuckGo Instant Answer ──────────────────────────────────────
async function searchDuckDuckGo(placeName) {
  var result = { snippet: "", relatedTopics: [], images: [] };
  try {
    var q = placeName + " Singapore halal food";
    var url =
      "https://api.duckduckgo.com/?q=" +
      encodeURIComponent(q) +
      "&format=json&no_redirect=1&no_html=1&skip_disambig=1";
    var res = await fetchWithTimeout(url);
    var data = await res.json();

    result.snippet = data.Abstract || data.AbstractText || "";

    if (data.Image) {
      result.images.push({
        url: data.Image.startsWith("http")
          ? data.Image
          : "https://duckduckgo.com" + data.Image,
        caption: data.Heading || placeName,
        source: "DuckDuckGo",
      });
    }

    // Extract useful related topics
    var topics = data.RelatedTopics || [];
    for (var i = 0; i < Math.min(topics.length, 5); i++) {
      if (topics[i] && topics[i].Text) {
        result.relatedTopics.push(topics[i].Text);
      }
    }
  } catch (err) {
    console.warn("DuckDuckGo crawl failed:", err.message);
  }
  return result;
}

// ─── 3. Scrape establishment website ────────────────────────────────────
async function scrapeWebsite(websiteUrl) {
  var result = { description: "", images: [], title: "" };
  if (!websiteUrl) return result;

  try {
    // Normalise URL
    if (!websiteUrl.startsWith("http")) {
      websiteUrl = "https://" + websiteUrl;
    }

    var res = await fetchWithTimeout(websiteUrl, { timeout: 6000 });
    if (!res.ok) return result;

    var contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("text/html")) return result;

    var html = await res.text();
    var $ = cheerio.load(html);

    // Extract meta information
    result.title =
      $('meta[property="og:title"]').attr("content") ||
      $("title").text() ||
      "";
    result.description =
      $('meta[property="og:description"]').attr("content") ||
      $('meta[name="description"]').attr("content") ||
      "";

    // Extract og:image
    var ogImage = $('meta[property="og:image"]').attr("content");
    if (ogImage) {
      // Make absolute URL
      if (ogImage.startsWith("//")) ogImage = "https:" + ogImage;
      else if (ogImage.startsWith("/")) {
        var base = new URL(websiteUrl);
        ogImage = base.origin + ogImage;
      }
      result.images.push({
        url: ogImage,
        caption: result.title || "Restaurant photo",
        source: "Website",
      });
    }

    // Try to find hero/header images
    var imgSelectors = [
      'img[class*="hero"]',
      'img[class*="banner"]',
      'img[class*="header"]',
      'img[class*="logo"]',
      ".hero img",
      ".banner img",
      "header img",
    ];
    for (var s = 0; s < imgSelectors.length; s++) {
      var img = $(imgSelectors[s]).first();
      if (img.length) {
        var src = img.attr("src") || img.attr("data-src");
        if (src && !src.includes("svg") && !src.includes("icon")) {
          if (src.startsWith("//")) src = "https:" + src;
          else if (src.startsWith("/")) {
            var baseUrl = new URL(websiteUrl);
            src = baseUrl.origin + src;
          }
          if (src.startsWith("http")) {
            result.images.push({
              url: src,
              caption: img.attr("alt") || "Restaurant",
              source: "Website",
            });
          }
        }
      }
    }
  } catch (err) {
    console.warn("Website crawl failed:", err.message);
  }
  return result;
}

// ─── 4. DuckDuckGo HTML search for extra snippets ───────────────────────
async function searchWebSnippets(placeName) {
  var snippets = [];
  try {
    var q = placeName + " Singapore halal restaurant review";
    var url = "https://html.duckduckgo.com/html/?q=" + encodeURIComponent(q);
    var res = await fetchWithTimeout(url, {
      headers: {
        "User-Agent":
          "HalalGuideSG/1.0 (halal food guide; educational project)",
        Accept: "text/html",
      },
    });
    var html = await res.text();
    var $ = cheerio.load(html);

    $(".result__snippet").each(function (i) {
      if (i >= 5) return false;
      var text = $(this).text().trim();
      if (text && text.length > 30) {
        snippets.push(text);
      }
    });
  } catch (err) {
    console.warn("Web snippets crawl failed:", err.message);
  }
  return snippets;
}

// ─── 5. Cuisine-based fallback images ───────────────────────────────────
var CUISINE_IMAGES = {
  malay: "https://images.unsplash.com/photo-1562279972-096e1e2e3afc?w=600&q=80",
  indonesian: "https://images.unsplash.com/photo-1585032226651-759b368d7246?w=600&q=80",
  indian: "https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=600&q=80",
  middle_eastern: "https://images.unsplash.com/photo-1541518763669-27fef04b14ea?w=600&q=80",
  arab: "https://images.unsplash.com/photo-1541518763669-27fef04b14ea?w=600&q=80",
  turkish: "https://images.unsplash.com/photo-1599487488170-d11ec9c172f0?w=600&q=80",
  burger: "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=600&q=80",
  japanese: "https://images.unsplash.com/photo-1553621042-f6e147245754?w=600&q=80",
  kebab: "https://images.unsplash.com/photo-1529006557810-274b9b2fc783?w=600&q=80",
  seafood: "https://images.unsplash.com/photo-1615141982883-c7ad0e69fd62?w=600&q=80",
  chinese: "https://images.unsplash.com/photo-1552566626-52f8b828add9?w=600&q=80",
  default: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600&q=80",
};

function getCuisineFallbackImage(cuisine) {
  if (!cuisine) return CUISINE_IMAGES.default;
  var c = cuisine.toLowerCase();
  var keys = Object.keys(CUISINE_IMAGES);
  for (var i = 0; i < keys.length; i++) {
    if (c.indexOf(keys[i]) !== -1) return CUISINE_IMAGES[keys[i]];
  }
  return CUISINE_IMAGES.default;
}

// ─── 6. Article Composer ────────────────────────────────────────────────
function composeArticle(place, wiki, ddg, website, snippets) {
  var name = place.name;
  var cuisine = place.cuisine;
  var type = place.type;
  var address = place.address;
  var halalStatus = place.halalStatus;

  // Collect all info snippets
  var infoPool = [];
  if (website.description) infoPool.push(website.description);
  if (wiki.summary) infoPool.push(wiki.summary);
  if (ddg.snippet) infoPool.push(ddg.snippet);
  snippets.forEach(function (s) { infoPool.push(s); });
  ddg.relatedTopics.forEach(function (t) { infoPool.push(t); });

  // Deduplicate and clean
  var seen = {};
  infoPool = infoPool.filter(function (text) {
    var key = text.substring(0, 50).toLowerCase();
    if (seen[key]) return false;
    seen[key] = true;
    return text.length > 20;
  });

  // Format cuisine nicely
  var cuisineStr = "";
  if (cuisine) {
    cuisineStr = cuisine
      .split(";")
      .map(function (c) {
        return c.trim().replace(/_/g, " ").replace(/\b\w/g, function (l) {
          return l.toUpperCase();
        });
      })
      .join(", ");
  }

  // Build article sections
  var article = [];

  // Opening
  var openings = [
    "Nestled in the heart of Singapore, **" + name + "** is a welcoming spot for anyone seeking delicious halal-friendly food.",
    "Looking for a great halal dining experience? **" + name + "** is a hidden gem worth discovering in Singapore.",
    "**" + name + "** brings together flavour and warmth, making it a favourite among halal food lovers in Singapore.",
    "Whether you're a local or just visiting, **" + name + "** offers a comforting and authentic halal dining experience.",
  ];
  article.push(openings[Math.floor(Math.random() * openings.length)]);

  // Cuisine info
  if (cuisineStr) {
    article.push(
      "Specialising in **" + cuisineStr + "** cuisine, this " +
      formatTypeSimple(type) +
      " serves up dishes that celebrate rich culinary traditions."
    );
  }

  // Halal status
  if (halalStatus === "yes" || halalStatus === "only") {
    article.push(
      "🕌 This establishment is **halal-certified**, so you can dine with complete peace of mind."
    );
  } else if (halalStatus === "likely") {
    article.push(
      "🟢 Based on its cuisine and menu, this spot is considered **Muslim-friendly**. We recommend confirming halal certification directly with the establishment."
    );
  }

  // Crawled information
  if (infoPool.length > 0) {
    article.push(""); // spacer
    article.push("### What People Say");
    // Pick the best 3 snippets
    var bestSnippets = infoPool.slice(0, 3);
    bestSnippets.forEach(function (s) {
      // Clean up the snippet
      var clean = s.replace(/\s+/g, " ").trim();
      if (clean.length > 300) clean = clean.substring(0, 297) + "...";
      article.push("> " + clean);
    });
  }

  // Address
  if (address) {
    article.push("");
    article.push("📍 **Location:** " + address);
  }

  // Opening hours
  if (place.openingHours) {
    article.push("🕐 **Hours:** " + place.openingHours);
  }

  // Closing
  var closings = [
    "Drop by and experience the warmth and flavours for yourself! 🍽️",
    "Whether it's a quick bite or a leisurely meal, this place won't disappoint. Enjoy! 😊",
    "Add this to your halal food trail in Singapore — you'll be glad you did! ✨",
    "A wonderful choice for your next meal. Selamat makan! 🤲",
  ];
  article.push("");
  article.push(closings[Math.floor(Math.random() * closings.length)]);

  return article.join("\n\n");
}

function formatTypeSimple(type) {
  var map = {
    restaurant: "restaurant",
    fast_food: "fast food spot",
    cafe: "café",
    food_court: "food court stall",
    butcher: "halal butcher",
    supermarket: "supermarket",
  };
  return map[type] || "establishment";
}

// ─── Main: Fetch place details ──────────────────────────────────────────
async function fetchPlaceDetails(place) {
  console.log("🔍 Crawling details for:", place.name);

  // Run all crawls in parallel
  var results = await Promise.all([
    searchWikipedia(place.name, place.cuisine),
    searchDuckDuckGo(place.name),
    scrapeWebsite(place.website),
    searchWebSnippets(place.name),
  ]);

  var wiki = results[0];
  var ddg = results[1];
  var website = results[2];
  var snippets = results[3];

  // Collect all images, deduplicate by URL
  var allImages = []
    .concat(website.images)
    .concat(wiki.images)
    .concat(ddg.images);

  var seenUrls = {};
  var images = allImages.filter(function (img) {
    if (!img || !img.url || seenUrls[img.url]) return false;
    seenUrls[img.url] = true;
    return true;
  });

  // Add cuisine fallback if no images found
  if (images.length === 0) {
    images.push({
      url: getCuisineFallbackImage(place.cuisine),
      caption: place.cuisine
        ? "Delicious " + place.cuisine.split(";")[0] + " cuisine"
        : "Halal food in Singapore",
      source: "Unsplash",
    });
  }

  // Compose the article
  var article = composeArticle(place, wiki, ddg, website, snippets);

  var detail = {
    article: article,
    images: images,
    sources: {
      wikipedia: wiki.url || null,
      website: place.website || null,
    },
  };

  console.log(
    "✅ Crawled:",
    place.name,
    "- images:",
    images.length,
    "- article:",
    article.length,
    "chars"
  );

  return detail;
}

module.exports = {
  fetchPlaceDetails: fetchPlaceDetails,
};
