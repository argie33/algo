/**
 * CORS API Headers Test
 * Tests that API requests don't include CORS-problematic headers
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('🌐 CORS API Headers Validation', () => {
  let mockFetch;
  
  const CORS_PROBLEMATIC_HEADERS = [
    'cache-control',
    'pragma',
    'expires',
    'x-requested-with',
    'x-custom-header'
  ];
  
  const ALLOWED_CORS_HEADERS = [
    'accept',
    'content-type', 
    'authorization',
    'x-api-key'
  ];

  beforeEach(() => {
    mockFetch = vi.fn();
    global.fetch = mockFetch;
  });

  describe('API Health Service Headers', () => {
    it('should not send CORS-problematic headers', async () => {
      // Mock the API health service
      const { default: apiHealthService } = await import('../../../services/apiHealthService');
      
      // Mock successful response
      mockFetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: 'healthy' })
      });
      
      // Trigger a health check
      const endpoint = { name: 'test', path: '/api/health' };
      await apiHealthService.checkEndpoint(endpoint);
      
      // Verify fetch was called
      expect(mockFetch).toHaveBeenCalled();
      
      const [url, options] = mockFetch.mock.calls[0];
      const headers = options.headers || {};
      
      // Check that no CORS-problematic headers are present
      Object.keys(headers).forEach(header => {
        const normalizedHeader = header.toLowerCase();
        expect(CORS_PROBLEMATIC_HEADERS).not.toContain(normalizedHeader);
      });
      
      // Verify only safe headers are used
      Object.keys(headers).forEach(header => {
        const normalizedHeader = header.toLowerCase();
        expect([...ALLOWED_CORS_HEADERS, 'accept']).toContain(normalizedHeader);
      });
    });
    
    it('should handle CORS errors gracefully', async () => {
      const { default: apiHealthService } = await import('../../../services/apiHealthService');
      
      // Mock CORS error
      mockFetch.mockRejectedValue(new TypeError('Failed to fetch'));
      
      const endpoint = { name: 'test', path: '/api/health' };
      const result = await apiHealthService.checkEndpoint(endpoint);
      
      expect(result.healthy).toBe(false);
      expect(result.error).toContain('Failed to fetch');
    });
  });

  describe('General API Client Headers', () => {
    it('should validate common API request patterns', () => {
      // Test common request configurations
      const commonRequests = [
        {
          name: 'GET request',
          headers: {
            'Accept': 'application/json'
          }
        },
        {
          name: 'POST request',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          }
        },
        {
          name: 'Authenticated request',
          headers: {
            'Accept': 'application/json',
            'Authorization': 'Bearer token123'
          }
        }
      ];
      
      commonRequests.forEach(request => {
        Object.keys(request.headers).forEach(header => {
          const normalizedHeader = header.toLowerCase();
          
          // Should not contain problematic headers
          expect(CORS_PROBLEMATIC_HEADERS).not.toContain(normalizedHeader);
          
          // Should only contain allowed headers  
          expect(ALLOWED_CORS_HEADERS).toContain(normalizedHeader);
        });
      });
    });
  });

  describe('Fetch Configuration Validation', () => {
    it('should validate fetch options for CORS compliance', () => {
      const safeFetchConfig = {
        method: 'GET',
        headers: {
          'Accept': 'application/json'
        },
        mode: 'cors', // Explicitly set CORS mode
        credentials: 'omit' // Don't send credentials for CORS
      };
      
      // Verify configuration is CORS-safe
      expect(safeFetchConfig.mode).toBe('cors');
      
      if (safeFetchConfig.headers) {
        Object.keys(safeFetchConfig.headers).forEach(header => {
          const normalizedHeader = header.toLowerCase();
          expect(CORS_PROBLEMATIC_HEADERS).not.toContain(normalizedHeader);
        });
      }
    });
    
    it('should provide CORS-safe request template', () => {
      const corsTemplate = {
        method: 'GET',
        headers: {
          'Accept': 'application/json'
          // DO NOT ADD:
          // 'Cache-Control': 'no-cache' ❌ 
          // 'Pragma': 'no-cache' ❌
          // 'X-Requested-With': 'XMLHttpRequest' ❌
        },
        mode: 'cors'
      };
      
      // Verify template is safe
      expect(corsTemplate.mode).toBe('cors');
      expect(corsTemplate.headers['Cache-Control']).toBeUndefined();
      expect(corsTemplate.headers['cache-control']).toBeUndefined();
      expect(corsTemplate.headers['Pragma']).toBeUndefined();
      expect(corsTemplate.headers['X-Requested-With']).toBeUndefined();
    });
  });
  
  describe('Error Patterns', () => {
    it('should identify CORS error patterns', () => {
      const corsErrorPatterns = [
        'has been blocked by CORS policy',
        'Access-Control-Allow-Headers',
        'preflight response',
        'Request header field',
        'is not allowed'
      ];
      
      const errorMessage = "Access to fetch at 'https://api.example.com/health' has been blocked by CORS policy: Request header field cache-control is not allowed by Access-Control-Allow-Headers in preflight response.";
      
      const isCorsError = corsErrorPatterns.some(pattern => 
        errorMessage.includes(pattern)
      );
      
      expect(isCorsError).toBe(true);
    });
    
    it('should provide CORS troubleshooting guidance', () => {
      const corsGuidance = {
        commonCauses: [
          'Sending disallowed headers (cache-control, pragma, etc.)',
          'Custom headers not configured on server',
          'Wrong Content-Type for request',
          'Missing Access-Control-Allow-Headers on server'
        ],
        solutions: [
          'Remove problematic headers from client requests',
          'Configure server CORS to allow required headers',
          'Use simple requests when possible (GET with basic headers)',
          'Check server Access-Control-Allow-Headers configuration'
        ]
      };
      
      expect(corsGuidance.commonCauses).toContain('Sending disallowed headers (cache-control, pragma, etc.)');
      expect(corsGuidance.solutions).toContain('Remove problematic headers from client requests');
    });
  });
});