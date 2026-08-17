FROM node:24-bookworm-slim

ENV NODE_ENV=production

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci --omit=dev \
    && npm cache clean --force

COPY --chown=node:node data ./data
COPY --chown=node:node public ./public
COPY --chown=node:node logger.js server.js ./

USER node

EXPOSE 8080

CMD ["node", "server.js"]
