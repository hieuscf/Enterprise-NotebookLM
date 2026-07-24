# =============================================================================
# File: Dockerfile
# Module/Service: Web App
# Layer: UI
# Purpose: Multi-stage Next.js production image for the Web App container.
# Responsibilities:
#   - Build Next.js app and serve via `next start`
# Dependencies:
#   - Node 22, package.json
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: docker-compose.yml, frontend/app
# Important Notes: Phase 1.1 skeleton — no LLM calls from frontend.
# =============================================================================

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000 \
    HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
