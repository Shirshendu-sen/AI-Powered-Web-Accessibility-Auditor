# Scanner service — Playwright + axe-core in an official Playwright image
# so Chromium's shared libs are already provided by the base.
#
# Version tag MUST match services/scanner/package.json's playwright version,
# per the guide's Common Issues note about mismatched Chromium bundles.
FROM mcr.microsoft.com/playwright:v1.61.1-jammy

ENV NODE_ENV=production \
    PORT=4000

WORKDIR /app

# Copy manifest first so dependency install layer stays cacheable when
# only src/ changes.
COPY package.json package-lock.json ./

# npm ci gives a strictly reproducible install from the lockfile.
# --omit=dev drops eslint/etc if any land later.
RUN npm ci --omit=dev

COPY src ./src

EXPOSE 4000

# The Phase 2 close-context-per-scan discipline is enforced by
# src/scan.js — Docker cannot fix a memory leak in application logic.
CMD ["node", "src/server.js"]
