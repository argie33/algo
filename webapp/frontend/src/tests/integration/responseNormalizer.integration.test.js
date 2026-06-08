import { describe, test, expect } from 'vitest';
import { extractData, extractPaginatedData } from '../../utils/responseNormalizer';

describe('responseNormalizer Integration Tests', () => {
  describe('Real Backend Response Formats', () => {
    test('handles single object response (status endpoint format)', () => {
      // This matches the actual /api/algo/status response
      const response = {
        data: {
          statusCode: 200,
          data: {
            run_id: 'RUN-2026-06-08-014331',
            current_phase: 'phase_1_planning_mode',
            status: 'success',
            portfolio: {
              total_value: 74180.93,
              daily_return_pct: 0.0,
              unrealized_pnl_pct: 1.53,
              open_positions: 9,
            },
          },
          headers: {},
        },
      };

      const result = extractData(response);

      expect(result.statusCode).toBe(200);
      expect(result.success).toBe(true);
      expect(result.data).toBeDefined();
      expect(result.data.run_id).toBe('RUN-2026-06-08-014331');
      expect(result.data.portfolio.total_value).toBe(74180.93);
    });

    test('handles paginated response (trades endpoint format)', () => {
      // This matches the actual /api/algo/trades response
      const response = {
        data: {
          success: true,
          statusCode: 200,
          items: [
            {
              trade_id: 'TRD-F9A5DD4A89',
              symbol: 'ZGN',
              entry_price: 14.46,
              status: 'rejected',
            },
            {
              trade_id: 'TRD-17465A03F2',
              symbol: 'VATE',
              entry_price: 25.3,
              status: 'open',
            },
          ],
          pagination: {
            total: 150,
            limit: 50,
            offset: 0,
            page: 1,
            totalPages: 3,
            hasNext: true,
            hasPrev: false,
          },
        },
      };

      const result = extractData(response);

      expect(result.statusCode).toBe(200);
      expect(result.success).toBe(true);
      expect(Array.isArray(result.items)).toBe(true);
      expect(result.items.length).toBe(2);
      expect(result.items[0].symbol).toBe('ZGN');
      expect(result.pagination.total).toBe(150);
      expect(result.pagination.hasNext).toBe(true);
    });

    test('handles error response (4xx format)', () => {
      // This matches error response format from backend
      const response = {
        data: {
          success: false,
          statusCode: 400,
          error: 'bad_request',
          message: 'Invalid parameters',
          timestamp: '2026-06-08T20:08:52Z',
        },
        status: 400,
      };

      expect(() => extractData(response)).toThrow();
    });

    test('handles error response (5xx format)', () => {
      const response = {
        data: {
          success: false,
          statusCode: 500,
          error: 'internal_error',
          message: 'Database connection error',
          timestamp: '2026-06-08T20:08:52Z',
        },
        status: 500,
      };

      expect(() => extractData(response)).toThrow('Database connection error');
    });

    test('extracts paginated data correctly', () => {
      const response = {
        data: {
          success: true,
          statusCode: 200,
          items: [
            { id: 1, name: 'Item 1' },
            { id: 2, name: 'Item 2' },
          ],
          pagination: {
            total: 100,
            limit: 50,
            offset: 0,
            page: 1,
          },
        },
      };

      const result = extractPaginatedData(response);

      expect(result.items).toHaveLength(2);
      expect(result.pagination.total).toBe(100);
      expect(result.pagination.hasNext).toBe(true);
    });
  });

  describe('Edge Cases with Real-World Data', () => {
    test('does not spread data fields that could collide', () => {
      // This test verifies that we don't accidentally spread data.data
      // which could cause field collisions with statusCode or success
      const response = {
        data: {
          statusCode: 200,
          data: {
            statusCode: 999, // Field that would collide if spread
            success: false,  // Field that would collide if spread
            actualData: 'preserved',
          },
        },
      };

      const result = extractData(response);

      // The response-level statusCode should win, not the data-level one
      expect(result.statusCode).toBe(200);
      expect(result.success).toBe(true);
      // The actual data object should be accessible
      expect(result.data.statusCode).toBe(999); // Preserved in the data object
      expect(result.data.success).toBe(false); // Preserved in the data object
      expect(result.data.actualData).toBe('preserved');
    });

    test('handles empty items array', () => {
      const response = {
        data: {
          success: true,
          statusCode: 200,
          items: [],
          pagination: {
            total: 0,
            limit: 50,
            offset: 0,
            page: 1,
          },
        },
      };

      const result = extractData(response);

      expect(result.items).toEqual([]);
      expect(result.pagination.total).toBe(0);
      expect(result.pagination.hasNext).toBe(false);
    });
  });
});
