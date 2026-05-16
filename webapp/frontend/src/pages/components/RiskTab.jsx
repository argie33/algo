import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis,
  Tooltip as RechartTooltip, ResponsiveContainer, Cell
} from 'recharts';

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

const COLORS = ['var(--brand)', 'var(--purple)', 'var(--success)', 'var(--amber)', 'var(--danger)', 'var(--cyan)'];

function RiskTab({ circuitBreakers, markets, positions = [] }) {
  const breakers = Array.isArray(circuitBreakers) ? circuitBreakers : (circuitBreakers?.breakers || []);
  const anyTriggered = Array.isArray(circuitBreakers) ? false : circuitBreakers?.any_triggered;

  const sectorExposure = React.useMemo(() => {
    const totals = {};
    positions.forEach(p => {
      const s = p.sector || 'Unknown';
      totals[s] = (totals[s] || 0) + (p.position_value || 0);
    });
    const total = Object.values(totals).reduce((a, b) => a + b, 0);
    return Object.entries(totals)
      .map(([sector, value]) => ({ sector, value, pct: total > 0 ? Math.round(value / total * 1000) / 10 : 0 }))
      .sort((a, b) => b.value - a.value);
  }, [positions]);

  const statusColor = (triggered) => triggered ? 'var(--danger)' : 'var(--success)';
  const breakerBg = (triggered) => triggered ? 'rgba(225, 29, 72, 0.1)' : 'rgba(34, 197, 94, 0.1)';
  const breakerBorder = (triggered) => triggered ? 'var(--danger)' : 'var(--success)';

  const getPct = (current, threshold) => threshold > 0 ? Math.min(current / threshold * 100, 100) : 0;

  return (
    <div style={{ padding: 'var(--space-4)' }}>
      {anyTriggered && (
        <div className="alert alert-danger" style={{ marginBottom: 'var(--space-4)' }}>
          <strong>{!Array.isArray(circuitBreakers) ? circuitBreakers.triggered_count : breakers.filter(b => b.triggered).length} circuit breaker{(!Array.isArray(circuitBreakers) ? circuitBreakers.triggered_count : breakers.filter(b => b.triggered).length) !== 1 ? 's' : ''} triggered</strong> — new entries halted
        </div>
      )}

      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="card-head">
          <div className="card-title">Circuit Breakers — Kill-Switch Status</div>
        </div>
        <div className="card-body">
          <div className="grid grid-3" style={{ gap: 'var(--space-4)' }}>
            {breakers.map(b => (
              <div key={b.id} style={{
                padding: 'var(--space-3)',
                background: breakerBg(b.triggered),
                border: `1px solid ${breakerBorder(b.triggered)}`,
                borderLeft: `4px solid ${statusColor(b.triggered)}`,
                borderRadius: 'var(--r-md)',
              }}>
                <div className="flex items-start justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                  <div style={{ flex: 1 }}>
                    <div className="t-2xs muted strong">{b.label}</div>
                    <div className="flex items-baseline gap-1" style={{ marginTop: 4 }}>
                      <div className="mono tnum" style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)', color: statusColor(b.triggered) }}>
                        {b.current}{b.unit}
                      </div>
                      <div className="t-xs muted">{b.threshold}{b.unit}</div>
                    </div>
                    <div style={{
                      marginTop: 'var(--space-2)',
                      height: 4,
                      background: 'var(--border-soft)',
                      borderRadius: 'var(--r-pill)',
                      overflow: 'hidden',
                    }}>
                      <div style={{
                        width: `${getPct(b.current, b.threshold)}%`,
                        height: '100%',
                        background: statusColor(b.triggered),
                        transition: 'width 0.3s',
                      }} />
                    </div>
                  </div>
                  <span className={`badge ${b.triggered ? 'badge-danger' : 'badge-success'}`} style={{ marginLeft: 'var(--space-2)' }}>
                    {b.triggered ? 'TRIPPED' : 'OK'}
                  </span>
                </div>
                <div className="t-2xs muted" style={{ marginTop: 'var(--space-2)' }}>{b.description}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-2" style={{ gap: 'var(--space-4)' }}>
        <div className="card">
          <div className="card-head">
            <div className="card-title">Sector Exposure</div>
            <div className="card-sub">{positions.length} open positions</div>
          </div>
          <div className="card-body">
            {sectorExposure.length === 0 ? (
              <div className="empty"><div className="empty-title">No open positions</div></div>
            ) : (
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sectorExposure} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 80 }}>
                    <XAxis type="number" tickFormatter={v => `${v}%`} tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                    <YAxis type="category" dataKey="sector" tick={{ fill: 'var(--text)', fontSize: 10 }} width={80} />
                    <RechartTooltip
                      contentStyle={TOOLTIP_STYLE}
                      formatter={(v, n, p) => [`${p.payload.pct}% ($${p.payload.value?.toLocaleString()})`, 'Exposure']}
                    />
                    <Bar dataKey="pct" radius={[0, 3, 3, 0]}>
                      {sectorExposure.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Position Risk Summary</div>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {positions.length === 0 ? (
              <div className="empty"><div className="empty-title">No open positions</div></div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th className="num">Value</th>
                      <th className="num">Stop Dist</th>
                      <th className="num">At Risk $</th>
                      <th>Sector</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map(p => (
                      <tr key={p.symbol}>
                        <td className="strong mono">{p.symbol}</td>
                        <td className="num mono tnum">${Math.round(p.position_value || 0).toLocaleString()}</td>
                        <td className={`num mono tnum ${p.distance_to_stop_pct < 3 ? 'down' : p.distance_to_stop_pct < 5 ? 'muted' : ''}`}>
                          {p.distance_to_stop_pct != null ? `${p.distance_to_stop_pct.toFixed(1)}%` : '—'}
                        </td>
                        <td className="num mono tnum down">${Math.round(p.open_risk_dollars || 0).toLocaleString()}</td>
                        <td className="t-xs muted">{p.sector || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default RiskTab;
