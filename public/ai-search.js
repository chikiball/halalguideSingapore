/**
 * AI Search Module — Hybrid Approach
 *
 * Single search flow: OSM (Overpass) for geographic discovery + AI for research.
 * No mode toggle — just one Search button.
 *
 * Flow:
 *   1. User taps Search → pulsating ✨ "AI is performing search for halal food"
 *   2. Overpass API finds restaurants with real coordinates (~2s)
 *   3. Cards appear on map immediately
 *   4. AI agent researches each place in background (classification, article)
 *   5. Cards update progressively with halal badges
 *   6. Tap card → full AI article + details
 */

(function () {
  "use strict";

  // ─── State ───
  let aiResearchCache = {};
  let currentPlaces = []; // shared reference to the places array

  // ─── Badge config for AI classifications ───
  const AI_BADGES = {
    halal_certified:  { label: "Halal Certified", icon: "☪️", cls: "badge-halal" },
    muslim_owned:     { label: "Muslim Owned", icon: "🟢", cls: "badge-halal" },
    no_pork_no_lard:  { label: "No Pork No Lard", icon: "🚫🐷", cls: "badge-likely" },
    halal_friendly:   { label: "Halal Friendly", icon: "🔵", cls: "badge-likely" },
    vegetarian:       { label: "Vegetarian", icon: "🌿", cls: "badge-vegan" },
    vegan:            { label: "Vegan", icon: "🌱", cls: "badge-vegan" },
    unverified:       { label: "Unverified", icon: "⚪", cls: "badge-unverified" },
  };

  // ─── Inject CSS ───
  const style = document.createElement("style");
  style.textContent = `
    .badge-vegan { background: #e0f2f1; color: #00695c; }
    .badge-unverified { background: #f5f5f5; color: #9e9e9e; }

    .ai-loading-bar {
      padding: 12px 20px;
      font-size: 14px;
      color: #1a6b4a;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .ai-loading-bar .pulse {
      display: inline-block;
      animation: aiPulse 1.2s ease-in-out infinite;
      font-size: 20px;
    }
    @keyframes aiPulse {
      0%, 100% { opacity: 0.4; transform: scale(0.9); }
      50% { opacity: 1; transform: scale(1.2); }
    }

    .card-research-status {
      font-size: 11px;
      color: #5a5a7a;
      margin-top: 4px;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .card-research-status .mini-pulse {
      display: inline-block;
      animation: aiPulse 1.2s ease-in-out infinite;
      font-size: 12px;
    }

    .ai-article-section {
      padding: 16px 20px;
      border-top: 1px solid #f0f0f0;
    }
    .ai-article-section h3 {
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 8px;
      color: #1a1a2e;
    }
    .ai-article-section .ai-tags {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-top: 10px;
    }
    .ai-article-section .ai-tag {
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 12px;
      background: #f0f0f0;
      color: #555;
    }
    .ai-confidence {
      font-size: 12px;
      margin-top: 6px;
      padding: 6px 10px;
      border-radius: 8px;
      background: #f8f9fa;
    }
    .ai-confidence .level-high { color: #2e7d32; font-weight: 600; }
    .ai-confidence .level-medium { color: #f57f17; font-weight: 600; }
    .ai-confidence .level-low { color: #c62828; font-weight: 600; }
  `;
  document.head.appendChild(style);

  // ─── Override searchHalal with hybrid approach ───
  const _origSearchHalal = window.searchHalal;

  window.searchHalal = async function () {
    const radius = document.getElementById("radiusSelect").value;
    const loader = document.getElementById("loader");
    const emptyState = document.getElementById("emptyState");
    const cardsEl = document.getElementById("cards");
    const statusBar = document.getElementById("statusBar");
    const searchBtn = document.getElementById("searchBtn");

    // Reset
    emptyState.classList.remove("active");
    cardsEl.innerHTML = "";
    searchBtn.disabled = true;
    currentPlaces = [];
    if (window.markersLayer) window.markersLayer.clearLayers();

    // Show pulsating AI loading
    loader.classList.remove("active");
    statusBar.innerHTML = `
      <div class="ai-loading-bar">
        <span class="pulse">✨</span>
        AI is performing search for halal food...
      </div>
    `;

    try {
      // ───── STEP 1: OSM Discovery (fast, geographic) ─────
      const lat = window.searchLat;
      const lng = window.searchLng;
      if (!lat || !lng) {
        statusBar.innerHTML = "⚠️ Please select a location first";
        searchBtn.disabled = false;
        return;
      }

      // Fetch ALL food places (not just halal-filtered) — AI will classify
      const osmRes = await fetch(`/api/halal?lat=${lat}&lng=${lng}&radius=${radius}&all=true`);
      const osmData = await osmRes.json();

      if (!osmRes.ok) throw new Error(osmData.error || "Search failed");

      let places = osmData.places || [];

      // Sort by distance
      places.forEach((p) => {
        p.distance = window.getDistance ? getDistance(lat, lng, p.lat, p.lng) : 0;
      });
      places.sort((a, b) => a.distance - b.distance);

      if (places.length === 0) {
        emptyState.classList.add("active");
        statusBar.innerHTML = "No food places found nearby. Try a larger radius.";
        searchBtn.disabled = false;
        return;
      }

      // Store reference
      currentPlaces = places;
      window.places = places; // for the original modal to work

      statusBar.innerHTML = `
        <div class="ai-loading-bar">
          <span class="pulse">✨</span>
          Found ${places.length} places — AI is researching halal status...
        </div>
      `;

      // ───── STEP 2: Render cards + map markers immediately ─────
      places.forEach((place, i) => {
        renderHybridCard(place, i, cardsEl);

        if (window.markersLayer && window.L) {
          const icon = L.divIcon({
            className: "",
            html: '<div style="width:30px;height:30px;background:#1a6b4a;border:2px solid white;border-radius:50%;box-shadow:0 2px 8px rgba(0,0,0,0.2);display:flex;align-items:center;justify-content:center;font-size:15px;">🍽️</div>',
            iconSize: [30, 30],
            iconAnchor: [15, 15],
          });
          const marker = L.marker([place.lat, place.lng], { icon: icon })
            .addTo(window.markersLayer)
            .bindPopup("<b>" + escHtml(place.name) + "</b>");
          marker.on("click", function () { openHybridModal(i); });
        }
      });

      // Fit map bounds
      if (window.map && window.L) {
        const bounds = L.latLngBounds(places.map((p) => [p.lat, p.lng]));
        bounds.extend([lat, lng]);
        map.fitBounds(bounds, { padding: [40, 40] });
      }

      // ───── STEP 3: AI research on each place (background) ─────
      let researchedCount = 0;
      const researchPromises = places.map(async (place, i) => {
        try {
          const result = await researchPlace(place);
          researchedCount++;

          // Update card badge
          if (result && result.classification) {
            updateCardBadge(i, result.classification);
          }

          // Update status
          statusBar.innerHTML = `
            <div class="ai-loading-bar">
              <span class="pulse">✨</span>
              Researching... ${researchedCount}/${places.length} places done
            </div>
          `;
        } catch (e) {
          console.warn("Research failed for", place.name, e);
        }
      });

      // Wait for all research to complete
      await Promise.all(researchPromises);

      // Final status
      statusBar.innerHTML = `Found <span class="count">${places.length}</span> place${places.length > 1 ? "s" : ""} — AI research complete ✨`;

    } catch (err) {
      statusBar.innerHTML = `⚠️ ${err.message}`;
      console.error("Hybrid search error:", err);
    }

    searchBtn.disabled = false;
  };

  // ─── Research a single place via AI agent ───
  async function researchPlace(place) {
    const cacheKey = place.name + "_" + (place.lat || 0).toFixed(3);
    if (aiResearchCache[cacheKey]) return aiResearchCache[cacheKey];

    try {
      const response = await fetch("/api/ai/place/details", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(place),
      });

      if (!response.ok) return null;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let research = null;
      let article = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.classification) research = data;
            if (data.article || data.title) article = data;
          } catch (e) {}
        }
      }

      const result = { research, article, classification: research?.classification || null };
      aiResearchCache[cacheKey] = result;
      return result;

    } catch (e) {
      console.warn("Research API error:", e);
      return null;
    }
  }

  // ─── Render hybrid card ───
  function renderHybridCard(place, index, container) {
    const card = document.createElement("div");
    card.className = "card";
    card.onclick = function () { openHybridModal(index); };
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    card.id = "hybrid-card-" + index;

    const distStr = place.distance < 1000
      ? Math.round(place.distance) + "m away"
      : (place.distance / 1000).toFixed(1) + "km away";

    card.innerHTML = `
      <div class="card-header">
        <div class="card-name">${escHtml(place.name)}</div>
        <span class="card-badge badge-unverified" id="badge-${index}">⚪ Checking...</span>
      </div>
      ${place.cuisine ? '<div class="card-cuisine">🍴 ' + escHtml(formatCuisine(place.cuisine)) + "</div>" : ""}
      <div class="card-distance">📍 ${distStr}</div>
      ${place.address ? '<div class="card-address">' + escHtml(place.address) + "</div>" : ""}
      <div class="card-research-status" id="research-status-${index}">
        <span class="mini-pulse">✨</span> AI researching halal status...
      </div>
    `;
    container.appendChild(card);
  }

  // ─── Update card badge after research ───
  function updateCardBadge(index, classification) {
    const status = classification.status || "unverified";
    const badge = AI_BADGES[status] || AI_BADGES.unverified;

    const badgeEl = document.getElementById("badge-" + index);
    if (badgeEl) {
      badgeEl.className = "card-badge " + badge.cls;
      badgeEl.innerHTML = badge.icon + " " + badge.label;
    }

    const statusEl = document.getElementById("research-status-" + index);
    if (statusEl) {
      const conf = classification.confidence || "low";
      statusEl.innerHTML = `✨ ${badge.label} — ${conf} confidence`;
      statusEl.style.color = "#1a6b4a";
    }

    if (currentPlaces[index]) {
      currentPlaces[index].halalStatus = status;
      currentPlaces[index].aiClassification = classification;
    }
  }

  // ─── Open hybrid modal ───
  function openHybridModal(index) {
    const p = currentPlaces[index];
    if (!p) return;

    const distStr = p.distance < 1000
      ? Math.round(p.distance) + "m away"
      : (p.distance / 1000).toFixed(1) + "km away";

    const classification = p.aiClassification || {};
    const status = classification.status || p.halalStatus || "unverified";
    const badge = AI_BADGES[status] || AI_BADGES.unverified;

    // Header
    document.getElementById("modalHeader").innerHTML = `
      <h2>${escHtml(p.name)}</h2>
      <div class="modal-badges">
        <span class="card-badge ${badge.cls}">${badge.icon} ${badge.label}</span>
        ${p.type ? '<span class="card-badge badge-type">' + formatType(p.type) + '</span>' : ''}
      </div>
    `;

    // Quick info
    let bodyHtml = "";
    const rows = [
      { icon: "📍", label: "Distance", value: distStr },
      p.cuisine && { icon: "🍴", label: "Cuisine", value: formatCuisine(p.cuisine) },
      p.address && { icon: "🏠", label: "Address", value: p.address },
      p.openingHours && { icon: "🕐", label: "Hours", value: p.openingHours },
      p.phone && { icon: "📞", label: "Phone", value: '<a href="tel:' + escHtml(p.phone) + '">' + escHtml(p.phone) + '</a>' },
      p.website && { icon: "🌐", label: "Website", value: '<a href="' + escHtml(p.website) + '" target="_blank">Visit</a>' },
    ].filter(Boolean);

    rows.forEach(function (r) {
      bodyHtml += '<div class="detail-row"><div class="detail-icon">' + r.icon + '</div><div class="detail-content"><div class="detail-label">' + r.label + '</div><div class="detail-value">' + (r.value.includes("<a") ? r.value : escHtml(r.value)) + '</div></div></div>';
    });
    document.getElementById("modalBody").innerHTML = bodyHtml;

    // Actions
    document.getElementById("modalActions").innerHTML = `
      <button class="btn btn-primary" onclick="navigateTo(${p.lat}, ${p.lng})">🧭 Directions</button>
      <button class="btn btn-outline" onclick="panTo(${p.lat}, ${p.lng})">🗺️ Show on Map</button>
    `;

    // Check if AI research is available
    const cacheKey = p.name + "_" + (p.lat || 0).toFixed(3);
    const cached = aiResearchCache[cacheKey];

    if (cached) {
      renderResearchInModal(cached, p);
    } else {
      // Show loading
      document.getElementById("modalGallery").innerHTML = '<div class="shimmer shimmer-img" style="flex-shrink:0;"></div>';
      document.getElementById("modalArticle").innerHTML = `
        <div class="ai-loading-bar">
          <span class="pulse">✨</span> AI is researching ${escHtml(p.name)}...
        </div>
        <div class="shimmer shimmer-title" style="margin-top:12px;"></div>
        <div class="shimmer shimmer-line"></div>
        <div class="shimmer shimmer-line-med"></div>
      `;
      document.getElementById("modalSources").innerHTML = "";

      // Trigger research if not already running
      researchPlace(p).then(function (result) {
        if (result) {
          renderResearchInModal(result, p);
          updateCardBadge(index, result.classification || {});
        }
      });
    }

    // Open modal
    document.getElementById("modalOverlay").classList.add("active");
    document.body.style.overflow = "hidden";
  }

  // ─── Render research results in modal ───
  function renderResearchInModal(result, place) {
    const research = result.research;
    const article = result.article;
    const classification = result.classification || (research && research.classification) || {};

    // Gallery
    const galleryEl = document.getElementById("modalGallery");
    const images = (article && article.images) || (research && research.images) || [];
    if (images.length > 0) {
      galleryEl.innerHTML = images.map(function (img) {
        return '<img class="gallery-img" src="' + escHtml(img.url) + '" alt="' + escHtml(img.caption || place.name) + '" loading="lazy" onerror="this.style.display=\'none\'" />';
      }).join("");
    } else {
      galleryEl.innerHTML = "";
    }

    // Article
    const articleEl = document.getElementById("modalArticle");
    let html = "";

    if (article && article.title) {
      html += '<div class="ai-article-section"><h3>' + escHtml(article.title) + "</h3>";
      if (article.article) {
        html += article.article.split("\n\n").map(function (block) {
          block = block.trim();
          if (!block) return "";
          return "<p>" + escHtml(block).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>") + "</p>";
        }).join("");
      }
      if (article.tags && article.tags.length > 0) {
        html += '<div class="ai-tags">' + article.tags.map(function (t) { return '<span class="ai-tag">' + escHtml(t) + "</span>"; }).join("") + "</div>";
      }
      html += "</div>";
    }

    // Classification section
    if (classification.status) {
      const badge = AI_BADGES[classification.status] || AI_BADGES.unverified;
      html += '<div class="ai-article-section"><h3>☪️ Halal Assessment</h3>';
      html += '<p><strong>' + badge.icon + " " + (classification.label || classification.status) + "</strong></p>";
      if (classification.confidence) {
        html += '<div class="ai-confidence">Confidence: <span class="level-' + classification.confidence + '">' + classification.confidence.toUpperCase() + "</span></div>";
      }
      if (classification.reasoning) {
        html += "<p style='font-size:13px;color:#5a5a7a;margin-top:8px;'>" + escHtml(classification.reasoning) + "</p>";
      }

      const details = [
        classification.cuisine && { icon: "🍴", label: "Cuisine", value: classification.cuisine },
        classification.price_range && { icon: "💰", label: "Price", value: classification.price_range },
        classification.popular_dishes && classification.popular_dishes.length > 0 && { icon: "⭐", label: "Popular", value: classification.popular_dishes.join(", ") },
        classification.hours && { icon: "🕐", label: "Hours", value: classification.hours },
        classification.phone && { icon: "📞", label: "Phone", value: classification.phone },
        classification.website && { icon: "🌐", label: "Website", value: '<a href="' + escHtml(classification.website) + '" target="_blank">Visit</a>' },
      ].filter(Boolean);

      details.forEach(function (d) {
        html += '<div class="detail-row"><div class="detail-icon">' + d.icon + '</div><div class="detail-content"><div class="detail-label">' + d.label + '</div><div class="detail-value">' + (d.value.includes("<a") ? d.value : escHtml(d.value)) + "</div></div></div>";
      });
      html += "</div>";
    }

    articleEl.innerHTML = html || '<p style="color:#5a5a7a;">AI research in progress...</p>';
  }

  // ─── Helpers ───
  function escHtml(str) {
    if (window.escHtml) return window.escHtml(str);
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  function formatCuisine(c) {
    if (window.formatCuisine) return window.formatCuisine(c);
    return c.split(";").map(function (s) { return s.trim().replace(/_/g, " ").replace(/\b\w/g, function (l) { return l.toUpperCase(); }); }).join(", ");
  }

  function formatType(type) {
    const map = { restaurant: "🍽️ Restaurant", fast_food: "🍔 Fast Food", cafe: "☕ Café", food_court: "🏪 Food Court" };
    return map[type] || type;
  }

  // ─── Public API ───
  window.aiSearch = {
    getMode: function () { return "hybrid"; },
    openHybridModal: openHybridModal,
  };

  console.log("✨ AI Search (hybrid) loaded — OSM discovery + AI research");
})();
