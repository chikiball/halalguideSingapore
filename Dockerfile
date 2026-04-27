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
