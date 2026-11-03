# syntax=docker/dockerfile:1
# Multi-stage build for the Next.js dashboard (output: "standalone").

FROM node:22-alpine AS deps
WORKDIR /app
# Optional organisation CA certificates (see ../certs/README.md) for TLS-inspecting networks.
# Appended to the bundle before any download (apk/npm) so they apply to the whole build.
COPY --from=certs . /tmp/extra-ca/
RUN for f in /tmp/extra-ca/*.crt; do [ -f "$f" ] && cat "$f" >> /etc/ssl/certs/ca-certificates.crt; done; true
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS builder
WORKDIR /app
# Rewrites (/api/* -> backend) are resolved at build time and baked into the
# standalone server, so the backend URL must be known here.
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
ARG API_INTERNAL_URL=http://api:8000
# Informational at runtime; the value used by rewrites is the build-time one above.
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
RUN addgroup -S -g 1001 nodejs && adduser -S -u 1001 -G nodejs nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/login >/dev/null 2>&1 || exit 1
CMD ["node", "server.js"]
