const BASE = 'http://localhost:3001';
const endpoints = [
  '/api/algo/status',
  '/api/algo/positions',
  '/api/algo/performance',
  '/api/algo/trades?limit=5',
  '/api/algo/equity-curve?limit=5',
  '/api/algo/circuit-breakers',
  '/api/algo/daily-return-histogram',
  '/api/algo/trade-distribution',
  '/api/algo/holding-period-distribution',
  '/api/algo/stage-distribution',
  '/api/algo/data-status',
  '/api/algo/metrics',
  '/api/algo/risk-metrics',
  '/api/algo/performance-analytics',
  '/api/algo/sentiment',
  '/api/algo/economic-calendar',
  '/api/algo/portfolio',
  '/api/algo/exposure-policy',
  '/api/algo/last-run',
  '/api/algo/sector-position-warnings',
  '/api/algo/swing-scores?limit=5',
  '/api/algo/rejection-funnel',
  '/api/algo/evaluate',
  '/api/algo/data-quality',
  '/api/algo/market-sentiment',
  '/api/algo/trend-criteria',
  '/api/algo/performance-metrics',
  '/api/algo/portfolio-summary',
];

for (const ep of endpoints) {
  try {
    const r = await fetch(`${BASE}${ep}`);
    const json = await r.json();
    const data = json.data;
    const status = json.statusCode || r.status;

    if (status >= 400 || json.errorType || json._error) {
      console.log(`❌ ${status} ${ep}`);
      console.log(`   errorType=${json.errorType}, msg=${json.message || json._error || ''}`);
    } else {
      // Show what's in the data
      let summary = '';
      if (data === null || data === undefined) {
        summary = 'NULL DATA';
      } else if (Array.isArray(data)) {
        summary = `array[${data.length}]`;
        if (data.length === 0) summary = '⚠️  EMPTY ARRAY';
      } else if (typeof data === 'object') {
        const keys = Object.keys(data);
        // Show key sizes
        const sizes = keys.map(k => {
          const v = data[k];
          if (Array.isArray(v)) return `${k}[${v.length}]`;
          if (v === null || v === undefined) return `${k}=null`;
          if (typeof v === 'object') return `${k}={...}`;
          return `${k}=${String(v).substring(0, 20)}`;
        }).slice(0, 6).join(', ');
        summary = sizes;
      } else {
        summary = String(data).substring(0, 100);
      }
      console.log(`✅ ${status} ${ep} → ${summary}`);
    }
  } catch(e) {
    console.log(`💥 FAILED ${ep}: ${e.message}`);
  }
}
