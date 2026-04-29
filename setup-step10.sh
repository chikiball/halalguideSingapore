#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Step 10: Wire AI routes into server.js + index.html
# Run once: bash setup-step10.sh
# ═══════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"
echo "📂 Patching files in: $(pwd)"

# ─── 1. Patch server.js: add AI routes ───
if grep -q "ai-routes" server.js 2>/dev/null; then
  echo "✅ server.js already has AI routes"
else
  # Insert require('./ai-routes')(app) after app.use(express.json())
  if grep -q "express.json" server.js; then
    sed -i.bak '/express\.json/a\
\
// AI Agent routes (proxy to Python agent-service)\
require("./ai-routes")(app);' server.js
    rm -f server.js.bak
    echo "✅ server.js patched — added AI routes"
  else
    # Fallback: add after static middleware
    sed -i.bak '/express\.static/a\
\
app.use(express.json());\
require("./ai-routes")(app);' server.js
    rm -f server.js.bak
    echo "✅ server.js patched (fallback position)"
  fi
fi

# ─── 1b. Patch server.js: support ?all=true to skip halal filter ───
if grep -q "req.query.all" server.js 2>/dev/null; then
  echo "✅ server.js already has all=true support"
else
  # Add ?all=true parameter check before the halal filter
  sed -i.bak 's|// Filter for halal/Muslim-friendly places|// Skip halal filter if ?all=true (hybrid mode: AI classifies instead)\
      var skipFilter = req.query.all === "true";\
\
      // Filter for halal/Muslim-friendly places|' server.js
  # Change the filter line to check skipFilter
  sed -i.bak 's|var halalPlaces = data.elements.filter(function (el) {|var halalPlaces = skipFilter ? data.elements : data.elements.filter(function (el) {|' server.js
  rm -f server.js.bak
  echo "✅ server.js patched — ?all=true skips halal filter"
fi

# ─── 2. Patch index.html: expose let-scoped vars on window ───
if grep -q "window.searchLat" public/index.html 2>/dev/null; then
  echo "✅ index.html already has window bridge"
else
  # Insert a bridge script before </script> (end of main script block)
  # This exposes let-scoped variables so ai-search.js IIFE can access them
  sed -i.bak 's|// Handle escape key for modal|// Expose let-scoped vars for external modules (ai-search.js, ai-debug.js)\
    window.searchLat = undefined; window.searchLng = undefined;\
    window.markersLayer = undefined; window.map = undefined;\
    Object.defineProperty(window, "searchLat", { get: function() { return searchLat; }, set: function(v) { searchLat = v; } });\
    Object.defineProperty(window, "searchLng", { get: function() { return searchLng; }, set: function(v) { searchLng = v; } });\
    Object.defineProperty(window, "markersLayer", { get: function() { return markersLayer; } });\
    Object.defineProperty(window, "map", { get: function() { return map; } });\
    window.getDistance = getDistance;\
    window.escHtml = escHtml;\
\
    // Handle escape key for modal|' public/index.html
  rm -f public/index.html.bak
  echo "✅ index.html patched — exposed let vars on window"
fi

# ─── 2b. Patch index.html: add ai-search.js script ───
if grep -q "ai-search.js" public/index.html 2>/dev/null; then
  echo "✅ index.html already has ai-search.js"
else
  # Insert <script src="/ai-search.js"></script> before </body>
  sed -i.bak 's|</body>|<script src="/ai-search.js"></script>\n</body>|' public/index.html
  rm -f public/index.html.bak
  echo "✅ index.html patched — added ai-search.js"
fi

# ─── 2b. Patch index.html: add ai-debug.js script ───
if grep -q "ai-debug.js" public/index.html 2>/dev/null; then
  echo "✅ index.html already has ai-debug.js"
else
  # Insert <script src="/ai-debug.js"></script> after ai-search.js
  sed -i.bak 's|</body>|<script src="/ai-debug.js"></script>\n</body>|' public/index.html
  rm -f public/index.html.bak
  echo "✅ index.html patched — added ai-debug.js (activate with ?debug=1)"
fi

# ─── 2c. Patch index.html: default radius 500m, max 3km ───
if grep -q "5000.*5 km" public/index.html 2>/dev/null; then
  # Change default from 1500 to 500
  sed -i.bak 's|<option value="1500" selected>1.5 km radius</option>|<option value="1500">1.5 km radius</option>|' public/index.html
  sed -i.bak 's|<option value="500">500m radius</option>|<option value="500" selected>500m radius</option>|' public/index.html
  # Remove 5km option
  sed -i.bak '/<option value="5000">5 km radius<\/option>/d' public/index.html
  rm -f public/index.html.bak
  echo "✅ index.html patched — default 500m, removed 5km"
else
  echo "✅ index.html radius already patched"
fi

# ─── 2d. Patch index.html: make Search here popup a button ───
if grep -q "searchHalal()" public/index.html 2>/dev/null && ! grep -q "Search here.*searchHalal" public/index.html 2>/dev/null; then
  sed -i.bak "s|bindPopup(\"<b>Search here</b>\")|bindPopup('<div style=\"text-align:center\"><b>📍 Selected Location</b><br><button onclick=\"searchHalal()\" style=\"margin-top:6px;padding:6px 16px;background:#1a6b4a;color:white;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer\">🔍 Search here</button></div>')|" public/index.html
  rm -f public/index.html.bak
  echo "✅ index.html patched — Search here popup is now a button"
else
  echo "✅ index.html search bubble already patched"
fi

# ─── 3. Verify ───
echo ""
echo "═══════════════════════════════════════════════════"
echo "✅ Step 10 patches applied!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "Verify:"
grep -n "ai-routes" server.js && echo "  ✓ AI routes in server.js"
grep -n "ai-search.js" public/index.html && echo "  ✓ AI search in index.html"
grep -n "ai-debug.js" public/index.html && echo "  ✓ AI debug in index.html (use ?debug=1)"
echo ""
echo "New files:"
ls -la ai-routes.js public/ai-search.js public/ai-debug.js
