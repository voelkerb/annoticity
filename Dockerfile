FROM node:22-bookworm-slim AS web-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg python3-tables \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /home/node/.cache/annoticity \
    && chown -R node:node /home/node/.cache
WORKDIR /app/server
COPY server/package.json server/package-lock.json ./
RUN npm ci --omit=dev
COPY server/src ./src
COPY --from=web-build /app/web/dist /app/web/dist
ENV NODE_ENV=production PORT=8000 ANNOTICITY_PUBLIC=true ANNOTICITY_HOST=0.0.0.0
USER node
EXPOSE 8000
CMD ["node", "src/index.js"]
