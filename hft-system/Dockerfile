# Multi-stage build for optimized production image
FROM node:20-alpine AS builder

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./
COPY tsconfig.json ./

# Install dependencies
RUN npm ci --only=production && npm cache clean --force

# Copy source code
COPY src ./src

# Build TypeScript
RUN npm run build

# Production image
FROM node:20-alpine AS production

# Install dumb-init for proper signal handling
RUN apk add --no-cache dumb-init

# Create app user
RUN addgroup -g 1001 -S nodejs
RUN adduser -S hftuser -u 1001

# Set working directory
WORKDIR /app

# Copy built application
COPY --from=builder --chown=hftuser:nodejs /app/dist ./dist
COPY --from=builder --chown=hftuser:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=hftuser:nodejs /app/package*.json ./

# Switch to non-root user
USER hftuser

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node dist/src/health-check.js || exit 1

# Start application
ENTRYPOINT ["dumb-init", "--"]
CMD ["node", "dist/src/main.js"]
