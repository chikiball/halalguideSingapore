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
