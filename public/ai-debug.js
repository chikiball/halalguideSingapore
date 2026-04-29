/**
 * AI Debug Panel — Real-time pipeline logging
 *
 * Enable:  add ?debug=1 to URL (e.g., https://halal.nandharu.uk/?debug=1)
 * Disable: remove ?debug=1 or set ?debug=0
 *
 * Shows a live log panel at the bottom of the screen that prints:
 * - All SSE events as they arrive
 * - SearXNG search results count
 * - Each restaurant found + geocoded
 * - LLM extraction details
 * - Research progress per restaurant
 * - Article writing status
 *
 * To disable for production: remove <script src="/ai-debug.js"> from index.html
 * or just don't use ?debug=1
 */

(function () {
  "use strict";

  // Only activate if ?debug=1 is in the URL
  const params = new URLSearchParams(window.location.search);
  if (params.get("debug") !== "1") return;

  console.log("🐛 AI Debug mode ON");

  // ─── Inject debug panel CSS ───
  const style = document.createElement("style");
  style.textContent = `
    #debugPanel {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      height: 35vh;
      max-height: 300px;
      background: #0d1117;
      color: #c9d1d9;
      font-family: 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 11px;
      line-height: 1.5;
      z-index: 9999;
      display: flex;
      flex-direction: column;
      border-top: 2px solid #1a6b4a;
      transition: height 0.3s;
    }
    #debugPanel.collapsed {
      height: 32px;
      max-height: 32px;
    }
    #debugPanel.collapsed #debugLogs { display: none; }

    #debugHeader {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 4px 12px;
      background: #161b22;
      border-bottom: 1px solid #30363d;
      cursor: pointer;
      user-select: none;
      flex-shrink: 0;
    }
    #debugHeader .title {
      font-weight: 600;
      color: #1a6b4a;
    }
    #debugHeader .controls {
      display: flex;
      gap: 8px;
    }
    #debugHeader .controls button {
      background: #21262d;
      color: #c9d1d9;
      border: 1px solid #30363d;
      border-radius: 4px;
      padding: 2px 8px;
      font-size: 10px;
      cursor: pointer;
      font-family: inherit;
    }
    #debugHeader .controls button:hover {
      background: #30363d;
    }
    #debugHeader .badge {
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 8px;
      background: #1a6b4a;
      color: white;
      margin-left: 6px;
    }

    #debugLogs {
      flex: 1;
      overflow-y: auto;
      padding: 8px 12px;
      scroll-behavior: smooth;
    }
    #debugLogs::-webkit-scrollbar { width: 6px; }
    #debugLogs::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }

    .dlog { margin-bottom: 2px; white-space: pre-wrap; word-break: break-all; }
    .dlog .ts { color: #484f58; }
    .dlog .tag { font-weight: 600; padding: 0 4px; border-radius: 3px; }
    .tag-phase { color: #58a6ff; }
    .tag-search { color: #d2a8ff; }
    .tag-place { color: #3fb950; }
    .tag-geocode { color: #f0883e; }
    .tag-llm { color: #f778ba; }
    .tag-research { color: #79c0ff; }
    .tag-article { color: #56d364; }
    .tag-error { color: #f85149; background: #3d1214; }
    .tag-info { color: #8b949e; }
    .tag-sse { color: #484f58; }

    /* Push main content up when debug panel is open */
    body.debug-active .cards { padding-bottom: 340px !important; }
  `;
  document.head.appendChild(style);

  // ─── Inject debug panel HTML ───
  const panel = document.createElement("div");
  panel.id = "debugPanel";
  panel.innerHTML = `
    <div id="debugHeader" onclick="window.aiDebug.toggle()">
      <span>
        <span class="title">🐛 AI Debug</span>
        <span class="badge" id="debugCount">0</span>
      </span>
      <span class="controls">
        <button onclick="event.stopPropagation(); window.aiDebug.clear()">Clear</button>
        <button onclick="event.stopPropagation(); window.aiDebug.copy()">Copy</button>
        <button id="debugToggleBtn">▼ Collapse</button>
      </span>
    </div>
    <div id="debugLogs"></div>
  `;
  document.body.appendChild(panel);
  document.body.classList.add("debug-active");

  let logCount = 0;
  const logsEl = document.getElementById("debugLogs");
  const countEl = document.getElementById("debugCount");
  let allLogs = [];

  // ─── Log function ───
  function log(tag, message, data) {
    logCount++;
    const now = new Date();
    const ts = now.toLocaleTimeString("en-GB", { hour12: false }) + "." + String(now.getMilliseconds()).padStart(3, "0");

    const entry = document.createElement("div");
    entry.className = "dlog";

    let dataStr = "";
    if (data !== undefined) {
      if (typeof data === "object") {
        try { dataStr = " " + JSON.stringify(data); } catch (e) { dataStr = " [object]"; }
      } else {
        dataStr = " " + String(data);
      }
      // Truncate long data
      if (dataStr.length > 200) dataStr = dataStr.substring(0, 197) + "...";
    }

    entry.innerHTML = `<span class="ts">${ts}</span> <span class="tag tag-${tag}">[${tag.toUpperCase()}]</span> ${escHtml(message)}${dataStr ? '<span style="color:#484f58">' + escHtml(dataStr) + '</span>' : ''}`;

    logsEl.appendChild(entry);
    logsEl.scrollTop = logsEl.scrollHeight;
    countEl.textContent = logCount;

    allLogs.push(`${ts} [${tag.toUpperCase()}] ${message}${dataStr}`);

    // Also log to console
    console.log(`🐛 [${tag}] ${message}`, data || "");
  }

  // ─── Intercept fetch to capture SSE streams ───
  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const url = typeof args[0] === "string" ? args[0] : args[0]?.url || "";
    const opts = args[1] || {};

    // Only intercept AI endpoints
    if (!url.includes("/api/ai/")) {
      return originalFetch.apply(this, args);
    }

    const method = (opts.method || "GET").toUpperCase();
    let body = null;
    try { body = opts.body ? JSON.parse(opts.body) : null; } catch (e) {}

    if (url.includes("/search")) {
      log("phase", "🔍 AI Search started", body);
      log("info", `POST ${url}`);
    } else if (url.includes("/place/details")) {
      log("phase", `🔬 Research started: ${body?.name || "?"}`, { lat: body?.lat, lng: body?.lng });
      log("info", `POST ${url}`);
    }

    const response = await originalFetch.apply(this, args);

    if (!response.ok) {
      log("error", `HTTP ${response.status} from ${url}`);
      return response;
    }

    // Clone response so we can read the stream without consuming it
    const [stream1, stream2] = response.body.tee();

    // Read stream1 for debug logging
    readSSEStream(stream1, url);

    // Return response with stream2 for the actual consumer
    return new Response(stream2, {
      headers: response.headers,
      status: response.status,
      statusText: response.statusText,
    });
  };

  // ─── Read SSE stream for debug logging ───
  async function readSSEStream(stream, url) {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let placeCount = 0;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          log("sse", "Stream ended");
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              handleDebugEvent(data, url);
            } catch (e) {
              // raw SSE data
            }
          } else if (line.startsWith(": ping")) {
            log("sse", "keepalive ping");
          }
        }
      }
    } catch (e) {
      log("error", `Stream read error: ${e.message}`);
    }
  }

  // ─── Handle SSE events for debug logging ───
  let discoveredPlaces = [];

  function handleDebugEvent(data, url) {
    // Agent debug events (sent as phase="debug" with type field)
    if (data.debug || data.phase === "debug") {
      const tagMap = {
        phase: "phase", search: "search", geocode: "geocode",
        llm: "llm", filter: "search", cache: "info", error: "error",
      };
      const tag = tagMap[data.type] || "info";
      log(tag, data.message);

      // Expand search results as individual log lines
      if (data.data && data.data.results && data.data.results.length > 0) {
        log("search", `📋 All ${data.data.results.length} search results:`);
        data.data.results.forEach((r, i) => {
          log("search", `  ${i + 1}. ${r.title}`, { url: r.url });
        });
      }

      // Expand LLM-extracted places as individual log lines
      if (data.data && data.data.places && data.data.places.length > 0) {
        log("llm", `📋 All ${data.data.places.length} LLM-extracted places:`);
        data.data.places.forEach((p, i) => {
          log("llm", `  ${i + 1}. ${p.name} | ${p.address || "no address"}`);
        });
      }

      // Expand filtered places
      if (data.data && data.data.places && data.type === "filter") {
        data.data.places.forEach((p, i) => {
          log("search", `  ✅ ${p.name} (${p.distance}m)`);
        });
      }

      // Show other data if present
      if (data.data && !data.data.results && !data.data.places) {
        log(tag, "  ↳ data:", data.data);
      }
      return;
    }

    // Phase status events
    if (data.phase) {
      const phaseIcons = { discovery: "🔍", research: "🔬", writing: "✍️" };
      log("phase", `${phaseIcons[data.phase] || "⏳"} ${data.message}`);
      return;
    }

    // Place discovered
    if (data.name && data.lat && data.lng && !data.classification && !data.article) {
      discoveredPlaces.push(data);
      const dist = data.distance ? `${data.distance}m` : "?m";
      log("place", `📍 #${discoveredPlaces.length} ${data.name} (${dist})`, {
        lat: data.lat?.toFixed(4),
        lng: data.lng?.toFixed(4),
        cuisine: data.cuisine || "-",
        status: data.halalStatus || "unverified",
      });
      return;
    }

    // Research results (classification)
    if (data.classification) {
      const cls = data.classification;
      log("research", `☪️ Classification: ${cls.icon || ""} ${cls.label || cls.status}`, {
        confidence: cls.confidence,
        cuisine: cls.cuisine,
        price: cls.price_range,
        dishes: cls.popular_dishes?.join(", "),
        cert: cls.certificate,
      });
      if (cls.reasoning) {
        log("llm", `💭 Reasoning: ${cls.reasoning.substring(0, 150)}${cls.reasoning.length > 150 ? "..." : ""}`);
      }
      if (data.images?.length) {
        log("info", `🖼️ ${data.images.length} images found`);
      }
      return;
    }

    // Article
    if (data.article || data.title) {
      log("article", `📝 Article: "${data.title || "Untitled"}"`, {
        length: data.article?.length || 0,
        tags: data.tags,
      });
      return;
    }

    // Done
    if (data.count !== undefined) {
      log("phase", `✅ Discovery complete: ${data.count} places found`);
      if (discoveredPlaces.length > 0) {
        log("info", `📋 All discovered places:`);
        discoveredPlaces.forEach((p, i) => {
          log("place", `  ${i + 1}. ${p.name} — ${p.address || "no address"} (${p.distance || "?"}m)`);
        });
      }
      discoveredPlaces = []; // reset for next search
      return;
    }

    // Error
    if (data.message && !data.phase) {
      log("error", `⚠️ ${data.message}`);
      return;
    }

    // Unknown event
    log("sse", "Unknown event", data);
  }

  // ─── Helper ───
  function escHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ─── Public API ───
  window.aiDebug = {
    toggle: function () {
      const p = document.getElementById("debugPanel");
      const btn = document.getElementById("debugToggleBtn");
      p.classList.toggle("collapsed");
      btn.textContent = p.classList.contains("collapsed") ? "▲ Expand" : "▼ Collapse";
    },
    clear: function () {
      logsEl.innerHTML = "";
      logCount = 0;
      countEl.textContent = "0";
      allLogs = [];
      log("info", "Debug log cleared");
    },
    copy: function () {
      const text = allLogs.join("\n");
      navigator.clipboard.writeText(text).then(function () {
        log("info", `📋 Copied ${allLogs.length} log lines to clipboard`);
      });
    },
    log: log, // expose for manual logging
  };

  // ─── Initial log ───
  log("info", "🐛 AI Debug panel active — URL: " + window.location.href);
  log("info", "Search mode: " + (window.aiSearch?.getMode?.() || "unknown"));
  log("info", "Tip: Toggle 🤖 AI Search and tap Search to see pipeline logs");

})();
