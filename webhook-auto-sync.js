#!/usr/bin/env node

/**
 * Webhook Auto-Sync Endpoint
 * Immediate webhook-triggered document sync routine
 * 
 * Usage:
 * 1. POST to this endpoint after any significant changes
 * 2. Automatically syncs 4 core documents
 * 3. Updates todo list with current priorities
 * 4. Returns next actions to work on
 */

const express = require('express');
const crypto = require('crypto');
const DocumentSyncManager = require('./auto-sync-docs');

const app = express();
const port = process.env.PORT || 3001;

// Middleware
app.use(express.json());

// Webhook signature verification (if using GitHub webhooks)
function verifySignature(req, res, next) {
  const signature = req.headers['x-hub-signature-256'];
  const secret = process.env.WEBHOOK_SECRET;
  
  if (!signature || !secret) {
    return next(); // Skip verification if not configured
  }
  
  const hmac = crypto.createHmac('sha256', secret);
  const digest = 'sha256=' + hmac.update(req.body).digest('hex');
  
  if (crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(digest))) {
    next();
  } else {
    res.status(401).json({ error: 'Invalid signature' });
  }
}

// Main webhook endpoint
app.post('/webhook/auto-sync', verifySignature, async (req, res) => {
  console.log('🔔 Webhook triggered: Auto-Sync Documentation Routine');
  
  try {
    const syncManager = new DocumentSyncManager();
    const result = await syncManager.run();
    
    res.json({
      success: true,
      message: 'Auto-sync completed successfully',
      nextActions: result,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Auto-sync webhook failed:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'auto-sync-webhook',
    timestamp: new Date().toISOString()
  });
});

// Manual trigger endpoint (for development)
app.post('/manual-sync', async (req, res) => {
  console.log('🔧 Manual sync triggered');
  
  try {
    const syncManager = new DocumentSyncManager();
    const result = await syncManager.run();
    
    res.json({
      success: true,
      message: 'Manual sync completed successfully',
      nextActions: result,
      workflow: {
        step1: 'Review the next actions below',
        step2: 'Update todos as you complete work',
        step3: 'Run manual sync after significant changes',
        step4: 'Follow operational guidelines in CLAUDE.md'
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Manual sync failed:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Start server
app.listen(port, () => {
  console.log(`🚀 Auto-Sync Webhook listening on port ${port}`);
  console.log(`📡 Webhook endpoint: POST /webhook/auto-sync`);
  console.log(`🔧 Manual trigger: POST /manual-sync`);
  console.log(`💚 Health check: GET /health`);
});

module.exports = app;