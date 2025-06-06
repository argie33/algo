# Use the official Node.js runtime as the base image
FROM node:18-alpine

# Set the working directory in the container
WORKDIR /app

# Copy package files first
COPY package*.json ./

# Install production dependencies with fallback options
RUN npm ci --only=production || \
    (npm install --only=production && npm cache clean --force)

# Copy the source code
COPY src ./src

# Create a non-root user to run the application
RUN addgroup -g 1001 -S nodejs
RUN adduser -S nodeapp -u 1001

# Change ownership of the /app directory to the nodejs user
RUN chown -R nodeapp:nodejs /app
USER nodeapp

# Expose the port the app runs on
EXPOSE 3001

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3001/api/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) }).on('error', () => process.exit(1))"

# Command to run the application
CMD ["node", "src/server.js"]
