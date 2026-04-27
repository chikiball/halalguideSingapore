#!/bin/bash
# Run this locally to update the 3 sandbox-locked files
# Usage: bash server-setup/scripts/update-deploy-files.sh

cd "$(dirname "$0")/../.." || exit 1
echo "📂 Working in: $(pwd)"

# ─── 1. Dockerfile (hardened, matches aidatajakarta pattern) ───
cat > Dockerfile << 'DEOF'
FROM node:18-alpine

WORKDIR /app

# Install curl for healthcheck
RUN apk add --no-cache curl

# Install dependencies first (layer caching)
COPY package*.json ./
RUN npm ci --production

# Copy app source
COPY . .

# Create non-root user and give ownership
RUN addgroup -S appuser && adduser -S -G appuser -h /app -s /sbin/nologin appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port (internal only — no host binding)
EXPOSE 3000

# Health check
HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=30s \
  CMD curl -sf http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
DEOF
echo "✅ Dockerfile updated"

# ─── 2. .dockerignore ───
cat > .dockerignore << 'DIEOF'
node_modules
npm-debug.log
.git
.gitignore
.github
README.md
context.md
server-setup
.DS_Store
DIEOF
echo "✅ .dockerignore updated"

# ─── 3. fly.toml (matches aidatajakarta convention) ───
cat > fly.toml << 'FTEOF'
app = "halal-guide-singapore"
primary_region = "sin"

[build]

[env]
  PORT = "3000"
  NODE_ENV = "production"

[http_service]
  internal_port = 3000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0
  processes = ["app"]

[[vm]]
  memory = "512mb"
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512
FTEOF
echo "✅ fly.toml updated"

echo ""
echo "🎉 All deploy files updated! Now run:"
echo "   git add -A && git commit -m 'Update deploy configs' && git push origin main"
