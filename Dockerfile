FROM node:18-alpine

WORKDIR /app

# Install dependencies first (layer caching)
COPY package*.json ./
RUN npm ci --production

# Copy app source
COPY . .

EXPOSE 3000

CMD ["node", "server.js"]
