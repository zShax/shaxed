FROM node:24-alpine

ENV NODE_ENV=production
WORKDIR /app

RUN npm install -g pm2@6

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY ecosystem.config.cjs ./
COPY server ./server
COPY public ./public

# blog.db lives here; docker-compose mounts a volume over it
RUN mkdir -p /app/data && chown -R node:node /app/data
USER node

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s \
  CMD wget -qO- http://127.0.0.1:${PORT:-3000}/healthz || exit 1

CMD ["pm2-runtime", "ecosystem.config.cjs"]
