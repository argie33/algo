/**
 * Response Formatter Middleware Tests
 */

// Mock the responseFormatter utility before requiring anything
const mockResponseFormatter = {
  success: jest.fn(),
  error: jest.fn(),
  paginated: jest.fn(),
  validationError: jest.fn(),
  notFound: jest.fn(),
  unauthorized: jest.fn(),
  forbidden: jest.fn(),
  serverError: jest.fn()
};

jest.mock('../../utils/responseFormatter', () => mockResponseFormatter);

const responseFormatterMiddleware = require('../../middleware/responseFormatter');

describe('Response Formatter Middleware', () => {
  let req, res, next;

  beforeEach(() => {
    req = {};
    res = {
      set: jest.fn(),
      status: jest.fn().mockReturnThis(),
      json: jest.fn()
    };
    next = jest.fn();

    // Reset all mocks
    jest.clearAllMocks();
    
    // Setup default mock returns
    mockResponseFormatter.success.mockReturnValue({
      statusCode: 200,
      response: { success: true, data: null }
    });
    mockResponseFormatter.error.mockReturnValue({
      statusCode: 400,
      response: { success: false, error: 'Test error' }
    });
    mockResponseFormatter.paginated.mockReturnValue({
      statusCode: 200,
      response: { success: true, data: [], pagination: {} }
    });
    mockResponseFormatter.validationError.mockReturnValue({
      statusCode: 422,
      response: { success: false, error: 'Validation failed' }
    });
    mockResponseFormatter.notFound.mockReturnValue({
      statusCode: 404,
      response: { success: false, error: 'Resource not found' }
    });
    mockResponseFormatter.unauthorized.mockReturnValue({
      statusCode: 401,
      response: { success: false, error: 'Unauthorized' }
    });
    mockResponseFormatter.forbidden.mockReturnValue({
      statusCode: 403,
      response: { success: false, error: 'Forbidden' }
    });
    mockResponseFormatter.serverError.mockReturnValue({
      statusCode: 500,
      response: { success: false, error: 'Server error' }
    });
  });

  describe('Middleware Setup', () => {
    it('should set API version header', () => {
      responseFormatterMiddleware(req, res, next);
      
      expect(res.set).toHaveBeenCalledWith('Api-Version', 'v1.0');
    });

    it('should call next() to continue middleware chain', () => {
      responseFormatterMiddleware(req, res, next);
      
      expect(next).toHaveBeenCalled();
    });

    it('should add all response methods to res object', () => {
      responseFormatterMiddleware(req, res, next);
      
      expect(typeof res.success).toBe('function');
      expect(typeof res.error).toBe('function');
      expect(typeof res.paginated).toBe('function');
      expect(typeof res.validationError).toBe('function');
      expect(typeof res.notFound).toBe('function');
      expect(typeof res.unauthorized).toBe('function');
      expect(typeof res.forbidden).toBe('function');
      expect(typeof res.serverError).toBe('function');
    });
  });

  describe('res.success()', () => {
    beforeEach(() => {
      responseFormatterMiddleware(req, res, next);
    });

    it('should call responseFormatter.success with correct parameters', () => {
      const data = { test: 'data' };
      const statusCode = 201;
      const meta = { count: 1 };

      res.success(data, statusCode, meta);

      expect(mockResponseFormatter.success).toHaveBeenCalledWith(data, statusCode, meta);
    });

    it('should use default statusCode and meta if not provided', () => {
      const data = { test: 'data' };

      res.success(data);

      expect(mockResponseFormatter.success).toHaveBeenCalledWith(data, 200, {});
    });

    it('should set status and return JSON response', () => {
      const data = { test: 'data' };
      
      res.success(data);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(res.json).toHaveBeenCalledWith({ success: true, data: null });
    });
  });

  describe('res.error()', () => {
    beforeEach(() => {
      responseFormatterMiddleware(req, res, next);
    });

    it('should call responseFormatter.error with correct parameters', () => {
      const message = 'Test error';
      const statusCode = 500;
      const details = { field: 'test' };

      res.error(message, statusCode, details);

      expect(mockResponseFormatter.error).toHaveBeenCalledWith(message, statusCode, details);
    });

    it('should use default statusCode and details if not provided', () => {
      const message = 'Test error';

      res.error(message);

      expect(mockResponseFormatter.error).toHaveBeenCalledWith(message, 400, {});
    });

    it('should set status and return JSON response', () => {
      const message = 'Test error';
      
      res.error(message);

      expect(res.status).toHaveBeenCalledWith(400);
      expect(res.json).toHaveBeenCalledWith({ success: false, error: 'Test error' });
    });
  });

  describe('res.paginated()', () => {
    beforeEach(() => {
      responseFormatterMiddleware(req, res, next);
    });

    it('should call responseFormatter.paginated with correct parameters', () => {
      const data = [1, 2, 3];
      const pagination = { page: 1, limit: 10, total: 100 };
      const meta = { query: 'test' };

      res.paginated(data, pagination, meta);

      expect(mockResponseFormatter.paginated).toHaveBeenCalledWith(data, pagination, meta);
    });

    it('should use default meta if not provided', () => {
      const data = [1, 2, 3];
      const pagination = { page: 1, limit: 10, total: 100 };

      res.paginated(data, pagination);

      expect(mockResponseFormatter.paginated).toHaveBeenCalledWith(data, pagination, {});
    });

    it('should set status and return JSON response', () => {
      const data = [1, 2, 3];
      const pagination = { page: 1, limit: 10, total: 100 };
      
      res.paginated(data, pagination);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(res.json).toHaveBeenCalledWith({ success: true, data: [], pagination: {} });
    });
  });

  describe('res.validationError()', () => {
    beforeEach(() => {
      responseFormatterMiddleware(req, res, next);
    });

    it('should call responseFormatter.validationError with correct parameters', () => {
      const errors = [{ field: 'name', message: 'Required' }];

      res.validationError(errors);

      expect(mockResponseFormatter.validationError).toHaveBeenCalledWith(errors);
    });

    it('should set status and return JSON response', () => {
      const errors = [{ field: 'name', message: 'Required' }];
      
      res.validationError(errors);

      expect(res.status).toHaveBeenCalledWith(422);
      expect(res.json).toHaveBeenCalledWith({ success: false, error: 'Validation failed' });
    });
  });

  describe('res.notFound()', () => {
    beforeEach(() => {
      responseFormatterMiddleware(req, res, next);
    });

    it('should call responseFormatter.notFound with custom resource', () => {
      const resource = 'User';

      res.notFound(resource);

      expect(mockResponseFormatter.notFound).toHaveBeenCalledWith(resource);
    });

    it('should use default resource if not provided', () => {
      res.notFound();

      expect(mockResponseFormatter.notFound).toHaveBeenCalledWith('Resource');
    });

    it('should set status and return JSON response', () => {
      res.notFound();

      expect(res.status).toHaveBeenCalledWith(404);
      expect(res.json).toHaveBeenCalledWith({ success: false, error: 'Resource not found' });
    });
  });

  describe('res.unauthorized()', () => {
    beforeEach(() => {
      responseFormatterMiddleware(req, res, next);
    });

    it('should call responseFormatter.unauthorized with custom message', () => {
      const message = 'Invalid token';

      res.unauthorized(message);

      expect(mockResponseFormatter.unauthorized).toHaveBeenCalledWith(message);
    });

    it('should use default message if not provided', () => {
      res.unauthorized();

      expect(mockResponseFormatter.unauthorized).toHaveBeenCalledWith('Unauthorized access');
    });

    it('should set status and return JSON response', () => {
      res.unauthorized();

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ success: false, error: 'Unauthorized' });
    });
  });

  describe('res.forbidden()', () => {
    beforeEach(() => {
      responseFormatterMiddleware(req, res, next);
    });

    it('should call responseFormatter.forbidden with custom message', () => {
      const message = 'Insufficient permissions';

      res.forbidden(message);

      expect(mockResponseFormatter.forbidden).toHaveBeenCalledWith(message);
    });

    it('should use default message if not provided', () => {
      res.forbidden();

      expect(mockResponseFormatter.forbidden).toHaveBeenCalledWith('Access forbidden');
    });

    it('should set status and return JSON response', () => {
      res.forbidden();

      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({ success: false, error: 'Forbidden' });
    });
  });

  describe('res.serverError()', () => {
    beforeEach(() => {
      responseFormatterMiddleware(req, res, next);
    });

    it('should call responseFormatter.serverError with correct parameters', () => {
      const message = 'Database error';
      const details = { query: 'SELECT * FROM users' };

      res.serverError(message, details);

      expect(mockResponseFormatter.serverError).toHaveBeenCalledWith(message, details);
    });

    it('should use default message and details if not provided', () => {
      res.serverError();

      expect(mockResponseFormatter.serverError).toHaveBeenCalledWith('Internal server error', {});
    });

    it('should set status and return JSON response', () => {
      res.serverError();

      expect(res.status).toHaveBeenCalledWith(500);
      expect(res.json).toHaveBeenCalledWith({ success: false, error: 'Server error' });
    });
  });

  describe('Integration Tests', () => {
    it('should handle multiple method calls on same response object', () => {
      responseFormatterMiddleware(req, res, next);

      // This simulates incorrect usage but should still work
      expect(() => {
        res.success({ data: 'test' });
        res.error('Should not call this after success');
      }).not.toThrow();
    });

    it('should maintain correct context for all methods', () => {
      responseFormatterMiddleware(req, res, next);

      const methods = [
        () => res.success({}),
        () => res.error('test'),
        () => res.paginated([], {}),
        () => res.validationError([]),
        () => res.notFound(),
        () => res.unauthorized(),
        () => res.forbidden(),
        () => res.serverError()
      ];

      methods.forEach(method => {
        expect(() => method()).not.toThrow();
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle formatter utility failures gracefully', () => {
      mockResponseFormatter.success.mockImplementation(() => {
        throw new Error('Formatter error');
      });

      responseFormatterMiddleware(req, res, next);

      expect(() => res.success({})).toThrow('Formatter error');
    });

    it('should handle missing response methods gracefully', () => {
      const incompleteRes = {
        set: jest.fn()
        // Missing status and json methods
      };

      responseFormatterMiddleware(req, incompleteRes, next);

      expect(() => incompleteRes.success({})).toThrow();
    });
  });
});