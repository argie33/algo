/**
 * Test suite to validate the standardized response format
 * Ensures frontend and backend are aligned on response structure
 */

const apiResponse = require('../webapp/lambda/utils/apiResponse');

describe('Response Format Standardization', () => {
  describe('sendSuccess() - Single Object', () => {
    test('wraps single object under data key with statusCode', () => {
      const mockRes = {
        status: (code) => {
          mockRes.statusCode = code;
          return mockRes;
        },
        json: (body) => {
          mockRes.body = body;
          return mockRes;
        }
      };

      const data = {
        algo_enabled: true,
        portfolio: { total_value: 50000 }
      };

      apiResponse.sendSuccess(mockRes, data, 200);

      expect(mockRes.statusCode).toBe(200);
      expect(mockRes.body).toEqual({
        success: true,
        statusCode: 200,
        data: {
          algo_enabled: true,
          portfolio: { total_value: 50000 }
        },
        timestamp: expect.any(String)
      });
    });
  });

  describe('sendSuccess() - Array', () => {
    test('creates paginated response with items and pagination', () => {
      const mockRes = {
        status: (code) => {
          mockRes.statusCode = code;
          return mockRes;
        },
        json: (body) => {
          mockRes.body = body;
          return mockRes;
        }
      };

      const items = [{ id: 1 }, { id: 2 }];

      apiResponse.sendSuccess(mockRes, items, 200);

      expect(mockRes.statusCode).toBe(200);
      expect(mockRes.body).toEqual({
        success: true,
        statusCode: 200,
        items: items,
        pagination: {
          limit: 2,
          offset: 0,
          total: 2,
          page: 1,
          totalPages: 1,
          hasNext: false,
          hasPrev: false
        },
        timestamp: expect.any(String)
      });
    });
  });

  describe('sendError()', () => {
    test('includes statusCode in error response', () => {
      const mockRes = {
        status: (code) => {
          mockRes.statusCode = code;
          return mockRes;
        },
        json: (body) => {
          mockRes.body = body;
          return mockRes;
        }
      };

      apiResponse.sendError(mockRes, 'Database connection failed', 503);

      expect(mockRes.statusCode).toBe(503);
      expect(mockRes.body).toEqual({
        success: false,
        statusCode: 503,
        error: 'service_unavailable',
        message: 'Database connection failed',
        timestamp: expect.any(String)
      });
    });
  });

  describe('Response Format Contract', () => {
    test('all success responses have required fields', () => {
      const mockRes = {
        status: (code) => {
          mockRes.statusCode = code;
          return mockRes;
        },
        json: (body) => {
          mockRes.body = body;
          return mockRes;
        }
      };

      apiResponse.sendSuccess(mockRes, { test: true }, 200);

      const response = mockRes.body;
      expect(response).toHaveProperty('success');
      expect(response).toHaveProperty('statusCode');
      expect(response).toHaveProperty('timestamp');
      expect(response.success).toBe(true);
      expect(typeof response.statusCode).toBe('number');
      expect(typeof response.timestamp).toBe('string');
    });

    test('all error responses have required fields', () => {
      const mockRes = {
        status: (code) => {
          mockRes.statusCode = code;
          return mockRes;
        },
        json: (body) => {
          mockRes.body = body;
          return mockRes;
        }
      };

      apiResponse.sendError(mockRes, 'Test error', 400);

      const response = mockRes.body;
      expect(response).toHaveProperty('success');
      expect(response).toHaveProperty('statusCode');
      expect(response).toHaveProperty('error');
      expect(response).toHaveProperty('message');
      expect(response).toHaveProperty('timestamp');
      expect(response.success).toBe(false);
    });
  });
});
