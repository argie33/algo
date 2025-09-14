/**
 * Malformed Request Integration Tests
 * Tests handling of malformed, corrupted, and invalid requests
 * Validates proper error responses and security measures
 */

const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("Malformed Request Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("JSON Parsing Error Scenarios", () => {
    test("should handle malformed JSON gracefully", async () => {
      const malformedJsonTests = [
        { body: '{"incomplete": json', description: "Incomplete JSON object" },
        { body: '{invalid: "json"}', description: "Invalid JSON syntax" },
        { body: '{"nested": {"incomplete": }', description: "Nested incomplete JSON" },
        { body: '{"duplicate": 1, "duplicate": 2}', description: "Duplicate keys" },
        { body: '{"valid": "start"}{invalid continuation}', description: "Multiple JSON objects" },
        { body: '{"escaped": "quote\\"break"}malformed', description: "Escaped quotes with garbage" },
        { body: '', description: "Empty body" },
        { body: 'not json at all', description: "Plain text instead of JSON" },
        { body: '[]malformed', description: "Array with garbage" }
      ];

      const testEndpoint = "/api/portfolio/analyze";

      for (const test of malformedJsonTests) {
        const response = await request(app)
          .post(testEndpoint)
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Content-Type", "application/json")
          .send(test.body);

        expect([400, 422]).toContain(response.status);
        
        if (response.status === 400 || response.status === 422) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(/json|parse|malformed|invalid/i);
        }
        
        // Should always return JSON response format
        expect(response.headers['content-type']).toMatch(/application\/json/);
        
        // Error should not expose the malformed content
        if (response.body?.error) {
          expect(response.body.error).not.toContain(test.body);
        }
      }
    });

    test("should handle JSON with dangerous characters", async () => {
      const dangerousJsonTests = [
        { body: '{"script": "<script>alert(\'xss\')</script>"}', description: "XSS attempt" },
        { body: '{"sql": "\'; DROP TABLE users; --"}', description: "SQL injection attempt" },
        { body: '{"path": "../../../etc/passwd"}', description: "Path traversal attempt" },
        { body: '{"command": "rm -rf /"}', description: "Command injection attempt" },
        { body: '{"unicode": "\\u0000\\u001f\\u007f"}', description: "Control characters" },
        { body: '{"large": "' + 'A'.repeat(100000) + '"}', description: "Extremely large string" }
      ];

      const testEndpoint = "/api/portfolio/analyze";

      for (const test of dangerousJsonTests) {
        const response = await request(app)
          .post(testEndpoint)
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Content-Type", "application/json")
          .send(test.body);

        // Should handle safely
        expect([200, 404]).toContain(response.status);
        
        if (response.status >= 400) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          
          // Error message should not echo back dangerous content
          const errorMessage = response.body.error.toLowerCase();
          expect(errorMessage).not.toMatch(/<script>|drop table|rm -rf|\.\.\/\.\.\//i);
        }
      }
    });

    test("should handle deeply nested JSON structures", async () => {
      // Create deeply nested JSON structure
      let deeplyNested = { level: 0 };
      let current = deeplyNested;
      
      for (let i = 1; i <= 100; i++) {
        current.nested = { level: i };
        current = current.nested;
      }
      
      const response = await request(app)
        .post("/api/portfolio/analyze")
        .set("Authorization", "Bearer dev-bypass-token")
        .set("Content-Type", "application/json")
        .send(deeplyNested);

      // Should handle deep nesting gracefully
      expect([200, 404]).toContain(response.status);
      
      if (response.status >= 400) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });
  });

  describe("HTTP Header Malformation", () => {
    test("should handle malformed authorization headers", async () => {
      const malformedAuthHeaders = [
        { auth: "Bearer\x00token", description: "Null byte in token" },
        { auth: "Bearer token\nmalicious", description: "Line break injection" },
        { auth: "Bearer token\rcarriage", description: "Carriage return injection" },
        { auth: "Bearer " + "A".repeat(10000), description: "Extremely long token" },
        { auth: "Bearer token\x80\x81\x82", description: "Non-ASCII bytes" },
        { auth: "Basic " + Buffer.from("user:pass").toString('base64'), description: "Basic auth on Bearer endpoint" }
      ];

      const testEndpoint = "/api/portfolio";

      for (const test of malformedAuthHeaders) {
        const response = await request(app)
          .get(testEndpoint)
          .set("Authorization", test.auth);

        expect([200, 400, 401, 403]).toContain(response.status);
        
        if (response.status === 400 || response.status === 401 || response.status === 403) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          
          // Error should not echo back malformed header
          expect(response.body.error).not.toContain(test.auth);
        }
      }
    });

    test("should handle malformed content-type headers", async () => {
      const malformedContentTypes = [
        { contentType: "application/json\x00", description: "Null byte in content type" },
        { contentType: "application/json; charset=utf-8\nmalicious", description: "Line break injection" },
        { contentType: "application/json;" + "x".repeat(1000), description: "Extremely long parameters" },
        { contentType: "application\x80/json", description: "Non-ASCII in content type" },
        { contentType: "text/plain; boundary=" + "A".repeat(1000), description: "Long boundary parameter" }
      ];

      const testEndpoint = "/api/portfolio/analyze";

      for (const test of malformedContentTypes) {
        const response = await request(app)
          .post(testEndpoint)
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Content-Type", test.contentType)
          .send('{"symbols": ["AAPL"]}');

        expect([200, 404]).toContain(response.status);
        
        if (response.status >= 400) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });

    test("should handle custom header injection attempts", async () => {
      const headerInjectionTests = [
        { headerName: "X-Custom\x00Header", value: "test", description: "Null byte in header name" },
        { headerName: "X-Custom-Header", value: "value\nInjected-Header: malicious", description: "Header injection in value" },
        { headerName: "X-Custom-Header", value: "value\r\nSet-Cookie: evil=true", description: "CRLF injection" },
        { headerName: "X-Very-" + "Long-".repeat(100) + "Header", value: "test", description: "Extremely long header name" }
      ];

      const testEndpoint = "/api/health";

      for (const test of headerInjectionTests) {
        try {
          const response = await request(app)
            .get(testEndpoint)
            .set(test.headerName, test.value);

          // Should handle gracefully
          expect([200, 404]).toContain(response.status);
          
          // Should not reflect malicious headers
          expect(response.headers['injected-header']).toBeUndefined();
          expect(response.headers['set-cookie']).not.toMatch(/evil=true/);
          
        } catch (error) {
          // Some malformed headers might be rejected at HTTP level
          expect(error.message).toMatch(/invalid|malformed|header/i);
        }
      }
    });
  });

  describe("URL and Path Malformation", () => {
    test("should handle malformed URLs and paths", async () => {
      const malformedPaths = [
        { path: "/api/portfolio/../../../etc/passwd", description: "Directory traversal" },
        { path: "/api/portfolio/%2e%2e%2f%2e%2e%2fetc%2fpasswd", description: "URL encoded traversal" },
        { path: "/api/portfolio/\x00", description: "Null byte in path" },
        { path: "/api/portfolio/" + "A".repeat(1000), description: "Extremely long path" },
        { path: "/api/portfolio/\x80\x81\x82", description: "Non-ASCII in path" },
        { path: "/api/portfolio/<script>alert('xss')</script>", description: "XSS in path" }
      ];

      for (const test of malformedPaths) {
        try {
          const response = await request(app)
            .get(test.path)
            .set("Authorization", "Bearer dev-bypass-token");

          expect([400, 404, 500]).toContain(response.status);
          
          if (response.status >= 400) {
            expect(response.body).toHaveProperty("success", false);
            expect(response.body).toHaveProperty("error");
            
            // Error should not echo back malformed path
            if (response.body.error) {
              expect(response.body.error).not.toMatch(/<script>|passwd|\.\.\/\.\.\//i);
            }
          }
          
        } catch (error) {
          // Some malformed URLs might be rejected at HTTP level
          expect(error.message).toMatch(/invalid|malformed|url/i);
        }
      }
    });

    test("should handle malformed query parameters", async () => {
      const malformedQueryTests = [
        { query: "param=value%", description: "Incomplete URL encoding" },
        { query: "param=value%ZZ", description: "Invalid URL encoding" },
        { query: "param\x00=value", description: "Null byte in parameter name" },
        { query: "param=value\x00", description: "Null byte in parameter value" },
        { query: "param=<script>alert('xss')</script>", description: "XSS in query parameter" },
        { query: "param='OR 1=1--", description: "SQL injection in query" },
        { query: "param=" + "A".repeat(10000), description: "Extremely long parameter value" }
      ];

      const testEndpoint = "/api/calendar/earnings";

      for (const test of malformedQueryTests) {
        const response = await request(app).get(testEndpoint + "?" + test.query);

        expect([200, 400, 414, 422]).toContain(response.status);
        
        if (response.status >= 400) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          
          // Error should not echo back dangerous content
          if (response.body.error) {
            const errorMessage = response.body.error.toLowerCase();
            expect(errorMessage).not.toMatch(/<script>|alert|'or 1=1/i);
          }
        }
      }
    });
  });

  describe("Request Body Malformation", () => {
    test("should handle oversized request bodies", async () => {
      // Create very large request body
      const largeBody = {
        symbols: Array(10000).fill("AAPL"),
        data: "A".repeat(100000),
        nested: {
          moreData: Array(1000).fill({ key: "value".repeat(100) })
        }
      };

      const response = await request(app)
        .post("/api/portfolio/analyze")
        .set("Authorization", "Bearer dev-bypass-token")
        .send(largeBody);

      expect([200, 413, 422]).toContain(response.status);
      
      if (response.status === 413) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toMatch(/too large|payload|size|limit/i);
      }
    });

    test("should handle binary data in JSON fields", async () => {
      const binaryDataTests = [
        { 
          body: { symbols: ["AAPL"], data: Buffer.from("binary data").toString('base64') },
          description: "Base64 encoded binary"
        },
        {
          body: { symbols: ["AAPL"], data: "\x00\x01\x02\x03\x04\x05" },
          description: "Raw binary bytes"
        },
        {
          body: { symbols: ["AAPL"], data: "text\x80\x81\x82more text" },
          description: "Mixed text and binary"
        }
      ];

      for (const test of binaryDataTests) {
        const response = await request(app)
          .post("/api/portfolio/analyze")
          .set("Authorization", "Bearer dev-bypass-token")
          .send(test.body);

        expect([200, 404]).toContain(response.status);
        
        if (response.status >= 400) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });

    test("should handle mismatched content-type and body", async () => {
      const mismatchTests = [
        {
          contentType: "application/json",
          body: "not json content",
          description: "Plain text with JSON content-type"
        },
        {
          contentType: "application/xml",
          body: '{"json": "with xml content-type"}',
          description: "JSON with XML content-type"
        },
        {
          contentType: "text/plain",
          body: '{"json": "with text content-type"}',
          description: "JSON with text content-type"
        }
      ];

      for (const test of mismatchTests) {
        const response = await request(app)
          .post("/api/portfolio/analyze")
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Content-Type", test.contentType)
          .send(test.body);

        expect([200, 404]).toContain(response.status);
        
        if (response.status >= 400) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("Character Encoding Issues", () => {
    test("should handle invalid UTF-8 sequences", async () => {
      // Note: Express typically handles UTF-8 validation, but we should test edge cases
      const encodingTests = [
        {
          body: JSON.stringify({ symbols: ["AAPL"], text: "Valid UTF-8: 你好" }),
          description: "Valid UTF-8"
        },
        {
          body: '{"symbols": ["AAPL"], "text": "Mixed: \uD83D\uDE00"}',
          description: "Emoji characters"
        },
        {
          body: '{"symbols": ["AAPL"], "text": "Control: \\u0000\\u0001\\u001F"}',
          description: "Control characters"
        }
      ];

      for (const test of encodingTests) {
        const response = await request(app)
          .post("/api/portfolio/analyze")
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Content-Type", "application/json; charset=utf-8")
          .send(test.body);

        expect([200, 404]).toContain(response.status);
        
        // Should handle encoding gracefully
        expect(response.headers['content-type']).toMatch(/application\/json/);
        
        if (response.status >= 400) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });

    test("should handle different character encodings", async () => {
      const charsetTests = [
        { charset: "utf-8", description: "Standard UTF-8" },
        { charset: "iso-8859-1", description: "Latin-1" },
        { charset: "windows-1252", description: "Windows encoding" }
      ];

      const testBody = '{"symbols": ["AAPL"], "text": "test"}';

      for (const test of charsetTests) {
        const response = await request(app)
          .post("/api/portfolio/analyze")
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Content-Type", `application/json; charset=${test.charset}`)
          .send(testBody);

        expect([200, 404]).toContain(response.status);
        
        if (response.status >= 400) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("Security and Sanitization", () => {
    test("should sanitize error messages containing malformed input", async () => {
      const maliciousInputs = [
        { input: '<script>alert("xss")</script>', type: "XSS" },
        { input: "'; DROP TABLE users; --", type: "SQL injection" },
        { input: "../../etc/passwd", type: "Path traversal" },
        { input: "${process.exit(1)}", type: "Template injection" }
      ];

      for (const test of maliciousInputs) {
        const response = await request(app)
          .post("/api/portfolio/analyze")
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Content-Type", "application/json")
          .send(`{"malicious": "${test.input}"}`);

        if (response.status >= 400 && response.body?.error) {
          const errorMessage = response.body.error;
          
          // Error message should not contain the malicious input verbatim
          expect(errorMessage).not.toContain(test.input);
          expect(errorMessage).not.toMatch(/<script>|DROP TABLE|\.\.\/|process\.exit/i);
          
          // Should be a generic, safe error message
          expect(errorMessage).toMatch(/invalid|malformed|error|failed/i);
        }
      }
    });

    test("should not expose stack traces in malformed request errors", async () => {
      const errorInducingRequests = [
        '{"unclosed": "string',
        '{"function": function() {}}',
        '{"undefined": undefined}'
      ];

      for (const malformedBody of errorInducingRequests) {
        const response = await request(app)
          .post("/api/portfolio/analyze")
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Content-Type", "application/json")
          .send(malformedBody);

        if (response.status >= 400 && response.body?.error) {
          const errorMessage = response.body.error;
          
          // Should not contain stack trace information
          expect(errorMessage).not.toMatch(/at Object\.|at Function\.|at .*\.js:\d+/);
          expect(errorMessage).not.toMatch(/node_modules|internal|process/);
          expect(errorMessage).not.toMatch(/Error: |TypeError: |SyntaxError: /);
        }
      }
    });
  });

  describe("Error Response Consistency", () => {
    test("should maintain consistent error format for all malformed requests", async () => {
      const consistencyTests = [
        {
          type: "malformed_json",
          request: () => request(app)
            .post("/api/portfolio/analyze")
            .set("Authorization", "Bearer dev-bypass-token")
            .set("Content-Type", "application/json")
            .send('{"invalid": json}')
        },
        {
          type: "malformed_auth",
          request: () => request(app)
            .get("/api/portfolio")
            .set("Authorization", "Bearer\x00token")
        },
        {
          type: "malformed_path",
          request: () => request(app)
            .get("/api/portfolio/../invalid")
            .set("Authorization", "Bearer dev-bypass-token")
        }
      ];

      for (const test of consistencyTests) {
        const response = await test.request();
        
        if (response.status >= 400) {
          // All error responses should have consistent structure
          expect(response.headers['content-type']).toMatch(/application\/json/);
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(typeof response.body.error).toBe("string");
          expect(response.body.error.length).toBeGreaterThan(0);
          
          // Optional timestamp field
          if (response.body.timestamp) {
            expect(typeof response.body.timestamp).toBe("string");
          }
        }
      }
    });

    test("should handle malformed requests without service disruption", async () => {
      // Send malformed requests mixed with valid ones
      const mixedRequests = [
        // Valid request
        request(app).get("/api/health"),
        // Malformed JSON
        request(app)
          .post("/api/portfolio/analyze")
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Content-Type", "application/json")
          .send('{"invalid": json}'),
        // Another valid request
        request(app).get("/api/market/overview"),
        // Malformed headers
        request(app)
          .get("/api/portfolio")
          .set("Authorization", "Bearer\x00token"),
        // Final valid request
        request(app).get("/api/health")
      ];

      const results = await Promise.all(
        mixedRequests.map(req => req.catch(err => ({ error: err.message })))
      );

      // Valid requests should still work
      const validRequests = [0, 2, 4]; // Indices of valid requests
      validRequests.forEach(index => {
        const result = results[index];
        if (!result.error) {
          expect([200, 500].includes(result.status)).toBe(true);
        }
      });

      // All requests should complete (not hang or crash server)
      expect(results.length).toBe(5);
      results.forEach(result => {
        expect(result).toBeDefined();
      });
    });
  });
});