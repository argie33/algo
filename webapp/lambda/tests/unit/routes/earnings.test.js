/**
 * Earnings Routes Unit Tests
 * Tests earnings route delegation to calendar functionality
 */

const express = require('express');
const request = require('supertest');

// Mock the calendar router
jest.mock('../../../routes/calendar', () => ({
  handle: jest.fn()
}));

describe('Earnings Routes Unit Tests', () => {
  let app;
  let earningsRouter;
  let mockCalendarHandle;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Set up mocks
    const calendarRouter = require('../../../routes/calendar');
    mockCalendarHandle = calendarRouter.handle;
    
    // Create test app
    app = express();
    app.use(express.json());
    
    // Load the route module
    earningsRouter = require('../../../routes/earnings');
    app.use('/earnings', earningsRouter);
  });

  describe('GET /earnings', () => {
    test('should delegate to calendar earnings endpoint', async () => {
      // Mock successful calendar response
      mockCalendarHandle.mockImplementation((req, res, next) => {
        res.json({
          success: true,
          earnings: [
            { symbol: 'AAPL', report_date: '2024-01-25', status: 'upcoming' }
          ],
          summary: { total: 1, upcoming: 1, reported: 0 }
        });
      });

      const response = await request(app)
        .get('/earnings');

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        earnings: expect.any(Array),
        summary: expect.any(Object)
      });
      expect(mockCalendarHandle).toHaveBeenCalledTimes(1);
    });

    test('should handle calendar delegation errors', async () => {
      // Mock calendar error
      mockCalendarHandle.mockImplementation((req, res, next) => {
        const error = new Error('Calendar service unavailable');
        next(error);
      });

      const response = await request(app)
        .get('/earnings');

      expect(response.status).toBe(500);
      expect(response.body).toMatchObject({
        success: false,
        error: 'Failed to fetch earnings data'
      });
    });
  });

  describe('GET /earnings/:symbol', () => {
    test('should delegate to calendar earnings with symbol filter', async () => {
      // Mock successful calendar response with symbol filter
      mockCalendarHandle.mockImplementation((req, res, next) => {
        expect(req.query.symbol).toBe('AAPL');
        res.json({
          success: true,
          earnings: [
            { symbol: 'AAPL', report_date: '2024-01-25', quarter: 1, year: 2024 }
          ],
          symbol: 'AAPL'
        });
      });

      const response = await request(app)
        .get('/earnings/AAPL');

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        earnings: expect.any(Array),
        symbol: 'AAPL'
      });
      expect(mockCalendarHandle).toHaveBeenCalledTimes(1);
    });

    test('should handle symbol-specific delegation errors', async () => {
      // Mock calendar error for symbol request
      mockCalendarHandle.mockImplementation((req, res, next) => {
        const error = new Error('Symbol not found');
        next(error);
      });

      const response = await request(app)
        .get('/earnings/INVALID');

      expect(response.status).toBe(500);
      expect(response.body).toMatchObject({
        success: false,
        error: 'Failed to fetch earnings details',
        symbol: 'INVALID'
      });
    });
  });

  describe('Error handling', () => {
    test('should handle unexpected errors gracefully', async () => {
      // Mock calendar router throwing an error
      mockCalendarHandle.mockImplementation(() => {
        throw new Error('Unexpected error');
      });

      const response = await request(app)
        .get('/earnings');

      expect(response.status).toBe(500);
      expect(response.body).toMatchObject({
        success: false,
        error: 'Failed to fetch earnings data',
        details: 'Unexpected error'
      });
    });
  });
});