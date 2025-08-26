import { vi, expect, test } from 'vitest';

// Import the mock
vi.mock('../services/api', async () => {
  const { createApiServiceMock } = await import('./mocks/api-service-mock');
  return {
    default: createApiServiceMock(),
    ...createApiServiceMock()
  };
});

import api from '../services/api';

test('Debug API mock functions', async () => {
  console.log('API mock object:', api);
  console.log('getPortfolioPerformance:', typeof api.getPortfolioPerformance);
  console.log('getPortfolioAnalytics:', typeof api.getPortfolioAnalytics);
  
  // Test the functions directly
  try {
    const perfResult = await api.getPortfolioPerformance('1Y');
    console.log('Performance result:', perfResult);
  } catch (e) {
    console.error('Performance error:', e);
  }
  
  try {
    const analyticsResult = await api.getPortfolioAnalytics('1Y');
    console.log('Analytics result:', analyticsResult);
  } catch (e) {
    console.error('Analytics error:', e);
  }
  
  expect(true).toBe(true);
});