// Jest globals are automatically available

describe('Error Handler Middleware', () => {
  let errorHandler;
  let req, res, next;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Clear module cache
    delete require.cache[require.resolve('../../middleware/errorHandler')];
    
    // Set up mock request/response/next
    req = {
      method: 'GET',
      path: '/api/test',
      headers: {},
      ip: '127.0.0.1'
    };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
      headersSent: false
    };
    next = jest.fn();

    // Import error handler
    errorHandler = require('../../middleware/errorHandler');
  });

  afterEach(() => {
    delete process.env.NODE_ENV;
  });

  describe('error handling', () => {
    test('should handle generic errors with 500 status', () => {
      const error = new Error('Something went wrong');
      
      errorHandler(error, req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(500);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Internal Server Error',
          message: 'Something went wrong',
          timestamp: expect.any(String)
        })
      );
      expect(next).not.toHaveBeenCalled();
    });

    test('should handle validation errors with 400 status', () => {
      const error = new Error('Invalid input');
      error.name = 'ValidationError';
      
      errorHandler(error, req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(400);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Validation Error',
          message: 'Invalid input'
        })
      );
    });

    test('should handle JWT errors with 401 status', () => {
      const error = new Error('Invalid token');
      error.name = 'JsonWebTokenError';
      
      errorHandler(error, req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Authentication Error',
          message: 'Invalid token'
        })
      );
    });

    test('should handle token expired errors with 401 status', () => {
      const error = new Error('Token expired');
      error.name = 'TokenExpiredError';
      
      errorHandler(error, req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Authentication Error',
          message: 'Token expired'
        })
      );
    });

    test('should handle database errors with 503 status', () => {
      const error = new Error('Connection failed');
      error.code = 'ECONNREFUSED';
      
      errorHandler(error, req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(503);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Service Unavailable',
          message: 'Database connection failed'
        })
      );
    });

    test('should handle permission denied errors with 403 status', () => {
      const error = new Error('Access denied');
      error.name = 'ForbiddenError';
      
      errorHandler(error, req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Forbidden',
          message: 'Access denied'
        })
      );
    });

    test('should handle rate limit errors with 429 status', () => {
      const error = new Error('Too many requests');
      error.name = 'RateLimitError';
      
      errorHandler(error, req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(429);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Too Many Requests',
          message: 'Too many requests'
        })
      );
    });

    test('should include stack trace in development environment', () => {
      process.env.NODE_ENV = 'development';
      const error = new Error('Development error');
      error.stack = 'Error stack trace...';
      
      errorHandler(error, req, res, next);
      
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          stack: 'Error stack trace...'
        })
      );
    });

    test('should not include stack trace in production environment', () => {
      process.env.NODE_ENV = 'production';
      const error = new Error('Production error');
      error.stack = 'Error stack trace...';
      
      errorHandler(error, req, res, next);
      
      expect(res.json).toHaveBeenCalledWith(
        expect.not.objectContaining({
          stack: expect.any(String)
        })
      );
    });

    test('should handle errors with custom status codes', () => {
      const error = new Error('Custom error');
      error.statusCode = 418;
      
      errorHandler(error, req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(418);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Custom error',
          message: 'Custom error'
        })
      );
    });

    test('should not send response if headers already sent', () => {
      res.headersSent = true;
      const error = new Error('Error after headers sent');
      
      errorHandler(error, req, res, next);
      
      expect(res.status).not.toHaveBeenCalled();
      expect(res.json).not.toHaveBeenCalled();
      expect(next).toHaveBeenCalledWith(error);
    });

    test('should include request context in error response', () => {
      const error = new Error('Context error');
      req.headers['x-request-id'] = 'req-123';
      req.user = { sub: 'user-123', username: 'testuser' };
      
      errorHandler(error, req, res, next);
      
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          requestId: 'req-123',
          path: '/api/test',
          method: 'GET',
          timestamp: expect.any(String)
        })
      );
    });

    test('should handle TypeError with 400 status', () => {
      const error = new TypeError('Invalid type');
      
      errorHandler(error, req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(400);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Bad Request',
          message: 'Invalid type'
        })
      );
    });

    test('should handle SyntaxError with 400 status', () => {
      const error = new SyntaxError('Invalid JSON');
      
      errorHandler(error, req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(400);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Bad Request',
          message: 'Invalid JSON'
        })
      );
    });

    test('should log error details for monitoring', () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
      const error = new Error('Error to be logged');
      error.stack = 'Error stack trace...';
      
      errorHandler(error, req, res, next);
      
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Error handling request'),
        expect.objectContaining({
          error: expect.objectContaining({
            message: 'Error to be logged',
            name: 'Error'
          }),
          request: expect.objectContaining({
            method: 'GET',
            path: '/api/test'
          })
        })
      );
      
      consoleSpy.mockRestore();
    });
  });
});