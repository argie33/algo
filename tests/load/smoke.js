import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 1,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<2000', 'p(99)<3000'],
    http_req_failed: ['rate<0.1'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3001';

const endpoints = [
  { name: 'health', path: '/api/health', threshold: 200 },
  { name: 'signals', path: '/api/signals/search?limit=10', threshold: 1500 },
  { name: 'stocks', path: '/api/stocks?limit=10', threshold: 800 },
  { name: 'scores', path: '/api/scores?limit=10', threshold: 800 },
  { name: 'sentiment', path: '/api/sentiment', threshold: 1200 },
  { name: 'market-status', path: '/api/market/status', threshold: 500 },
];

export default function () {
  for (const endpoint of endpoints) {
    const url = `${BASE_URL}${endpoint.path}`;
    const res = http.get(url);

    check(res, {
      [`${endpoint.name}: status is 200`]: (r) => r.status === 200,
      [`${endpoint.name}: response time < ${endpoint.threshold}ms`]: (r) => r.timings.duration < endpoint.threshold,
      [`${endpoint.name}: has valid JSON`]: (r) => {
        try {
          JSON.parse(r.body);
          return true;
        } catch {
          return false;
        }
      },
    });

    sleep(0.5);
  }
}
