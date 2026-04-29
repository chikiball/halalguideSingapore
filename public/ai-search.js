/**
 * AI Search Module — Step 10
 * Handles AI-powered search via SSE streaming.
 *
 * Loaded after the main index.html script.
 * Adds: search mode toggle, SSE consumption, progressive card rendering,
 *       AI-specific badges, and research/article streaming in modal.
 *
 * Requires: the main app's global functions (escHtml, openModal, etc.)
 */

(function () {
  "use strict";

  // ─── State ───
  let searchMode = "ai"; // "osm" or "ai" — default to AI
  let aiPlaces = [];
  let aiResearchCache = {};

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

  // ─── Inject additional CSS ───
  const style = document.createElement("style");
  style.textContent = `
    .search-mode-bar {
      display: flex;
      gap: 0;
      padding: 8px 20px 0;
    }
    .mode-toggle {
      flex: 1;
      padding: 8px 12px;
      border: 2px solid #e0e0e0;
      background: #fff;
      color: #5a5a7a;
      font-size: 12px;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
    }
    .mode-toggle:first-child { border-radius: 8px 0 0 8px; border-right: none; }
    .mode-toggle:last-child { border-radius: 0 8px 8px 0; }
    .mode-toggle.active { background: #1a6b4a; color: white; border-color: #1a6b4a; }
    .mode-toggle .mode-tag {
      font-size: 9px;
      padding: 1px 5px;
      border-radius: 8px;
      background: rgba(255,255,255,0.2);
    }
    .mode-toggle:not(.active) .mode-tag { background: #f0f0f0; color: #888; }

    .ai-status {
      padding: 8px 20px;
      font-size: 13px;
      color: #5a5a7a;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .ai-status .ai-spinner {
      width: 16px; height: 16px;
      border: 2px solid #e8f5ee;
      border-top-color: #1a6b4a;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    .ai-status .phase-label {
      font-weight: 600;
      color: #1a6b4a;
    }

    .badge-vegan { background: #e0f2f1; color: #00695c; }
    .badge-unverified { background: #f5f5f5; color: #9e9e9e; }

    .card-ai-status {
      font-size: 11px;
      color: #5a5a7a;
      margin-top: 4px;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .card-ai-status .mini-spinner {
      width: 12px; height: 12px;
      border: 2px solid #e0e0e0;
      border-top-color: #1a6b4a;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      display: inline-block;
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

  // ─── Inject search mode toggle into DOM ───
  function injectSearchModeToggle() {
    const controls = document.querySelector(".controls");
    if (!controls || document.getElementById("searchModeBar")) return;

    const bar = document.createElement("div");
    bar.className = "search-mode-bar";
    bar.id = "searchModeBar";
    bar.innerHTML = `
      <button class="mode-toggle" id="modeOSM" onclick="window.aiSearch.setMode('osm')">
        🗺️ Quick Search <span class="mode-tag">OSM</span>
      </button>
      <button class="mode-toggle active" id="modeAI" onclick="window.aiSearch.setMode('ai')">
        🤖 AI Search <span class="mode-tag">LLM</span>
      </button>
    `;
    controls.parentNode.insertBefore(bar, controls);
  }

  // ─── Set search mode ───
  function setMode(mode) {
    searchMode = mode;
    document.getElementById("modeOSM").classList.toggle("active", mode === "osm");
    document.getElementById("modeAI").classList.toggle("active", mode === "ai");
  }

  // ─── Override the global searchHalal function ───
  const originalSearchHalal = window.searchHalal;

  window.searchHalal = function () {
    if (searchMode === "ai") {
      searchAI();
    } else {
      originalSearchHalal();
    }
  };

  // ─── AI Search (SSE streaming) ───
  async function searchAI() {
    const radius = document.getElementById("radiusSelect").value;
    const loader = document.getElementById("loader");
    const emptyState = document.getElementById("emptyState");
    const cardsEl = document.getElementById("cards");
    const statusBar = document.getElementById("statusBar");
    const searchBtn = document.getElementById("searchBtn");

    loader.classList.remove("active");
    emptyState.classList.remove("active");
    cardsEl.innerHTML = "";
    searchBtn.disabled = true;
    aiPlaces = [];

    // Show AI status
    statusBar.innerHTML = `
      <div class="ai-status">
        <div class="ai-spinner"></div>
        <span class="phase-label">Discovering</span> — Searching for halal restaurants...
      </div>
    `;

    // Clear map markers
    if (window.markersLayer) window.markersLayer.clearLayers();

    try {
      const response = await fetch("/api/ai/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lat: window.searchLat,
          lng: window.searchLng,
          radius: parseInt(radius),
        }),
      });

      if (!response.ok) throw new Error("Agent service unavailable");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6);
            try {
              const data = JSON.parse(jsonStr);
              handleSSEEvent(line, data, cardsEl, statusBar);
            } catch (e) {
              // Not JSON, might be event: line
            }
          } else if (line.startsWith("event: ")) {
            // Store event type for next data line
            buffer = line + "\n" + buffer;
          }
        }
      }

    } catch (err) {
      statusBar.innerHTML = `⚠️ AI Search failed: ${err.message}. Try Quick Search (OSM) instead.`;
    }

    searchBtn.disabled = false;
  }

  // ─── Handle SSE events ───
  function handleSSEEvent(rawLine, data, cardsEl, statusBar) {
    // Parse event type from the raw SSE stream
    if (data.phase) {
      // Status event
      statusBar.innerHTML = `
        <div class="ai-status">
          <div class="ai-spinner"></div>
          <span class="phase-label">${data.phase === "discovery" ? "Discovering" : "Processing"}</span>
          — ${escHtml(data.message)}
        </div>
      `;
      return;
    }

    if (data.name && data.lat && data.lng) {
      // Place event — add to map + cards
      const idx = aiPlaces.length;
      data.distance = window.getDistance
        ? getDistance(window.searchLat, window.searchLng, data.lat, data.lng)
        : 0;
      aiPlaces.push(data);

      // Render card
      renderAICard(data, idx, cardsEl);

      // Add map marker
      if (window.markersLayer && window.L) {
        const icon = L.divIcon({
          className: "",
          html: '<div style="width:30px;height:30px;background:#1a6b4a;border:2px solid white;border-radius:50%;box-shadow:0 2px 8px rgba(0,0,0,0.2);display:flex;align-items:center;justify-content:center;font-size:15px;">🍽️</div>',
          iconSize: [30, 30],
          iconAnchor: [15, 15],
        });
        const marker = L.marker([data.lat, data.lng], { icon: icon })
          .addTo(window.markersLayer)
          .bindPopup("<b>" + escHtml(data.name) + "</b>");
        marker.on("click", function () { openAIModal(idx); });
      }

      // Update status
      statusBar.innerHTML = `Found <span class="count">${aiPlaces.length}</span> place${aiPlaces.length > 1 ? "s" : ""} so far...`;
      return;
    }

    if (data.count !== undefined) {
      // Done event
      const radius = document.getElementById("radiusSelect").value;
      if (aiPlaces.length === 0) {
        document.getElementById("emptyState").classList.add("active");
        statusBar.innerHTML = "No halal places found. Try a larger radius.";
      } else {
        statusBar.innerHTML = `Found <span class="count">${aiPlaces.length}</span> halal place${aiPlaces.length > 1 ? "s" : ""} via AI search`;
        // Fit map bounds
        if (window.map && window.L && aiPlaces.length > 0) {
          const bounds = L.latLngBounds(aiPlaces.map(function (p) { return [p.lat, p.lng]; }));
          bounds.extend([window.searchLat, window.searchLng]);
          map.fitBounds(bounds, { padding: [40, 40] });
        }
      }
      return;
    }

    if (data.message) {
      // Error event
      statusBar.innerHTML = "⚠️ " + escHtml(data.message);
    }
  }

  // ─── Render AI card ───
  function renderAICard(place, index, container) {
    const card = document.createElement("div");
    card.className = "card";
    card.onclick = function () { openAIModal(index); };
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    card.id = "ai-card-" + index;

    const distStr = place.distance < 1000
      ? Math.round(place.distance) + "m away"
      : (place.distance / 1000).toFixed(1) + "km away";

    const status = place.halalStatus || "unverified";
    const badge = AI_BADGES[status] || AI_BADGES.unverified;

    card.innerHTML = `
      <div class="card-header">
        <div class="card-name">${escHtml(place.name)}</div>
        <span class="card-badge ${badge.cls}">${badge.icon} ${badge.label}</span>
      </div>
      ${place.cuisine ? '<div class="card-cuisine">🍴 ' + escHtml(place.cuisine) + "</div>" : ""}
      <div class="card-distance">📍 ${distStr}</div>
      ${place.address ? '<div class="card-address">' + escHtml(place.address) + "</div>" : ""}
      <div class="card-ai-status" id="ai-card-status-${index}">
        🤖 <span style="color:#1a6b4a;">AI powered</span> — tap for details
      </div>
    `;
    container.appendChild(card);
  }

  // ─── Open AI modal with SSE research streaming ───
  function openAIModal(index) {
    const p = aiPlaces[index];
    if (!p) return;

    const distStr = p.distance < 1000
      ? Math.round(p.distance) + "m away"
      : (p.distance / 1000).toFixed(1) + "km away";

    const status = p.halalStatus || "unverified";
    const badge = AI_BADGES[status] || AI_BADGES.unverified;

    // Header
    document.getElementById("modalHeader").innerHTML = `
      <h2>${escHtml(p.name)}</h2>
      <div class="modal-badges">
        <span class="card-badge ${badge.cls}">${badge.icon} ${badge.label}</span>
        <span class="card-badge badge-type">🤖 AI Research</span>
      </div>
    `;

    // Quick info
    let bodyHtml = "";
    const rows = [
      { icon: "📍", label: "Distance", value: distStr },
      p.cuisine && { icon: "🍴", label: "Cuisine", value: p.cuisine },
      p.address && { icon: "🏠", label: "Address", value: p.address },
    ].filter(Boolean);

    rows.forEach(function (r) {
      bodyHtml += `
        <div class="detail-row">
          <div class="detail-icon">${r.icon}</div>
          <div class="detail-content">
            <div class="detail-label">${r.label}</div>
            <div class="detail-value">${escHtml(r.value)}</div>
          </div>
        </div>`;
    });
    document.getElementById("modalBody").innerHTML = bodyHtml;

    // Show shimmer in gallery + article areas
    document.getElementById("modalGallery").innerHTML = '<div class="shimmer shimmer-img" style="flex-shrink:0;"></div>';
    document.getElementById("modalArticle").innerHTML = `
      <div class="ai-status">
        <div class="ai-spinner"></div>
        <span class="phase-label">Researching</span> — gathering evidence about ${escHtml(p.name)}...
      </div>
      <div class="shimmer shimmer-title" style="margin-top:12px;"></div>
      <div class="shimmer shimmer-line"></div>
      <div class="shimmer shimmer-line-med"></div>
      <div class="shimmer shimmer-line"></div>
      <div class="shimmer shimmer-line-short"></div>
    `;
    document.getElementById("modalSources").innerHTML = "";

    // Actions
    document.getElementById("modalActions").innerHTML = `
      <button class="btn btn-primary" onclick="navigateTo(${p.lat}, ${p.lng})">🧭 Directions</button>
      <button class="btn btn-outline" onclick="panTo(${p.lat}, ${p.lng})">🗺️ Show on Map</button>
    `;

    // Open modal
    document.getElementById("modalOverlay").classList.add("active");
    document.body.style.overflow = "hidden";

    // Check cache first
    const cacheKey = p.name + "_" + p.lat.toFixed(3);
    if (aiResearchCache[cacheKey]) {
      renderAIResearch(aiResearchCache[cacheKey].research, aiResearchCache[cacheKey].article, p);
      return;
    }

    // Stream research + article via SSE
    fetchAIDetails(p, index, cacheKey);
  }

  // ─── Fetch AI details via SSE ───
  async function fetchAIDetails(place, index, cacheKey) {
    try {
      const response = await fetch("/api/ai/place/details", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(place),
      });

      if (!response.ok) throw new Error("Research failed");

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

            if (data.phase) {
              // Update status in modal
              const articleEl = document.getElementById("modalArticle");
              if (articleEl && data.phase === "writing") {
                articleEl.innerHTML = `
                  <div class="ai-status">
                    <div class="ai-spinner"></div>
                    <span class="phase-label">Writing</span> — composing article for ${escHtml(place.name)}...
                  </div>
                `;
              }
            }

            if (data.classification) {
              research = data;
              // Update card badge
              updateCardBadge(index, data.classification);
            }

            if (data.article || data.title) {
              article = data;
            }

            if (data.name && !data.classification && !data.article) {
              // Done event
              if (research || article) {
                aiResearchCache[cacheKey] = { research: research, article: article };
                renderAIResearch(research, article, place);
              }
            }
          } catch (e) { /* skip non-JSON */ }
        }
      }

      // Final render if not triggered by done event
      if ((research || article) && !aiResearchCache[cacheKey]) {
        aiResearchCache[cacheKey] = { research: research, article: article };
        renderAIResearch(research, article, place);
      }

    } catch (err) {
      document.getElementById("modalArticle").innerHTML = `
        <p style="color:#5a5a7a;">⚠️ Could not load AI research: ${escHtml(err.message)}</p>
      `;
    }
  }

  // ─── Render AI research results in modal ───
  function renderAIResearch(research, article, place) {
    // Images
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
      html += '<div class="ai-article-section">';
      html += "<h3>" + escHtml(article.title) + "</h3>";

      if (article.article) {
        // Render markdown-ish article
        const rendered = article.article
          .split("\n\n")
          .map(function (block) {
            block = block.trim();
            if (!block) return "";
            return "<p>" + escHtml(block).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>") + "</p>";
          })
          .join("");
        html += rendered;
      }

      // Tags
      if (article.tags && article.tags.length > 0) {
        html += '<div class="ai-tags">';
        article.tags.forEach(function (tag) {
          html += '<span class="ai-tag">' + escHtml(tag) + "</span>";
        });
        html += "</div>";
      }

      html += "</div>";
    }

    // Classification details
    if (research && research.classification) {
      const cls = research.classification;
      const badge = AI_BADGES[cls.status] || AI_BADGES.unverified;

      html += '<div class="ai-article-section">';
      html += '<h3>☪️ Halal Assessment</h3>';
      html += '<p><strong>' + badge.icon + " " + (cls.label || cls.status) + "</strong></p>";

      if (cls.confidence) {
        html += '<div class="ai-confidence">Confidence: <span class="level-' + cls.confidence + '">' + cls.confidence.toUpperCase() + "</span></div>";
      }

      if (cls.reasoning) {
        html += "<p style='font-size:13px;color:#5a5a7a;margin-top:8px;'>" + escHtml(cls.reasoning) + "</p>";
      }

      if (cls.certificate) {
        html += "<p>📜 Certificate: <strong>" + escHtml(cls.certificate) + "</strong></p>";
      }

      // Extra details from classification
      const details = [
        cls.cuisine && { icon: "🍴", label: "Cuisine", value: cls.cuisine },
        cls.price_range && { icon: "💰", label: "Price", value: cls.price_range },
        cls.popular_dishes && cls.popular_dishes.length > 0 && { icon: "⭐", label: "Popular", value: cls.popular_dishes.join(", ") },
        cls.hours && { icon: "🕐", label: "Hours", value: cls.hours },
        cls.phone && { icon: "📞", label: "Phone", value: cls.phone },
        cls.website && { icon: "🌐", label: "Website", value: '<a href="' + escHtml(cls.website) + '" target="_blank">Visit</a>' },
      ].filter(Boolean);

      details.forEach(function (d) {
        html += '<div class="detail-row"><div class="detail-icon">' + d.icon + '</div><div class="detail-content"><div class="detail-label">' + d.label + '</div><div class="detail-value">' + (d.value.includes("<a") ? d.value : escHtml(d.value)) + "</div></div></div>";
      });

      html += "</div>";
    }

    articleEl.innerHTML = html || '<p style="color:#5a5a7a;">No additional details available.</p>';
  }

  // ─── Update card badge after research completes ───
  function updateCardBadge(index, classification) {
    const card = document.getElementById("ai-card-" + index);
    if (!card) return;

    const status = classification.status || "unverified";
    const badge = AI_BADGES[status] || AI_BADGES.unverified;

    // Update badge
    const badgeEl = card.querySelector(".card-badge");
    if (badgeEl) {
      badgeEl.className = "card-badge " + badge.cls;
      badgeEl.innerHTML = badge.icon + " " + badge.label;
    }

    // Update AI status line
    const statusEl = document.getElementById("ai-card-status-" + index);
    if (statusEl) {
      statusEl.innerHTML = "🤖 <span style='color:#1a6b4a;'>Researched</span> — " +
        (classification.confidence || "low") + " confidence";
    }

    // Update the place in aiPlaces
    if (aiPlaces[index]) {
      aiPlaces[index].halalStatus = status;
    }
  }

  // ─── Helper: use global escHtml ───
  function escHtml(str) {
    if (window.escHtml) return window.escHtml(str);
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ─── Initialize on DOM ready ───
  function init() {
    // Wait for the main app to be ready
    const check = setInterval(function () {
      if (document.querySelector(".controls")) {
        clearInterval(check);
        injectSearchModeToggle();
        console.log("🤖 AI Search module loaded");
      }
    }, 200);
  }

  // Export to window
  window.aiSearch = {
    setMode: setMode,
    getMode: function () { return searchMode; },
    openAIModal: openAIModal,
  };

  // Start
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
