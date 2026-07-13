FROM node:22-alpine AS build

WORKDIR /src
COPY package.json package-lock.json tsconfig.base.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/api-client/package.json ./packages/api-client/package.json
COPY packages/design-tokens/package.json ./packages/design-tokens/package.json
COPY packages/knowledge-graph/package.json ./packages/knowledge-graph/package.json
COPY packages/platform-bridge/package.json ./packages/platform-bridge/package.json
COPY packages/shared-schema/package.json ./packages/shared-schema/package.json
RUN npm ci

COPY apps/web ./apps/web
COPY packages ./packages
ARG VITE_CLOUD_API_URL=/
ARG VITE_TURNSTILE_SITE_KEY=
ARG VITE_APP_VERSION=0.1.0
ENV VITE_CLOUD_API_URL=$VITE_CLOUD_API_URL
ENV VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY
ENV VITE_APP_VERSION=$VITE_APP_VERSION
RUN npm run web:build

FROM nginx:1.27-alpine
ARG VITE_APP_VERSION=0.1.0
LABEL org.opencontainers.image.title="OmniLit Web" \
      org.opencontainers.image.version="${VITE_APP_VERSION}"
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /src/apps/web/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/healthz"]
CMD ["nginx", "-g", "daemon off;"]
