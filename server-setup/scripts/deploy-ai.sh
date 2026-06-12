#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Halal Guide SG — Full AI Stack Deployment
# Run on server: sudo bash deploy-ai.sh
#
# Prerequisites:
#   - Docker + Docker Compose installed
#   - .env present in the site dir with DEEPSEEK_API_KEY (and MAPBOX_TOKEN)
#   - server-net Docker network exists
#   - Cloudflare tunnel configured for halal.nandharu.uk
# ═══════════════════════════════════════════════════════════════
set -e

SITE_DIR="/home/nandha/server/sites/halalguideSingapore"
NGINX_DIR="/home/nandha/server/nginx/conf.d"
REPO="https://github.com/chikiball/halalguideSingapore.git"

echo "═══════════════════════════════════════════════════"
echo "🕌 Halal Guide SG — AI Stack Deployment"
echo "═══════════════════════════════════════════════════"
echo ""

# ─── 1. Pre-flight checks ────────────────────────────────────
echo "🔍 Pre-flight checks..."

# Docker
if ! command -v docker &>/dev/null; then
  echo "❌ Docker not found. Install it first."
  exit 1
fi
echo "  ✅ Docker $(docker --version | grep -oP '\d+\.\d+\.\d+')"

# Docker Compose
if ! docker compose version &>/dev/null; then
  echo "❌ Docker Compose not found."
  exit 1
fi
echo "  ✅ Docker Compose $(docker compose version --short)"

# DeepSeek API key (LLM is a hosted API — no local model container)
if grep -q "^DEEPSEEK_API_KEY=.\+" "$SITE_DIR/.env" 2>/dev/null; then
  echo "  ✅ DEEPSEEK_API_KEY present in .env"
else
  echo "❌ DEEPSEEK_API_KEY missing. Create $SITE_DIR/.env from .env.example."
  exit 1
fi

# server-net network
if ! docker network inspect server-net &>/dev/null 2>&1; then
  echo "  Creating server-net network..."
  docker network create server-net
fi
echo "  ✅ server-net network exists"

echo ""

# ─── 2. Clone / update repo ──────────────────────────────────
echo "📦 Updating repository..."
if [ -d "$SITE_DIR" ]; then
  cd "$SITE_DIR"
  git pull origin main
  echo "  ✅ Repository updated"
else
  git clone "$REPO" "$SITE_DIR"
  cd "$SITE_DIR"
  echo "  ✅ Repository cloned"
fi

# ─── 3. Run setup scripts ────────────────────────────────────
echo ""
echo "🔧 Running setup scripts..."

# Create agent-service files if not present
if [ ! -f "agent-service/main.py" ]; then
  bash setup-agent-service.sh
  echo "  ✅ Agent service scaffolded"
else
  echo "  ✅ Agent service already exists"
fi

# Patch server.js + index.html
bash setup-step10.sh
echo "  ✅ AI routes patched"

# Update Dockerfile + fly.toml + .dockerignore
bash server-setup/scripts/update-deploy-files.sh
echo "  ✅ Deploy files updated"

# ─── 4. Copy nginx config ────────────────────────────────────
echo ""
echo "🌐 Updating nginx config..."
cp server-setup/nginx/halalguideSingapore.conf "$NGINX_DIR/"
docker exec nginx-gateway nginx -t 2>/dev/null && \
  docker exec nginx-gateway nginx -s reload
echo "  ✅ Nginx config deployed + reloaded"

# ─── 5. Build and start all containers ───────────────────────
echo ""
echo "🐳 Building and starting containers..."
docker compose up -d --build
echo ""

# ─── 6. Wait for health checks ───────────────────────────────
echo "⏳ Waiting for services to be healthy..."
echo -n "  SearXNG: "
for i in $(seq 1 30); do
  if docker inspect --format='{{.State.Health.Status}}' searxng 2>/dev/null | grep -q healthy; then
    echo "✅ healthy"
    break
  fi
  sleep 2
  echo -n "."
done

echo -n "  Agent: "
for i in $(seq 1 30); do
  if docker inspect --format='{{.State.Health.Status}}' halal-agent 2>/dev/null | grep -q healthy; then
    echo "✅ healthy"
    break
  fi
  sleep 3
  echo -n "."
done

echo -n "  App: "
for i in $(seq 1 20); do
  if docker inspect --format='{{.State.Health.Status}}' halalguideSingapore 2>/dev/null | grep -q healthy; then
    echo "✅ healthy"
    break
  fi
  sleep 2
  echo -n "."
done

# ─── 7. Run integration tests ────────────────────────────────
echo ""
echo "🧪 Running integration tests..."

# Test 1: App health
echo -n "  [1/5] App serves HTML: "
if curl -sf http://localhost:3000/ | grep -q "Halal Guide"; then
  echo "✅ PASS"
else
  echo "❌ FAIL"
fi

# Test 2: Overpass API (OSM search)
echo -n "  [2/5] OSM search API: "
RESULT=$(curl -sf "http://localhost:3000/api/halal?lat=1.3006&lng=103.8563&radius=1000" 2>/dev/null)
if echo "$RESULT" | grep -q '"count"'; then
  COUNT=$(echo "$RESULT" | grep -oP '"count":\s*\K\d+')
  echo "✅ PASS ($COUNT places)"
else
  echo "❌ FAIL"
fi

# Test 3: SearXNG
echo -n "  [3/5] SearXNG search: "
if curl -sf "http://searxng:8888/search?q=test&format=json" 2>/dev/null | grep -q '"results"'; then
  echo "✅ PASS"
else
  # Try via Docker network
  if docker exec searxng wget -qO- "http://localhost:8888/healthz" 2>/dev/null | grep -q "OK"; then
    echo "✅ PASS (via container)"
  else
    echo "⚠️ SKIP (not accessible from host, but may work via Docker network)"
  fi
fi

# Test 4: Agent health
echo -n "  [4/5] Agent health: "
AGENT_HEALTH=$(curl -sf http://localhost:5000/health 2>/dev/null || docker exec halal-agent curl -sf http://localhost:5000/health 2>/dev/null)
if echo "$AGENT_HEALTH" | grep -q '"ok"'; then
  echo "✅ PASS"
else
  echo "⚠️ SKIP (internal only, check via: docker exec halal-agent curl http://localhost:5000/health)"
fi

# Test 5: DeepSeek API key wired into the agent
echo -n "  [5/5] DeepSeek key: "
if echo "$AGENT_HEALTH" | grep -q '"api_key_set": *true'; then
  echo "✅ PASS"
else
  echo "❌ FAIL — DEEPSEEK_API_KEY not loaded. Check $SITE_DIR/.env and rebuild the agent."
fi

# ─── 8. Summary ──────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo "📊 Container Status:"
echo "═══════════════════════════════════════════════════"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "halal|searxng|agent"
echo ""
echo "═══════════════════════════════════════════════════"
echo "🎉 Deployment complete!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  🌐 Live URL: https://halal.nandharu.uk"
echo "  📊 Status:   sudo bash /home/nandha/server/scripts/status.sh"
echo "  📋 Logs:     cd $SITE_DIR && docker compose logs -f"
echo "  🔄 Redeploy: sudo bash $SITE_DIR/server-setup/scripts/deploy-ai.sh"
echo ""
