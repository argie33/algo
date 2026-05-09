import React, { useState, useEffect, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, AreaChart, Area, ReferenceLine,
} from 'recharts';
import { api } from '../services/api';

const WIN_THRESHOLD = 55;
const GOOD_R = 1.0;

function pct(n) { return `${n >= 0 ? '+' : ''}${n}%`; }
function fmt(n, dec = 1) { return n == null ? '—' : Number(n).toFixed(dec); }
function clr(n, threshold = 0) {
  return n > threshold ? 'var(--success)' : n < threshold ? 'var(--danger)' : 'var(--text-muted)';
}

export default function SignalIntelligence() {
  const [patterns, setPatterns] = useState([]);
  const [funnel, setFunnel] = useState(null);
  const [trades, setTrades] = useState([]);
  const [days, setDays] = useState(180);
  const [sortKey, setSortKey] = useState('total_trades');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [patR, funR, tradeR] = await Promise.all([
          api.get(`/api/algo/signal-performance-by-pattern?days=${days}`).catch(() => null),
          api.get('/api/algo/rejection-funnel').catch(() => null),
          api.get(`/api/algo/signal-performance?days=${days}`).catch(() => null),
        ]);
        setPatterns(patR?.data?.patterns || []);
        setFunnel(funR?.data || null);
        setTrades(tradeR?.data?.trades || []);
      } catch (e) {
        setError(e.message);
      }
      setLoading(false);
    };
    load();
  }, [days]);

  // Overall stats
  const overall = useMemo(() => {
    if (!patterns.length) return null;
    const total = patterns.reduce((s, p) => s + p.total_trades, 0);
    const wins = patterns.reduce((s, p) => s + p.wins, 0);
    const totalPnl = patterns.reduce((s, p) => s + p.total_pnl, 0);
    const avgR = patterns.length > 0
      ? patterns.reduce((s, p) => s + p.avg_r_multiple * p.total_trades, 0) / total : 0;
    return {
      total_trades: total,
      wins,
      win_rate: total > 0 ? Math.round(wins / total * 1000) / 10 : 0,
      total_pnl: totalPnl,
      avg_r: Math.round(avgR * 100) / 100,
    };
  }, [patterns]);

  // Sorted pattern list for chart
  const sortedPatterns = useMemo(() =>
    [...patterns].sort((a, b) => b[sortKey] - a[sortKey]),
    [patterns, sortKey]
  );

  // Funnel data for chart
  const funnelData = useMemo(() => {
    if (!funnel?.tiers) return [];
    return funnel.tiers.map(t => ({
      name: `T${t.tier}`,
      label: t.name,
      pass: t.pass,
      reject: t.reject > 0 ? t.reject : 0,
    }));
  }, [funnel]);

  const winRateColor = (wr) => wr >= WIN_THRESHOLD ? '#3fb950' : wr >= 45 ? '#d29922' : '#f85149';
  const rColor = (r) => r >= GOOD_R ? '#3fb950' : r >= 0 ? '#d29922' : '#f85149';

  if (loading) {
    return (
      <div className="main-content">
        <div className="page-head">
          <h1 className="page-head-title">Signal Intelligence</h1>
        </div>
        <div style={{ padding: '2rem', color: 'var(--text-muted)' }}>Loading signal data…</div>
      </div>
    );
  }

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <h1 className="page-head-title">Signal Intelligence</h1>
          <p className="page-head-sub">Pattern win rates · filter funnel · trade-level signal analysis</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          {[90, 180, 365].map(d => (
            <button key={d} className={`btn btn-sm ${days === d ? 'btn-brand' : 'btn-ghost'}`}
              onClick={() => setDays(d)}>{d}d</button>
          ))}
        </div>
      </div>

      {error && (
        <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--danger)', background: 'var(--danger-soft)' }}>
          <div className="card-body" style={{ color: 'var(--danger)', fontSize: '0.875rem' }}>Error loading data: {error}</div>
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-4" style={{ marginBottom: '1.5rem' }}>
        <div className="card">
          <div className="card-body">
            <div style={{ fontSize: '0.65rem', letterSpacing: '0.08em', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>TOTAL TRADES ANALYZED</div>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
              {overall?.total_trades ?? '—'}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>last {days} days, closed trades</div>
          </div>
        </div>
        <div className="card">
          <div className="card-body">
            <div style={{ fontSize: '0.65rem', letterSpacing: '0.08em', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>OVERALL WIN RATE</div>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: winRateColor(overall?.win_rate ?? 0) }}>
              {overall?.win_rate != null ? `${overall.win_rate}%` : '—'}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{overall?.wins ?? 0}W / {(overall?.total_trades ?? 0) - (overall?.wins ?? 0)}L</div>
          </div>
        </div>
        <div className="card">
          <div className="card-body">
            <div style={{ fontSize: '0.65rem', letterSpacing: '0.08em', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>AVG R-MULTIPLE</div>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: rColor(overall?.avg_r ?? 0) }}>
              {overall?.avg_r != null ? `${overall.avg_r >= 0 ? '+' : ''}${overall.avg_r}R` : '—'}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>per closed trade</div>
          </div>
        </div>
        <div className="card">
          <div className="card-body">
            <div style={{ fontSize: '0.65rem', letterSpacing: '0.08em', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>TOTAL P&amp;L</div>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: clr(overall?.total_pnl ?? 0) }}>
              {overall?.total_pnl != null ? `${overall.total_pnl >= 0 ? '+' : ''}$${Math.round(overall.total_pnl).toLocaleString()}` : '—'}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>realized, all patterns</div>
          </div>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
        {/* Win Rate by Pattern */}
        <div className="card">
          <div className="card-body">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '0.8rem', letterSpacing: '0.06em', fontWeight: 700 }}>WIN RATE BY PATTERN</h3>
              <div style={{ display: 'flex', gap: '0.25rem' }}>
                {[['win_rate_pct', 'Win%'], ['total_trades', 'Volume'], ['avg_r_multiple', 'Avg R']].map(([k, l]) => (
                  <button key={k} className={`btn btn-sm ${sortKey === k ? 'btn-brand' : 'btn-ghost'}`}
                    style={{ fontSize: '0.7rem', padding: '2px 8px' }}
                    onClick={() => setSortKey(k)}>{l}</button>
                ))}
              </div>
            </div>
            {sortedPatterns.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem', padding: '2rem 0', textAlign: 'center' }}>
                No pattern data — needs closed trades in signal_trade_performance table
              </div>
            ) : (
              <div style={{ height: Math.max(180, sortedPatterns.length * 36) }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sortedPatterns} layout="vertical" margin={{ top: 0, right: 60, bottom: 0, left: 100 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis type="number" domain={sortKey === 'win_rate_pct' ? [0, 100] : undefined}
                      tickFormatter={sortKey === 'win_rate_pct' ? v => `${v}%` : sortKey === 'avg_r_multiple' ? v => `${v}R` : String}
                      tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                    <YAxis type="category" dataKey="base_type" tick={{ fill: 'var(--text)', fontSize: 10 }} width={100} />
                    <ReferenceLine x={WIN_THRESHOLD} stroke="var(--text-muted)" strokeDasharray="4 2"
                      style={{ display: sortKey === 'win_rate_pct' ? 'block' : 'none' }} />
                    <Tooltip
                      contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 11 }}
                      formatter={(v, _, p) => {
                        const row = p.payload;
                        return [
                          `${row.win_rate_pct}% win  ·  ${row.avg_r_multiple}R avg  ·  ${row.total_trades} trades`,
                          row.base_type,
                        ];
                      }}
                    />
                    <Bar dataKey={sortKey} radius={[0, 3, 3, 0]}>
                      {sortedPatterns.map((p, i) => (
                        <Cell key={i} fill={
                          sortKey === 'win_rate_pct' ? winRateColor(p.win_rate_pct) :
                          sortKey === 'avg_r_multiple' ? rColor(p.avg_r_multiple) :
                          'var(--brand)'
                        } />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>

        {/* Signal Filter Funnel */}
        <div className="card">
          <div className="card-body">
            <h3 style={{ margin: '0 0 1rem', fontSize: '0.8rem', letterSpacing: '0.06em', fontWeight: 700 }}>
              SIGNAL FILTER FUNNEL — {funnel?.total_signals || 0} total signals
            </h3>
            {funnelData.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem', padding: '2rem 0', textAlign: 'center' }}>
                No funnel data available
              </div>
            ) : (
              <>
                <div style={{ height: 200 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={funnelData} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                      <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                      <Tooltip
                        contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 11 }}
                        formatter={(v, name, p) => [v, name === 'pass' ? `Pass (${p.payload.label})` : `Reject (${p.payload.label})`]}
                      />
                      <Bar dataKey="pass" fill="var(--success)" stackId="a" name="pass" />
                      <Bar dataKey="reject" fill="var(--danger)" stackId="a" name="reject" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.75rem' }}>
                  {funnelData.map(t => (
                    <div key={t.name} style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      <span style={{ color: 'var(--text)', fontWeight: 600 }}>{t.name}</span> {t.label}: {t.pass} pass / {t.reject} reject
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Pattern Performance Table */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-body">
          <h3 style={{ margin: '0 0 1rem', fontSize: '0.8rem', letterSpacing: '0.06em', fontWeight: 700 }}>
            PATTERN PERFORMANCE BREAKDOWN
          </h3>
          {sortedPatterns.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem', padding: '1rem 0' }}>No pattern data yet</div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Pattern', 'Trades', 'Win%', 'Avg R', 'Avg P&L%', 'Total P&L', 'Avg Hold', 'T1 Hit%', 'T2 Hit%'].map(h => (
                      <th key={h} style={{ textAlign: 'right', padding: '6px 12px', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.7rem', letterSpacing: '0.06em' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedPatterns.map((p, i) => (
                    <tr key={p.base_type} style={{
                      borderBottom: '1px solid var(--border-soft)',
                      background: i % 2 === 0 ? 'transparent' : 'var(--surface-2)',
                    }}>
                      <td style={{ padding: '7px 12px', fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>
                        {p.base_type}
                      </td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
                        {p.total_trades}
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', marginLeft: 4 }}>({p.wins}W/{p.losses}L)</span>
                      </td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 700, color: winRateColor(p.win_rate_pct) }}>
                        {p.win_rate_pct}%
                      </td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: rColor(p.avg_r_multiple) }}>
                        {p.avg_r_multiple >= 0 ? '+' : ''}{p.avg_r_multiple}R
                      </td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: clr(p.avg_pnl_pct) }}>
                        {p.avg_pnl_pct >= 0 ? '+' : ''}{fmt(p.avg_pnl_pct)}%
                      </td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: clr(p.total_pnl) }}>
                        {p.total_pnl >= 0 ? '+' : ''}${Math.round(p.total_pnl).toLocaleString()}
                      </td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {fmt(p.avg_hold_days)}d
                      </td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
                        {p.t1_hit_rate}%
                      </td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {p.t2_hit_rate}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Recent Trades Table */}
      {trades.length > 0 && (
        <div className="card">
          <div className="card-body">
            <h3 style={{ margin: '0 0 1rem', fontSize: '0.8rem', letterSpacing: '0.06em', fontWeight: 700 }}>
              RECENT SIGNAL TRADES — {trades.length} records
            </h3>
            <div style={{ overflowX: 'auto', maxHeight: 380, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)', position: 'sticky', top: 0, background: 'var(--surface)' }}>
                    {['Symbol', 'Pattern', 'Signal Date', 'Entry', 'Exit', 'P&L%', 'R-Mult', 'Hold', 'Grade', 'T1', 'T2'].map(h => (
                      <th key={h} style={{ textAlign: 'right', padding: '6px 10px', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.68rem', letterSpacing: '0.05em' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t, i) => (
                    <tr key={t.trade_id || i} style={{
                      borderBottom: '1px solid var(--border-soft)',
                      background: i % 2 === 0 ? 'transparent' : 'var(--surface-2)',
                    }}>
                      <td style={{ padding: '5px 10px', fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>{t.symbol}</td>
                      <td style={{ padding: '5px 10px', color: 'var(--text-muted)', textAlign: 'right', fontSize: '0.72rem' }}>{t.base_type || '—'}</td>
                      <td style={{ padding: '5px 10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', textAlign: 'right' }}>{t.signal_date}</td>
                      <td style={{ padding: '5px 10px', color: 'var(--text)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>${fmt(t.entry_price, 2)}</td>
                      <td style={{ padding: '5px 10px', color: 'var(--text)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>${fmt(t.exit_price, 2)}</td>
                      <td style={{ padding: '5px 10px', fontFamily: 'var(--font-mono)', fontWeight: 700, textAlign: 'right', color: clr(t.realized_pnl_pct) }}>
                        {t.realized_pnl_pct >= 0 ? '+' : ''}{fmt(t.realized_pnl_pct)}%
                      </td>
                      <td style={{ padding: '5px 10px', fontFamily: 'var(--font-mono)', textAlign: 'right', color: rColor(t.r_multiple) }}>
                        {t.r_multiple >= 0 ? '+' : ''}{fmt(t.r_multiple)}R
                      </td>
                      <td style={{ padding: '5px 10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>{t.hold_days}d</td>
                      <td style={{ padding: '5px 10px', textAlign: 'right' }}>
                        <span style={{
                          background: { 'A+': '#238636', A: '#1a3a20', B: '#1a2a3a', C: '#3a3a14', D: '#3a2014', F: '#3a1414' }[t.swing_grade] || 'transparent',
                          color: { 'A+': '#3fb950', A: '#3fb950', B: '#58a6ff', C: '#d29922', D: '#fb950c', F: '#f85149' }[t.swing_grade] || 'var(--text-muted)',
                          padding: '1px 5px', borderRadius: 3, fontSize: '0.7rem', fontWeight: 700, fontFamily: 'var(--font-mono)',
                        }}>{t.swing_grade || '—'}</span>
                      </td>
                      <td style={{ padding: '5px 10px', textAlign: 'right', color: t.target_1_hit ? 'var(--success)' : 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {t.target_1_hit ? '✓' : '—'}
                      </td>
                      <td style={{ padding: '5px 10px', textAlign: 'right', color: t.target_2_hit ? 'var(--success)' : 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {t.target_2_hit ? '✓' : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
