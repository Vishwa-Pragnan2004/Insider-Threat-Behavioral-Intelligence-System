# ITBIS frontend — built as a static bundle, served by nginx.
#
#   docker build -f frontend/Dockerfile -t itbis-frontend frontend
#
# The app calls the API at the relative path /api/v1 (see
# src/services/apiClient.ts) rather than a hardcoded host — in dev, Vite's
# proxy forwards that to the backend (vite.config.ts); here, nginx.conf
# does the same job for the built static files.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS serve
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -q -O /dev/null http://localhost/ || exit 1
