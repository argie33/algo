import { describe, it, expect } from 'vitest';

/**
 * Unit tests for Trading Signals pagination logic
 * Tests the mathematical correctness of pagination calculations
 */

describe('TradingSignals Pagination Logic', () => {
  /**
   * Test data: 100 trading signals
   */
  const mockSignals = Array.from({ length: 100 }, (_, i) => ({
    symbol: `SYM${String(i + 1).padStart(3, '0')}`,
    signal: i % 2 === 0 ? 'Buy' : 'Sell',
    signal_type: i % 2 === 0 ? 'Buy' : 'Sell',
  }));

  describe('Page 1: First 25 signals', () => {
    it('should calculate correct start and end indices for page 1', () => {
      const page = 0;
      const rowsPerPage = 25;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      expect(startIndex).toBe(0);
      expect(endIndex).toBe(25);
    });

    it('should slice correctly for page 1 (signals 1-25)', () => {
      const page = 0;
      const rowsPerPage = 25;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const paginatedData = mockSignals.slice(startIndex, endIndex);

      expect(paginatedData.length).toBe(25);
      expect(paginatedData[0].symbol).toBe('SYM001');
      expect(paginatedData[24].symbol).toBe('SYM025');
    });

    it('should display "Showing 1 to 25 of 100 signals" for page 1', () => {
      const page = 0;
      const rowsPerPage = 25;
      const totalSignals = mockSignals.length;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const displayStart = startIndex + 1;
      const displayEnd = Math.min(endIndex, totalSignals);
      const infoText = `Showing ${displayStart} to ${displayEnd} of ${totalSignals} signals`;

      expect(infoText).toBe('Showing 1 to 25 of 100 signals');
    });
  });

  describe('Page 2: Signals 26-50 (Critical Test)', () => {
    it('should calculate correct start and end indices for page 2', () => {
      const page = 1;
      const rowsPerPage = 25;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      expect(startIndex).toBe(25);
      expect(endIndex).toBe(50);
    });

    it('should slice correctly for page 2 (signals 26-50)', () => {
      const page = 1;
      const rowsPerPage = 25;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const paginatedData = mockSignals.slice(startIndex, endIndex);

      expect(paginatedData.length).toBe(25);
      expect(paginatedData[0].symbol).toBe('SYM026');
      expect(paginatedData[24].symbol).toBe('SYM050');
    });

    it('should display "Showing 26 to 50 of 100 signals" for page 2', () => {
      const page = 1;
      const rowsPerPage = 25;
      const totalSignals = mockSignals.length;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const displayStart = startIndex + 1;
      const displayEnd = Math.min(endIndex, totalSignals);
      const infoText = `Showing ${displayStart} to ${displayEnd} of ${totalSignals} signals`;

      expect(infoText).toBe('Showing 26 to 50 of 100 signals');
    });

    it('should verify signals are different between page 1 and page 2', () => {
      const page1Data = mockSignals.slice(0, 25);
      const page2Data = mockSignals.slice(25, 50);

      const page1Symbols = page1Data.map((s) => s.symbol);
      const page2Symbols = page2Data.map((s) => s.symbol);

      // No overlap between pages
      const overlap = page1Symbols.filter((sym) => page2Symbols.includes(sym));
      expect(overlap.length).toBe(0);
    });
  });

  describe('Page 3: Signals 51-75', () => {
    it('should calculate correct indices for page 3', () => {
      const page = 2;
      const rowsPerPage = 25;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      expect(startIndex).toBe(50);
      expect(endIndex).toBe(75);
    });

    it('should display "Showing 51 to 75 of 100 signals" for page 3', () => {
      const page = 2;
      const rowsPerPage = 25;
      const totalSignals = mockSignals.length;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const displayStart = startIndex + 1;
      const displayEnd = Math.min(endIndex, totalSignals);
      const infoText = `Showing ${displayStart} to ${displayEnd} of ${totalSignals} signals`;

      expect(infoText).toBe('Showing 51 to 75 of 100 signals');
    });
  });

  describe('Page 4: Signals 76-100', () => {
    it('should calculate correct indices for page 4 (last page)', () => {
      const page = 3;
      const rowsPerPage = 25;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      expect(startIndex).toBe(75);
      expect(endIndex).toBe(100);
    });

    it('should display "Showing 76 to 100 of 100 signals" for page 4', () => {
      const page = 3;
      const rowsPerPage = 25;
      const totalSignals = mockSignals.length;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const displayStart = startIndex + 1;
      const displayEnd = Math.min(endIndex, totalSignals);
      const infoText = `Showing ${displayStart} to ${displayEnd} of ${totalSignals} signals`;

      expect(infoText).toBe('Showing 76 to 100 of 100 signals');
    });
  });

  describe('Rows per page variation', () => {
    it('should handle 50 rows per page correctly (page 1)', () => {
      const page = 0;
      const rowsPerPage = 50;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const paginatedData = mockSignals.slice(startIndex, endIndex);

      expect(paginatedData.length).toBe(50);
      expect(paginatedData[0].symbol).toBe('SYM001');
      expect(paginatedData[49].symbol).toBe('SYM050');
    });

    it('should handle 50 rows per page correctly (page 2)', () => {
      const page = 1;
      const rowsPerPage = 50;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const paginatedData = mockSignals.slice(startIndex, endIndex);

      expect(paginatedData.length).toBe(50);
      expect(paginatedData[0].symbol).toBe('SYM051');
      expect(paginatedData[49].symbol).toBe('SYM100');
    });

    it('should handle 100 rows per page (all on page 1)', () => {
      const page = 0;
      const rowsPerPage = 100;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const paginatedData = mockSignals.slice(startIndex, endIndex);

      expect(paginatedData.length).toBe(100);
      expect(paginatedData[0].symbol).toBe('SYM001');
      expect(paginatedData[99].symbol).toBe('SYM100');
    });
  });

  describe('Edge cases', () => {
    it('should handle empty data correctly', () => {
      const emptyData = [];
      const page = 0;
      const rowsPerPage = 25;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const paginatedData = emptyData.slice(startIndex, endIndex);

      expect(paginatedData.length).toBe(0);
    });

    it('should handle data smaller than page size', () => {
      const smallData = Array.from({ length: 5 }, (_, i) => ({ symbol: `SYM${i + 1}` }));
      const page = 0;
      const rowsPerPage = 25;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const paginatedData = smallData.slice(startIndex, endIndex);

      expect(paginatedData.length).toBe(5);
    });

    it('should not render invalid pages (page beyond data)', () => {
      const page = 10; // Way beyond available pages
      const rowsPerPage = 25;
      const startIndex = page * rowsPerPage;
      const endIndex = startIndex + rowsPerPage;

      const paginatedData = mockSignals.slice(startIndex, endIndex);

      expect(paginatedData.length).toBe(0);
    });
  });
});
