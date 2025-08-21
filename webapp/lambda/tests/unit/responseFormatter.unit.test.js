// Unit tests for response formatter utility

describe('Response Formatter Utility', () => {
  let responseFormatter;

  beforeEach(() => {
    // Clear module cache to ensure clean imports
    delete require.cache[require.resolve('../../utils/responseFormatter')];
    responseFormatter = require('../../utils/responseFormatter');
  });

  describe('success function', () => {
    test('should format basic success response', () => {
      const data = { message: 'test data' };
      const result = responseFormatter.success(data);

      expect(result.response.success).toBe(true);
      expect(result.response.data).toEqual(data);
      expect(result.response.timestamp).toBeDefined();
      expect(result.statusCode).toBe(200);
    });

    test('should accept custom status code', () => {
      const data = { id: 1 };
      const result = responseFormatter.success(data, 201);

      expect(result.statusCode).toBe(201);
      expect(result.response.success).toBe(true);
      expect(result.response.data).toEqual(data);
    });

    test('should include metadata', () => {
      const data = { items: [] };
      const meta = { count: 0, version: '1.0' };
      const result = responseFormatter.success(data, 200, meta);

      expect(result.response.count).toBe(0);
      expect(result.response.version).toBe('1.0');
      expect(result.response.data).toEqual(data);
    });

    test('should generate valid ISO timestamp', () => {
      const result = responseFormatter.success({});
      const timestamp = new Date(result.response.timestamp);
      
      expect(timestamp.toISOString()).toBe(result.response.timestamp);
      expect(Date.now() - timestamp.getTime()).toBeLessThan(1000); // Within 1 second
    });
  });

  describe('error function', () => {
    test('should format basic error response', () => {
      const message = 'Something went wrong';
      const result = responseFormatter.error(message);

      expect(result.response.success).toBe(false);
      expect(result.response.error).toBe(message);
      expect(result.response.timestamp).toBeDefined();
      expect(result.statusCode).toBe(400);
    });

    test('should accept custom status code', () => {
      const message = 'Not found';
      const result = responseFormatter.error(message, 404);

      expect(result.statusCode).toBe(404);
      expect(result.response.error).toBe(message);
    });

    test('should include error details', () => {
      const message = 'Validation failed';
      const details = { field: 'email', code: 'INVALID_FORMAT' };
      const result = responseFormatter.error(message, 422, details);

      expect(result.response.field).toBe('email');
      expect(result.response.code).toBe('INVALID_FORMAT');
      expect(result.response.error).toBe(message);
      expect(result.statusCode).toBe(422);
    });
  });

  describe('paginated function', () => {
    test('should format paginated response with default pagination', () => {
      const data = [{ id: 1 }, { id: 2 }, { id: 3 }];
      const pagination = { total: 10 };
      const result = responseFormatter.paginated(data, pagination);

      expect(result.response.success).toBe(true);
      expect(result.response.data.items).toEqual(data);
      expect(result.response.data.pagination.page).toBe(1);
      expect(result.response.data.pagination.limit).toBe(50);
      expect(result.response.data.pagination.total).toBe(10);
      expect(result.response.data.pagination.totalPages).toBe(1);
    });

    test('should calculate total pages correctly', () => {
      const data = [];
      const pagination = { page: 2, limit: 25, total: 100 };
      const result = responseFormatter.paginated(data, pagination);

      expect(result.response.data.pagination.page).toBe(2);
      expect(result.response.data.pagination.limit).toBe(25);
      expect(result.response.data.pagination.total).toBe(100);
      expect(result.response.data.pagination.totalPages).toBe(4);
    });

    test('should handle hasNext and hasPrev flags', () => {
      const data = [];
      const pagination = { hasNext: true, hasPrev: false };
      const result = responseFormatter.paginated(data, pagination);

      expect(result.response.data.pagination.hasNext).toBe(true);
      expect(result.response.data.pagination.hasPrev).toBe(false);
    });

    test('should include metadata', () => {
      const data = [];
      const pagination = {};
      const meta = { source: 'database', cached: false };
      const result = responseFormatter.paginated(data, pagination, meta);

      expect(result.response.data.source).toBe('database');
      expect(result.response.data.cached).toBe(false);
    });
  });

  describe('validationError function', () => {
    test('should format validation error with array of errors', () => {
      const errors = [
        { field: 'email', message: 'Invalid email format' },
        { field: 'password', message: 'Password too short' }
      ];
      const result = responseFormatter.validationError(errors);

      expect(result.response.success).toBe(false);
      expect(result.response.error).toBe('Validation failed');
      expect(result.response.errors).toEqual(errors);
      expect(result.response.type).toBe('validation_error');
      expect(result.statusCode).toBe(422);
    });

    test('should format validation error with single error object', () => {
      const error = { field: 'username', message: 'Username is required' };
      const result = responseFormatter.validationError(error);

      expect(result.response.errors).toEqual([error]);
      expect(result.response.type).toBe('validation_error');
    });
  });

  describe('notFound function', () => {
    test('should format not found error with default resource', () => {
      const result = responseFormatter.notFound();

      expect(result.response.success).toBe(false);
      expect(result.response.error).toBe('Resource not found');
      expect(result.response.type).toBe('not_found_error');
      expect(result.statusCode).toBe(404);
    });

    test('should format not found error with custom resource', () => {
      const result = responseFormatter.notFound('User');

      expect(result.response.error).toBe('User not found');
      expect(result.response.type).toBe('not_found_error');
    });
  });

  describe('unauthorized function', () => {
    test('should format unauthorized error with default message', () => {
      const result = responseFormatter.unauthorized();

      expect(result.response.success).toBe(false);
      expect(result.response.error).toBe('Unauthorized access');
      expect(result.response.type).toBe('unauthorized_error');
      expect(result.statusCode).toBe(401);
    });

    test('should format unauthorized error with custom message', () => {
      const message = 'Token expired';
      const result = responseFormatter.unauthorized(message);

      expect(result.response.error).toBe(message);
      expect(result.response.type).toBe('unauthorized_error');
    });
  });

  describe('forbidden function', () => {
    test('should format forbidden error with default message', () => {
      const result = responseFormatter.forbidden();

      expect(result.response.success).toBe(false);
      expect(result.response.error).toBe('Access forbidden');
      expect(result.response.type).toBe('forbidden_error');
      expect(result.statusCode).toBe(403);
    });

    test('should format forbidden error with custom message', () => {
      const message = 'Insufficient permissions';
      const result = responseFormatter.forbidden(message);

      expect(result.response.error).toBe(message);
    });
  });

  describe('serverError function', () => {
    test('should format server error with default message', () => {
      const result = responseFormatter.serverError();

      expect(result.response.success).toBe(false);
      expect(result.response.error).toBe('Internal server error');
      expect(result.response.type).toBe('server_error');
      expect(result.statusCode).toBe(500);
    });

    test('should format server error with custom message and details', () => {
      const message = 'Database connection failed';
      const details = { code: 'DB_ERROR', retryable: true };
      const result = responseFormatter.serverError(message, details);

      expect(result.response.error).toBe(message);
      expect(result.response.code).toBe('DB_ERROR');
      expect(result.response.retryable).toBe(true);
      expect(result.response.type).toBe('server_error');
    });
  });

  describe('module exports', () => {
    test('should export all required functions', () => {
      expect(typeof responseFormatter.success).toBe('function');
      expect(typeof responseFormatter.error).toBe('function');
      expect(typeof responseFormatter.paginated).toBe('function');
      expect(typeof responseFormatter.validationError).toBe('function');
      expect(typeof responseFormatter.notFound).toBe('function');
      expect(typeof responseFormatter.unauthorized).toBe('function');
      expect(typeof responseFormatter.forbidden).toBe('function');
      expect(typeof responseFormatter.serverError).toBe('function');
    });
  });

  describe('edge cases and error conditions', () => {
    test('should handle null data in success response', () => {
      const result = responseFormatter.success(null);
      
      expect(result.response.data).toBe(null);
      expect(result.response.success).toBe(true);
    });

    test('should handle undefined data in success response', () => {
      const result = responseFormatter.success(undefined);
      
      expect(result.response.data).toBe(undefined);
      expect(result.response.success).toBe(true);
    });

    test('should handle empty string error message', () => {
      const result = responseFormatter.error('');
      
      expect(result.response.error).toBe('');
      expect(result.response.success).toBe(false);
    });

    test('should handle large pagination numbers', () => {
      const data = [];
      const pagination = { page: 1000, limit: 100, total: 100000 };
      const result = responseFormatter.paginated(data, pagination);

      expect(result.response.data.pagination.totalPages).toBe(1000);
      expect(result.response.data.pagination.page).toBe(1000);
    });

    test('should handle empty pagination object', () => {
      const data = [1, 2, 3];
      const result = responseFormatter.paginated(data, {});

      expect(result.response.data.pagination.total).toBe(3);
      expect(result.response.data.pagination.totalPages).toBe(1);
    });
  });
});