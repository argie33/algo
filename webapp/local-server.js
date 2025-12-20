#!/usr/bin/env node

/**
 * Local Development Server
 * Wraps Lambda handler for local testing on port 3001
 * For production: Uses AWS Lambda + API Gateway
 */

const express = require("express");
const cors = require("cors");
const path = require("path");

// Load environment from .env.local
require("dotenv").config({ path: path.resolve(__dirname, "../.env.local") });

// Import Lambda handler
const { handler } = require("./lambda/index.js");

const app = express();
const PORT = process.env.PORT || 3001;

// CORS configuration
app.use(
  cors({
    origin: [
      "http://localhost:5173",
      "http://localhost:5174",
      "http://localhost:5175",
      "http://localhost:3000",
    ],
    credentials: true,
    methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allowedHeaders: ["Content-Type", "Authorization"],
  })
);

// Middleware
app.use(express.json({ limit: "10mb" }));
app.use(express.urlencoded({ limit: "10mb", extended: true }));

// Convert Express request/response to Lambda event/context
app.use(async (req, res, next) => {
  // Handle all routes through Lambda handler
  // Build Lambda event from Express request
  const event = {
    httpMethod: req.method,
    path: req.path,
    queryStringParameters: req.query || null,
    headers: req.headers,
    body: req.body ? JSON.stringify(req.body) : null,
    requestContext: {
      http: {
        method: req.method,
        path: req.path,
      },
    },
  };

  // Lambda context
  const context = {
    succeed: (data) => res.status(200).json(data),
    fail: (error) => res.status(500).json({ error: error.message }),
    done: (error, data) => {
      if (error) {
        res.status(500).json({ error: error.message });
      } else {
        res.status(200).json(data);
      }
    },
  };

  try {
    const result = await handler(event, context);

    // Handle response format from Lambda
    if (result && typeof result === "object") {
      const statusCode = result.statusCode || 200;
      let body = result.body;

      // Parse body if it's a string
      if (typeof body === "string") {
        try {
          body = JSON.parse(body);
        } catch (e) {
          // Keep as string if not JSON
        }
      }

      res.status(statusCode).json(body || result);
    } else {
      res.status(200).json(result);
    }
  } catch (error) {
    console.error("Error handling request:", error);
    res.status(500).json({
      error: error.message || "Internal Server Error",
      success: false,
    });
  }
});


// Start server
app.listen(PORT, "0.0.0.0", () => {
  console.log(`
╔════════════════════════════════════════════════════════════╗
║         LOCAL API SERVER RUNNING                           ║
╚════════════════════════════════════════════════════════════╝

  🚀 Server: http://localhost:${PORT}
  📡 Frontend: http://localhost:5173
  ✅ Health:  http://localhost:${PORT}/api/health

  Environment: ${process.env.NODE_ENV || "development"}
  Database:   ${process.env.DB_HOST}:${process.env.DB_PORT}

  Press Ctrl+C to stop
  `);
});

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\n\n✋ Shutting down gracefully...");
  process.exit(0);
});

process.on("SIGTERM", () => {
  console.log("\n\n✋ Shutting down gracefully...");
  process.exit(0);
});
