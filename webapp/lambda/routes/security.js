// Security Routes
// API endpoints for security monitoring, validation, and administration

const express = require('express');
const router = express.Router();
const SecurityService = require('../services/securityService');

// Initialize security service
const securityService = new SecurityService();

// Security metrics endpoint
router.get('/metrics', async (req, res) => {
  try {
    const timeWindow = parseInt(req.query.window) || 3600000; // 1 hour default
    const metrics = securityService.getSecurityMetrics(timeWindow);
    
    res.json({
      success: true,
      data: metrics,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Security metrics failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get security metrics',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Rate limit status
router.get('/rate-limits', async (req, res) => {
  try {
    const identifier = req.query.identifier || req.ip;
    const category = req.query.category || 'api';
    
    const status = securityService.checkRateLimit(identifier, category, req);
    
    res.json({
      success: true,
      data: {
        identifier,
        category,
        status,
        isBlocked: !status.allowed,
        remaining: status.allowed ? status.limit - status.requests : 0
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Rate limit check failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to check rate limit status',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Input validation test
router.post('/validate', async (req, res) => {
  try {
    const { input, schema, options = {} } = req.body;
    
    if (!input) {
      return res.status(400).json({
        success: false,
        error: 'Input required',
        message: 'Input field is required for validation'
      });
    }
    
    const validation = securityService.validateInput(input, schema, options);
    
    res.json({
      success: true,
      data: {
        input: typeof input === 'string' ? input.substring(0, 100) : input,
        schema,
        validation,
        options
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Input validation failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to validate input',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Object validation test
router.post('/validate-object', async (req, res) => {
  try {
    const { object, schema } = req.body;
    
    if (!object || !schema) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'Both object and schema are required'
      });
    }
    
    const validation = securityService.validateObject(object, schema);
    
    res.json({
      success: true,
      data: {
        validation,
        schema,
        fieldCount: Object.keys(object).length
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Object validation failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to validate object',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Password strength validation
router.post('/validate-password', async (req, res) => {
  try {
    const { password } = req.body;
    
    if (!password) {
      return res.status(400).json({
        success: false,
        error: 'Password required',
        message: 'Password field is required'
      });
    }
    
    const validation = securityService.validatePassword(password);
    
    res.json({
      success: true,
      data: {
        ...validation,
        password: '[REDACTED]' // Never return the actual password
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Password validation failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to validate password',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Generate CSRF token
router.post('/csrf-token', async (req, res) => {
  try {
    const sessionId = req.body.sessionId || req.sessionID || 'default-session';
    const token = securityService.generateCSRFToken(sessionId);
    
    res.json({
      success: true,
      data: {
        token,
        sessionId: sessionId !== 'default-session' ? sessionId : '[GENERATED]',
        expiresIn: 3600000 // 1 hour
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('CSRF token generation failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate CSRF token',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Validate CSRF token
router.post('/validate-csrf', async (req, res) => {
  try {
    const { token, sessionId } = req.body;
    
    if (!token || !sessionId) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'Both token and sessionId are required'
      });
    }
    
    const isValid = securityService.validateCSRFToken(token, sessionId);
    
    res.json({
      success: true,
      data: {
        valid: isValid,
        sessionId: '[REDACTED]',
        token: '[REDACTED]'
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('CSRF validation failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to validate CSRF token',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Security events (admin only)
router.get('/events', async (req, res) => {
  try {
    // In production, this would require admin authentication
    const limit = parseInt(req.query.limit) || 50;
    const severity = req.query.severity;
    const type = req.query.type;
    
    let events = [...securityService.securityEvents];
    
    // Filter by severity
    if (severity) {
      events = events.filter(event => event.severity === severity.toUpperCase());
    }
    
    // Filter by type
    if (type) {
      events = events.filter(event => event.type === type.toUpperCase());
    }
    
    // Sort by most recent and limit
    events = events
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, limit);
    
    res.json({
      success: true,
      data: {
        events,
        count: events.length,
        totalEvents: securityService.securityEvents.length,
        filters: { severity, type, limit }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Security events retrieval failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve security events',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Activity monitoring
router.post('/monitor-activity', async (req, res) => {
  try {
    const { userId, activity } = req.body;
    
    if (!userId || !activity) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'userId and activity are required'
      });
    }
    
    // Enhance activity with request data
    const enhancedActivity = {
      ...activity,
      ip: req.ip,
      userAgent: req.get('User-Agent'),
      timestamp: Date.now()
    };
    
    const patterns = securityService.detectUnusualActivity(userId, enhancedActivity);
    
    res.json({
      success: true,
      data: {
        userId: '[REDACTED]',
        activityMonitored: true,
        patterns,
        alert: patterns.unusual
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Activity monitoring failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to monitor activity',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Security headers test
router.get('/headers', async (req, res) => {
  try {
    const headers = securityService.getSecurityHeaders();
    
    res.json({
      success: true,
      data: {
        securityHeaders: headers,
        currentHeaders: Object.fromEntries(
          Object.entries(res.getHeaders()).filter(([key]) => 
            key.toLowerCase().startsWith('x-') || 
            key.toLowerCase().includes('security') ||
            key.toLowerCase().includes('content-security-policy')
          )
        )
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Security headers test failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get security headers',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Blocked IPs management (admin only)
router.get('/blocked-ips', async (req, res) => {
  try {
    const blockedIPs = Array.from(securityService.blockedIPs);
    
    res.json({
      success: true,
      data: {
        blockedIPs: blockedIPs.map(ip => ip.substring(0, ip.lastIndexOf('.')) + '.***'), // Partial masking
        count: blockedIPs.length
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Blocked IPs retrieval failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve blocked IPs',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Unblock IP (admin only)
router.post('/unblock-ip', async (req, res) => {
  try {
    const { ip } = req.body;
    
    if (!ip) {
      return res.status(400).json({
        success: false,
        error: 'IP address required',
        message: 'IP field is required'
      });
    }
    
    const wasBlocked = securityService.blockedIPs.has(ip);
    securityService.blockedIPs.delete(ip);
    
    // Log the unblock event
    securityService.logSecurityEvent('IP_UNBLOCKED', {
      ip: ip.substring(0, ip.lastIndexOf('.')) + '.***',
      wasBlocked,
      timestamp: new Date().toISOString()
    });
    
    res.json({
      success: true,
      data: {
        ip: ip.substring(0, ip.lastIndexOf('.')) + '.***',
        wasBlocked,
        currentlyBlocked: false
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('IP unblock failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to unblock IP',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Cleanup security data
router.post('/cleanup', async (req, res) => {
  try {
    securityService.cleanup();
    
    res.json({
      success: true,
      data: {
        message: 'Security service cleanup completed',
        activeRateLimiters: securityService.rateLimiters.size,
        securityEvents: securityService.securityEvents.length,
        blockedIPs: securityService.blockedIPs.size
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Security cleanup failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to cleanup security data',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Health check
router.get('/health', async (req, res) => {
  try {
    // Test core security functions
    const testValidation = securityService.validateInput('TEST123', 'symbol');
    const testPassword = securityService.validatePassword('TestPass123!');
    const testRateLimit = securityService.checkRateLimit('test-ip', 'api');
    
    res.json({
      success: true,
      message: 'Security services operational',
      services: {
        inputValidation: {
          status: testValidation.valid ? 'operational' : 'error',
          test: testValidation.valid
        },
        passwordValidation: {
          status: testPassword.valid ? 'operational' : 'error',
          strength: testPassword.strength
        },
        rateLimiting: {
          status: 'operational',
          allowed: testRateLimit.allowed
        },
        securityMonitoring: {
          status: 'operational',
          activeEvents: securityService.securityEvents.length,
          blockedIPs: securityService.blockedIPs.size
        }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Security health check failed:', error);
    res.status(503).json({
      success: false,
      error: 'Security services unhealthy',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;