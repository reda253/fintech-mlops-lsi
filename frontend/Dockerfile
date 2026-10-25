# syntax=docker/dockerfile:1
FROM node:24-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
RUN npm run lint && npm test

# These settings are public and are compiled into the browser bundle.
ARG VITE_USE_MOCKS=true
ARG VITE_AUTH_MODE=demo
ARG VITE_GRAFANA_URL=http://localhost:3000
ENV VITE_USE_MOCKS=$VITE_USE_MOCKS \
    VITE_AUTH_MODE=$VITE_AUTH_MODE \
    VITE_API_BASE_URL=/api/v1 \
    VITE_GRAFANA_URL=$VITE_GRAFANA_URL
RUN case "$VITE_USE_MOCKS" in true|false) ;; *) exit 1 ;; esac \
    && case "$VITE_AUTH_MODE" in demo|jwt) ;; *) exit 1 ;; esac \
    && npm run build

FROM nginx/nginx-unprivileged:stable-alpine AS runtime
USER root
RUN addgroup -S -g 10001 fintech \
    && adduser -S -D -H -u 10001 -G fintech fintech
COPY docker/nginx.conf.template /etc/nginx/frontend.conf.template
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/frontend-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/frontend-entrypoint.sh
COPY --from=build --chown=10001:10001 /workspace/dist/ /usr/share/nginx/html/
USER 10001:10001
ENV GATEWAY_UPSTREAM=http://api-gateway:8080
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
ENTRYPOINT ["/usr/local/bin/frontend-entrypoint.sh"]
CMD []
