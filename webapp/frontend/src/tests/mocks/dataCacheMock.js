/**
 * DataCache Mock for Tests
 * This mock provides cached data functionality for test environments
 */
import { vi } from "vitest";

const mockDataCache = {
  get: vi.fn().mockResolvedValue(null),
  set: vi.fn().mockResolvedValue(true),
  delete: vi.fn().mockResolvedValue(true),
  clear: vi.fn().mockResolvedValue(true),
  has: vi.fn().mockResolvedValue(false),
  size: vi.fn().mockResolvedValue(0),
  keys: vi.fn().mockResolvedValue([]),
  values: vi.fn().mockResolvedValue([]),
  entries: vi.fn().mockResolvedValue([]),

  // Market data cache methods
  getMarketData: vi.fn().mockResolvedValue({
    success: false,
    data: null,
    cached: false
  }),

  setMarketData: vi.fn().mockResolvedValue(true),

  // Cache management
  cleanup: vi.fn().mockResolvedValue(true),
  stats: vi.fn().mockResolvedValue({
    hits: 0,
    misses: 0,
    size: 0
  })
};

export default mockDataCache;