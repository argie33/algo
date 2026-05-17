import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '1m', target: 5 },     // Ramp to 5 VUs
    { duration: '3m', target: 25 },    // Ramp to 25 VUs
    { duration: '2m', target: 50 },    // Ramp to 50 VUs
    { duration: '2m', target: 25 },    // Ramp down to 25 VUs
    { duration: '1m', target: 0 },     // Ramp down to 0 VUs
  ],
  thresholds: {
    http_req_duration: ['p(95)<1000', 'p(99)<3000'],
    http_req_failed: ['rate<0.01'],
    'http_req_duration{staticAsset:yes}': ['p(99)<1000'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3001';

// Test endpoints with realistic workload distribution
const endpoints = [
  // Read-heavy endpoints that benefit from caching
  { name: 'signals', path: '/api/signals/search?limit=50&days=365', weight: 25 },
  { name: 'stocks', path: '/api/stocks?limit=50', weight: 20 },
  { name: 'scores', path: '/api/scores?limit=50', weight: 15 },
  { name: 'sentiment', path: '/api/sentiment', weight: 10 },

  // Real-time endpoints (no caching)
  { name: 'portfolio', path: '/api/portfolio', weight: 15 },
  { name: 'performance', path: '/api/performance', weight: 10 },

  // Infrastructure
  { name: 'health', path: '/api/health/detailed', weight: 5 },
];

// Weighted random selection
function selectEndpoint() {
  const totalWeight = endpoints.reduce((sum, e) => sum + e.weight, 0);
  let random = Math.random() * totalWeight;

  for (const endpoint of endpoints) {
    random -= endpoint.weight;
    if (random <= 0) {
      return endpoint;
    }
  }

  return endpoints[0];
}

export default function () {
  const endpoint = selectEndpoint();
  const url = `${BASE_URL}${endpoint.path}`;

  const res = http.get(url);

  check(res, {
    [`${endpoint.name}: status is 200`]: (r) => r.status === 200,
    [`${endpoint.name}: response time < 3s`]: (r) => r.timings.duration < 3000,
    [`${endpoint.name}: no errors`]: (r) => !r.body.includes('error'),
  });

  sleep(Math.random() * 2); // Random think time between 0-2 seconds
}
