/**
 * Trading Signals — analytical workbench for swing-trader signals.
 *
 * Sections:
 *   - Enhanced KPI strip (totals + crossings + freshness + quality)
 *   - 4-quadrant heatmap (SQS × age, sized by volume)
 *   - Setup-type breakdown (BUY signals by base type)
 *   - Recent signal performance (5d/20d return + hit rate)
 *   - SQS distribution histogram
 *   - Multi-select sector chips, score range, days-since slider, gates toggle
 *   - Row-expand: 60d sparkline, entry plan, gates pass status, reason
 *
 * Pure JSX + theme.css. Recharts only for charts.
 */

import React, { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Search, RefreshCw, Inbox, ChevronDown, ChevronUp } from 'lucide-react';
import {
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis,
  Tooltip, CartesianGrid, BarChart, Bar, Cell, AreaChart, Area, ReferenceLine,
} from 'recharts';
import { api } from '../services/api';

// ─── formatters ────────────────────────────────────────────────────────────
const fmtMoney = (v) => v == null ? '—' : `$${Number(v).toFixed(2)}`;
const fmtPct = (v) => v == null ? '—' : `${Number(v).toFixed(2)}%`;
const fmtInt = (v) => v == null ? '—' : Number(v).toLocaleString('en-US');
const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

const STAGE_VARIANT = {
  'Stage 1': 'badge', 'Stage 2': 'badge-success', 'Stage 2 - Markup': 'badge-success',
  'Stage 3': 'badge-amber', 'Stage 3 - Topping': 'badge-amber', 'Stage 4': 'badge-danger',
};
const QUALITY_VARIANT = { STRONG: 'badge-success', MODERATE: 'badge-amber', WEAK: 'badge-danger' };

const daysSince = (d) => {
  if (!d) return null;
  const ts = new Date(d).getTime();
  if (isNaN(ts)) return null;
  return Math.max(0, Math.floor((Date.now() - ts) / 86400000));
};

const sqsOf = (r) =>
  r.entry_quality_score ??
  r.signal_strength ??
  r.strength ??
  null;

// ─── main page ─────────────────────────────────────────────────────────────
export default function TradingSignals() {
  const [tab, setTab] = useState('stocks');
  const [signal, setSignal] = useState('all');
  const [timeframe, setTimeframe] = useState('daily');
  const [search, setSearch] = useState('');
  const [stageFilter, setStageFilter] = useState('all');
  const [sectorFilter, setSectorFilter] = useState([]); // multi-select chips
  const [scoreRange, setScoreRange] = useState([0, 100]);
  const [maxAge, setMaxAge] = useState(30);
  const [gatesOnly, setGatesOnly] = useState(false);
  const [expandedKey, setExpandedKey] = useState(null);

  const endpoint = tab === 'etfs' ? '/api/signals/etf' : '/api/signals/stocks';

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['signals', tab, signal, timeframe],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set('timeframe', timeframe);
      params.set('limit', '500');
      if (signal !== 'all') params.set('signal', signal);
      return api.get(`${endpoint}?${params.toString()}`).then(r => r.data);
    },
    refetchInterval: 60000,
  });

  // Pull swing scores so we can join "passes algo gates" + better SQS
  const { data: gatesData } = useQuery({
    queryKey: ['signals-gates'],
    queryFn: () =>
      api.get('/api/algo/swing-scores?limit=2000&min_score=0').then(r => r.data?.items || []),
    refetchInterval: 120000,
    enabled: tab === 'stocks',
  });

  const gateMap = useMemo(() => {
    const m = new Map();
    (gatesData || []).forEach(g => m.set(g.symbol, g));
    return m;
  }, [gatesData]);

  const rows = data?.items || data?.data || [];

  // Enrich rows with gate / sqs info
  const enriched = useMemo(() => rows.map(r => {
    const g = gateMap.get(r.symbol);
    return {
      ...r,
      _age: daysSince(r.signal_triggered_date || r.date),
      _sqs: sqsOf(r) ?? (g?.swing_score ?? null),
      _pass_gates: g?.pass_gates ?? null,
      _grade: g?.grade ?? null,
      _fail_reason: g?.fail_reason ?? null,
    };
  }), [rows, gateMap]);

  const allSectors = useMemo(() =>
    Array.from(new Set(enriched.map(r => r.sector).filter(Boolean))).sort(),
    [enriched]);

  const filtered = useMemo(() => {
    let r = enriched;
    if (search) {
      const q = search.trim().toUpperCase();
      r = r.filter(x => x.symbol?.startsWith(q));
    }
    if (stageFilter !== 'all') r = r.filter(x => (x.market_stage || '').includes(stageFilter));
    if (sectorFilter.length > 0) r = r.filter(x => sectorFilter.includes(x.sector));
    if (scoreRange[0] > 0 || scoreRange[1] < 100) {
      r = r.filter(x => {
        const s = x._sqs;
        if (s == null) return false;
        return s >= scoreRange[0] && s <= scoreRange[1];
      });
    }
    if (maxAge < 90) r = r.filter(x => x._age == null || x._age <= maxAge);
    if (gatesOnly) r = r.filter(x => x._pass_gates === true);
    return r;
  }, [enriched, search, stageFilter, sectorFilter, scoreRange, maxAge, gatesOnly]);

  // KPI calculations
  const kpi = useMemo(() => {
    const buys = filtered.filter(r => (r.signal || '').toUpperCase() === 'BUY');
    const sells = filtered.filter(r => (r.signal || '').toUpperCase() === 'SELL');
    const cross50 = filtered.filter(r => r.close != null && r.sma_50 != null
      && r.close > r.sma_50 && r.close - r.sma_50 < r.sma_50 * 0.02).length;
    const cross200 = filtered.filter(r => r.close != null && r.sma_200 != null
      && r.close > r.sma_200 && r.close - r.sma_200 < r.sma_200 * 0.02).length;
    const fresh = buys.filter(r => r._age != null && r._age <= 3).length;
    const hq = buys.filter(r => r._sqs != null && r._sqs > 80).length;
    return {
      total: filtered.length,
      buys: buys.length,
      sells: sells.length,
      ratio: sells.length === 0 ? '∞' : (buys.length / sells.length).toFixed(2),
      cross50,
      cross200,
      fresh,
      hq,
    };
  }, [filtered]);

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Trading Signals</div>
          <div className="page-head-sub">
            {tab === 'stocks' ? 'Pine-script signals for stocks' : 'Pine-script signals for ETFs'}
            {' · click any row for full detail'}
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 'var(--space-4)' }}>
        {[['stocks','Stocks'],['etfs','ETFs']].map(([v, lbl]) => (
          <button key={v} type="button" onClick={() => setTab(v)} style={{
            background: 'transparent', border: 'none',
            borderBottom: `2px solid ${tab === v ? 'var(--brand)' : 'transparent'}`,
            color: tab === v ? 'var(--brand-2)' : 'var(--text-muted)',
            fontWeight: tab === v ? 'var(--w-semibold)' : 'var(--w-medium)',
            fontSize: 'var(--t-sm)', padding: '12px 16px', cursor: 'pointer', marginBottom: -1,
          }}>{lbl} {tab === v && <span className="badge mono tnum" style={{ marginLeft: 6 }}>{rows.length}</span>}</button>
        ))}
      </div>

      {/* Enhanced KPI strip */}
      <div className="grid grid-4" style={{ marginBottom: 'var(--space-3)' }}>
        <div className="kpi"><div className="kpi-label">Total Signals</div><div className="kpi-value">{kpi.total}</div></div>
        <div className="kpi"><div className="kpi-label">BUY</div><div className="kpi-value up">{kpi.buys}</div></div>
        <div className="kpi"><div className="kpi-label">SELL</div><div className="kpi-value down">{kpi.sells}</div></div>
        <div className="kpi">
          <div className="kpi-label">BUY/SELL Ratio</div>
          <div className="kpi-value">{kpi.ratio}</div>
          <div className="kpi-sub">{kpi.buys > kpi.sells ? 'risk on' : kpi.buys < kpi.sells ? 'risk off' : 'even'}</div>
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="kpi">
          <div className="kpi-label">Crossing 50-day</div>
          <div className="kpi-value">{kpi.cross50}</div>
          <div className="kpi-sub">close within 2% above</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Crossing 200-day</div>
          <div className="kpi-value">{kpi.cross200}</div>
          <div className="kpi-sub">close within 2% above</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Fresh BUYs</div>
          <div className="kpi-value up">{kpi.fresh}</div>
          <div className="kpi-sub">≤ 3 days old</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">High Quality BUYs</div>
          <div className="kpi-value up">{kpi.hq}</div>
          <div className="kpi-sub">SQS &gt; 80</div>
        </div>
      </div>

      {/* Charts row 1 — heatmap + setup breakdown */}
      <div className="grid grid-2" style={{ marginBottom: 'var(--space-4)' }}>
        <SignalHeatmap rows={filtered} />
        <SetupBreakdown rows={filtered} />
      </div>

      {/* Charts row 2 — performance + SQS histogram */}
      <div className="grid grid-2" style={{ marginBottom: 'var(--space-4)' }}>
        <RecentPerformance rows={enriched} timeframe={timeframe} />
        <SqsHistogram rows={filtered} />
      </div>

      {/* Filters */}
      <div className="card card-pad-sm" style={{ marginBottom: 'var(--space-3)' }}>
        <div className="flex gap-3" style={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-faint)' }} />
            <input className="input" placeholder="Symbol (starts with)" value={search}
              onChange={e => setSearch(e.target.value)} style={{ paddingLeft: 32 }} />
          </div>
          <select className="select" value={signal} onChange={e => setSignal(e.target.value)} style={{ width: 130 }}>
            <option value="all">All signals</option>
            <option value="BUY">BUY only</option>
            <option value="SELL">SELL only</option>
          </select>
          <select className="select" value={timeframe} onChange={e => setTimeframe(e.target.value)} style={{ width: 120 }}>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
          <select className="select" value={stageFilter} onChange={e => setStageFilter(e.target.value)} style={{ width: 170 }}>
            <option value="all">All stages</option>
            <option value="Stage 1">Stage 1 (Basing)</option>
            <option value="Stage 2">Stage 2 (Markup)</option>
            <option value="Stage 3">Stage 3 (Topping)</option>
            <option value="Stage 4">Stage 4 (Decline)</option>
          </select>
          {tab === 'stocks' && (
            <label className="flex items-center gap-2" style={{ fontSize: 'var(--t-xs)', color: 'var(--text-muted)', cursor: 'pointer' }}>
              <input type="checkbox" checked={gatesOnly} onChange={e => setGatesOnly(e.target.checked)} />
              <span>Passes algo gates</span>
            </label>
          )}
        </div>

        {/* Sliders + chips */}
        <div className="flex gap-3" style={{ flexWrap: 'wrap', marginTop: 'var(--space-3)', alignItems: 'center' }}>
          <SliderField label="SQS range" value={scoreRange[0]} max={100}
            onChange={v => setScoreRange([Number(v), scoreRange[1]])} suffix={`–${scoreRange[1]}`} />
          <SliderField label="" value={scoreRange[1]} max={100}
            onChange={v => setScoreRange([scoreRange[0], Number(v)])} suffix="" />
          <SliderField label="Max age (days)" value={maxAge} max={90}
            onChange={v => setMaxAge(Number(v))} suffix={maxAge >= 90 ? 'all' : `${maxAge}d`} />
        </div>

        {allSectors.length > 0 && (
          <div className="flex gap-2" style={{ flexWrap: 'wrap', marginTop: 'var(--space-3)' }}>
            <span className="eyebrow" style={{ alignSelf: 'center' }}>Sectors</span>
            {allSectors.map(s => {
              const on = sectorFilter.includes(s);
              return (
                <button key={s} type="button"
                  onClick={() => setSectorFilter(on
                    ? sectorFilter.filter(x => x !== s)
                    : [...sectorFilter, s])}
                  className={`badge ${on ? 'badge-brand' : ''}`}
                  style={{ cursor: 'pointer', border: on ? 'none' : '1px solid var(--border)' }}>
                  {s}
                </button>
              );
            })}
            {sectorFilter.length > 0 && (
              <button type="button" onClick={() => setSectorFilter([])}
                className="badge" style={{ cursor: 'pointer', color: 'var(--text-muted)' }}>
                clear
              </button>
            )}
          </div>
        )}
      </div>

      <SignalsTable rows={filtered} loading={isLoading} kind={tab}
        expandedKey={expandedKey} setExpandedKey={setExpandedKey} />
    </div>
  );
}

// ─── slider field ──────────────────────────────────────────────────────────
function SliderField({ label, value, max, onChange, suffix }) {
  return (
    <div className="flex items-center gap-2" style={{ minWidth: 200 }}>
      {label && <span className="t-xs muted" style={{ minWidth: 90 }}>{label}</span>}
      <input
        type="range"
        min={0} max={max} value={value}
        onChange={e => onChange(e.target.value)}
        style={{ flex: 1, accentColor: 'var(--brand)' }}
      />
      <span className="t-xs mono tnum" style={{ minWidth: 36, textAlign: 'right', color: 'var(--text-2)' }}>
        {suffix}
      </span>
    </div>
  );
}

// ─── chart: signal heatmap ─────────────────────────────────────────────────
function SignalHeatmap({ rows }) {
  const data = useMemo(() => rows
    .filter(r => r._sqs != null && r._age != null && r.close != null)
    .map(r => ({
      symbol: r.symbol,
      sqs: Number(r._sqs),
      age: Number(r._age),
      vol: Number(r.volume) || 1,
      sector: r.sector || '—',
      close: Number(r.close),
      sig: (r.signal || '').toUpperCase(),
    })),
  [rows]);
  const buys = data.filter(d => d.sig === 'BUY');
  const sells = data.filter(d => d.sig === 'SELL');
  const navigate = useNavigate();

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Signal Heatmap</div>
          <div className="card-sub">SQS × Age · bubble size = volume · click to drill</div>
        </div>
      </div>
      <div className="card-body">
        {data.length === 0
          ? <Empty title="Not enough data for heatmap" />
          : (
            <div style={{ height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                  <XAxis type="number" dataKey="sqs" name="SQS" domain={[0, 100]}
                    stroke="var(--text-3)" fontSize={11} tickLine={false}
                    label={{ value: 'Composite SQS', position: 'insideBottom', offset: -2, fill: 'var(--text-muted)', fontSize: 10 }} />
                  <YAxis type="number" dataKey="age" name="Age (d)" reversed
                    stroke="var(--text-3)" fontSize={11} tickLine={false} width={36}
                    label={{ value: 'Days', angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 10 }} />
                  <ZAxis type="number" dataKey="vol" range={[40, 360]} />
                  <ReferenceLine x={50} stroke="var(--border-2)" strokeDasharray="2 4" />
                  <ReferenceLine y={7} stroke="var(--border-2)" strokeDasharray="2 4" />
                  <Tooltip cursor={{ strokeDasharray: '2 4' }} contentStyle={TOOLTIP_STYLE}
                    formatter={(v, k) => k === 'sqs' ? [`${Number(v).toFixed(1)}`, 'SQS']
                      : k === 'age' ? [`${v}d`, 'Age']
                      : k === 'vol' ? [fmtInt(v), 'Volume'] : v}
                    labelFormatter={() => ''}
                    content={({ active, payload }) => {
                      if (!active || !payload || !payload.length) return null;
                      const p = payload[0].payload;
                      return (
                        <div style={TOOLTIP_STYLE}>
                          <div style={{ fontWeight: 'var(--w-semibold)' }}>{p.symbol} <span style={{ color: p.sig === 'BUY' ? 'var(--success)' : 'var(--danger)' }}>{p.sig}</span></div>
                          <div className="muted t-2xs">{p.sector}</div>
                          <div className="t-2xs">${p.close.toFixed(2)} · SQS {p.sqs.toFixed(1)} · {p.age}d</div>
                        </div>
                      );
                    }} />
                  <Scatter data={buys} fill="var(--success)" fillOpacity={0.65}
                    onClick={(e) => e?.symbol && navigate(`/app/stock/${e.symbol}`)} />
                  <Scatter data={sells} fill="var(--danger)" fillOpacity={0.65}
                    onClick={(e) => e?.symbol && navigate(`/app/stock/${e.symbol}`)} />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          )}
      </div>
    </div>
  );
}

// ─── chart: setup type breakdown ───────────────────────────────────────────
function SetupBreakdown({ rows }) {
  const data = useMemo(() => {
    const buckets = {};
    rows.filter(r => (r.signal || '').toUpperCase() === 'BUY' && r.base_type).forEach(r => {
      const k = r.base_type;
      buckets[k] = (buckets[k] || 0) + 1;
    });
    return Object.entries(buckets)
      .map(([type, count]) => ({ type, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8);
  }, [rows]);

  const COLORS = ['var(--brand)', 'var(--cyan)', 'var(--purple)', 'var(--success)',
                  'var(--amber)', 'var(--brand-2)', 'var(--danger)', 'var(--text-3)'];

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Setup Type Breakdown</div>
          <div className="card-sub">BUY signals by base pattern</div>
        </div>
      </div>
      <div className="card-body">
        {data.length === 0
          ? <Empty title="No base-type data" desc="base_type column is empty for these signals." />
          : (
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" horizontal={false} />
                  <XAxis type="number" stroke="var(--text-3)" fontSize={11} tickLine={false} allowDecimals={false} />
                  <YAxis type="category" dataKey="type" stroke="var(--text-3)" fontSize={11}
                    tickLine={false} width={130}
                    tickFormatter={(v) => v.length > 16 ? v.slice(0, 14) + '…' : v} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'var(--surface-2)' }} />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                    {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
      </div>
    </div>
  );
}

// ─── chart: recent performance (look-back) ─────────────────────────────────
function RecentPerformance({ rows, timeframe }) {
  // For BUY signals from last 30 days, fetch price history per symbol and
  // compute 5d / 20d forward returns. Returns aggregated stats.
  const recentBuys = useMemo(() =>
    rows.filter(r =>
      (r.signal || '').toUpperCase() === 'BUY' &&
      r._age != null && r._age >= 5 && r._age <= 30 &&
      r.symbol && r.close != null
    ).slice(0, 40),  // cap to keep request count sane
  [rows]);

  const symbols = recentBuys.map(r => r.symbol).join(',');

  const { data: perfData, isLoading } = useQuery({
    queryKey: ['signal-perf', symbols, timeframe],
    queryFn: async () => {
      if (!recentBuys.length) return [];
      // Fetch in parallel, capped
      const promises = recentBuys.slice(0, 25).map(r =>
        api.get(`/api/prices/history/${r.symbol}?timeframe=${timeframe}&limit=60`)
           .then(res => ({ symbol: r.symbol, items: res.data?.data?.items || res.data?.items || [], entry: r }))
           .catch(() => ({ symbol: r.symbol, items: [], entry: r }))
      );
      return Promise.all(promises);
    },
    enabled: recentBuys.length > 0,
    staleTime: 300000,
  });

  const stats = useMemo(() => {
    if (!perfData || perfData.length === 0) return null;
    const r5 = [], r20 = [], wins20 = [];
    perfData.forEach(({ items, entry }) => {
      if (!items || items.length < 6) return;
      // items returned newest-first
      const sorted = [...items].sort((a, b) => new Date(b.date) - new Date(a.date));
      const sigDate = new Date(entry.signal_triggered_date || entry.date).getTime();
      // find the index of the signal day, then look forward
      const idxSignal = sorted.findIndex(p => new Date(p.date).getTime() <= sigDate);
      if (idxSignal < 0) return;
      const entryPx = Number(sorted[idxSignal]?.close);
      if (!entryPx) return;
      const px5 = Number(sorted[Math.max(0, idxSignal - 5)]?.close);
      const px20 = Number(sorted[Math.max(0, idxSignal - 20)]?.close);
      if (px5 && idxSignal >= 5) r5.push(((px5 - entryPx) / entryPx) * 100);
      if (px20 && idxSignal >= 20) {
        const ret20 = ((px20 - entryPx) / entryPx) * 100;
        r20.push(ret20);
        wins20.push(ret20 > 0 ? 1 : 0);
      }
    });
    const avg = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
    return {
      sample: perfData.length,
      avg5: avg(r5),
      avg20: avg(r20),
      hit20: wins20.length ? (wins20.filter(x => x).length / wins20.length) * 100 : null,
      n5: r5.length, n20: r20.length,
    };
  }, [perfData]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Recent Signal Performance</div>
          <div className="card-sub">BUY signals 5–30d ago · forward returns</div>
        </div>
      </div>
      <div className="card-body">
        {recentBuys.length === 0 ? (
          <Empty title="No mature BUYs" desc="Need BUY signals 5+ days old to compute returns." />
        ) : isLoading ? (
          <Empty title="Computing forward returns…" />
        ) : !stats ? (
          <Empty title="No performance data available" />
        ) : (
          <div className="grid grid-3" style={{ gap: 'var(--space-3)' }}>
            <Stile label="Avg 5d return"
              value={stats.avg5 != null ? `${stats.avg5 >= 0 ? '+' : ''}${stats.avg5.toFixed(2)}%` : '—'}
              tone={stats.avg5 == null ? 'flat' : stats.avg5 >= 0 ? 'up' : 'down'}
              sub={`n=${stats.n5}`} />
            <Stile label="Avg 20d return"
              value={stats.avg20 != null ? `${stats.avg20 >= 0 ? '+' : ''}${stats.avg20.toFixed(2)}%` : '—'}
              tone={stats.avg20 == null ? 'flat' : stats.avg20 >= 0 ? 'up' : 'down'}
              sub={`n=${stats.n20}`} />
            <Stile label="Hit rate (20d)"
              value={stats.hit20 != null ? `${stats.hit20.toFixed(0)}%` : '—'}
              tone={stats.hit20 == null ? 'flat' : stats.hit20 >= 50 ? 'up' : 'down'}
              sub={`% positive @ 20d`} />
            <div className="muted t-2xs col-span-3" style={{ marginTop: 4 }}>
              Sample size: {stats.sample} symbols · {timeframe} bars
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── chart: SQS distribution histogram ─────────────────────────────────────
function SqsHistogram({ rows }) {
  const data = useMemo(() => {
    const bins = Array.from({ length: 10 }, (_, i) => ({
      range: `${i * 10}–${i * 10 + 10}`,
      lo: i * 10, hi: i * 10 + 10, count: 0,
    }));
    rows.filter(r => (r.signal || '').toUpperCase() === 'BUY' && r._sqs != null).forEach(r => {
      const v = Number(r._sqs);
      const idx = Math.min(9, Math.max(0, Math.floor(v / 10)));
      bins[idx].count += 1;
    });
    return bins;
  }, [rows]);

  const maxCount = Math.max(...data.map(d => d.count), 1);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">SQS Distribution</div>
          <div className="card-sub">Composite signal quality across BUY signals</div>
        </div>
      </div>
      <div className="card-body">
        {maxCount === 1 && data.every(d => d.count === 0) ? (
          <Empty title="No SQS data" desc="No quality scores joined to current signals." />
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="range" stroke="var(--text-3)" fontSize={11} tickLine={false} interval={0} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false} allowDecimals={false} width={32} />
                <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'var(--surface-2)' }} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {data.map((b, i) => (
                    <Cell key={i}
                      fill={b.lo >= 80 ? 'var(--success)'
                        : b.lo >= 60 ? 'var(--brand)'
                        : b.lo >= 40 ? 'var(--amber)' : 'var(--danger)'}
                      fillOpacity={0.85} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── stile ─────────────────────────────────────────────────────────────────
function Stile({ label, value, sub, tone }) {
  return (
    <div className="stile">
      <div className="stile-label">{label}</div>
      <div className={`stile-value mono tnum ${tone || ''}`}>{value}</div>
      {sub && <div className="stile-sub">{sub}</div>}
    </div>
  );
}

// ─── table ─────────────────────────────────────────────────────────────────
function SignalsTable({ rows, loading, kind, expandedKey, setExpandedKey }) {
  const navigate = useNavigate();
  if (loading) return <Empty title="Loading…" />;
  if (rows.length === 0) return <Empty title="No active signals" desc={`No ${kind} signals match these filters.`} />;

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <div style={{ overflow: 'auto', maxHeight: '70vh' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Sector</th>
              <th className="num">Close</th>
              <th className="num">Buy Lvl</th>
              <th className="num">Stop</th>
              <th className="num">R/R</th>
              <th className="num">SQS</th>
              <th className="num">RSI</th>
              <th className="num">Vol Surge</th>
              <th>Base</th>
              <th>Stage</th>
              <th>Gates</th>
              <th className="num">Age</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const k = `${r.symbol}-${r.date}-${i}`;
              const expanded = expandedKey === k;
              const sig = (r.signal || '').toUpperCase();
              const rsi = r.rsi != null ? Number(r.rsi) : null;
              return (
                <React.Fragment key={k}>
                  <tr onClick={() => setExpandedKey(expanded ? null : k)}>
                    <td>
                      <div className="flex items-center gap-2">
                        <span className="strong" style={{ fontWeight: 'var(--w-bold)' }}>{r.symbol}</span>
                        <span className={`badge ${sig === 'BUY' ? 'badge-success' : 'badge-danger'}`}>{sig}</span>
                        {expanded ? <ChevronUp size={12} className="muted" /> : <ChevronDown size={12} className="muted" />}
                      </div>
                    </td>
                    <td className="muted t-xs">{r.sector || '—'}</td>
                    <td className="num">{fmtMoney(r.close)}</td>
                    <td className="num">
                      <span className={r.close >= r.buylevel ? 'up' : 'muted'}>{fmtMoney(r.buylevel)}</span>
                    </td>
                    <td className="num">{fmtMoney(r.stoplevel)}</td>
                    <td className="num">{r.risk_reward_ratio == null ? '—' : Number(r.risk_reward_ratio).toFixed(2)}</td>
                    <td className="num">
                      {r._sqs == null ? <span className="muted">—</span> : (
                        <span className={r._sqs >= 80 ? 'up' : r._sqs >= 60 ? '' : 'muted'}>
                          {Number(r._sqs).toFixed(0)}
                        </span>
                      )}
                    </td>
                    <td className="num">
                      {rsi == null ? <span className="muted">—</span> :
                        <span className={rsi > 70 ? 'down' : rsi < 30 ? 'up' : ''}>{rsi.toFixed(1)}</span>}
                    </td>
                    <td className="num">
                      {r.volume_surge_pct == null ? '—' : (
                        <span className={Number(r.volume_surge_pct) >= 0 ? 'up' : 'down'}>
                          {Number(r.volume_surge_pct) >= 0 ? '+' : ''}{Number(r.volume_surge_pct).toFixed(1)}%
                        </span>
                      )}
                    </td>
                    <td className="muted t-xs">{r.base_type ? `${r.base_type}` : '—'}</td>
                    <td>
                      {r.market_stage
                        ? <span className={`badge ${STAGE_VARIANT[r.market_stage] || 'badge'}`}>{r.market_stage.replace('Stage ', 'S')}</span>
                        : <span className="muted">—</span>}
                    </td>
                    <td>
                      {r._pass_gates == null ? <span className="muted t-2xs">—</span>
                        : r._pass_gates
                          ? <span className="badge badge-success">PASS{r._grade ? ` ${r._grade}` : ''}</span>
                          : <span className="badge badge-danger" title={r._fail_reason || ''}>FAIL</span>}
                    </td>
                    <td className="num muted t-xs">{r._age != null ? `${r._age}d` : '—'}</td>
                  </tr>
                  {expanded && (
                    <tr>
                      <td colSpan={13} style={{ background: 'var(--bg-2)', padding: 'var(--space-4)' }}>
                        <SignalDetail row={r} kind={kind} onSymbolClick={() => kind === 'stocks' && navigate(`/app/stock/${r.symbol}`)} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── row-expanded detail ───────────────────────────────────────────────────
function SignalDetail({ row, kind, onSymbolClick }) {
  return (
    <div>
      <div className="flex gap-3 items-center" style={{ marginBottom: 'var(--space-3)', flexWrap: 'wrap' }}>
        {kind === 'stocks' && (
          <button className="btn btn-outline btn-sm" onClick={onSymbolClick}>
            Open {row.symbol} detail →
          </button>
        )}
        {row._grade && <span className={`badge badge-lg ${row._grade.startsWith('A') ? 'badge-success' : row._grade === 'B' ? 'badge-cyan' : row._grade === 'C' ? 'badge-amber' : 'badge'}`}>Grade {row._grade}</span>}
        {row._pass_gates !== null && row._pass_gates !== undefined && (
          row._pass_gates
            ? <span className="badge badge-success">All gates pass</span>
            : <span className="badge badge-danger">Gate fail: {row._fail_reason || 'unknown'}</span>
        )}
      </div>

      {kind === 'stocks' && <PriceSparkline symbol={row.symbol} />}

      <div className="grid grid-3 gap-4" style={{ marginTop: 'var(--space-3)' }}>
        <DetailGroup title="Entry plan" items={[
          ['Buy zone', `${fmtMoney(row.buy_zone_start)} – ${fmtMoney(row.buy_zone_end)}`],
          ['Pivot', fmtMoney(row.pivot_price)],
          ['Initial stop', fmtMoney(row.initial_stop)],
          ['Trailing stop', fmtMoney(row.trailing_stop)],
          ['Position size', row.position_size_recommendation || '—'],
          ['Entry quality', row.entry_quality_score ? `${row.entry_quality_score}/100` : '—'],
        ]} />
        <DetailGroup title="Targets & exits" items={[
          ['Target T1 (+8%)', fmtMoney(row.profit_target_8pct)],
          ['Target T2 (+20%)', fmtMoney(row.profit_target_20pct)],
          ['Target T3 (+25%)', fmtMoney(row.profit_target_25pct)],
          ['Exit trigger 1', fmtMoney(row.exit_trigger_1_price)],
          ['Exit trigger 2', fmtMoney(row.exit_trigger_2_price)],
          ['Sell level', fmtMoney(row.sell_level)],
        ]} />
        <DetailGroup title="Technicals & strength" items={[
          ['RSI (14)', row.rsi != null ? Number(row.rsi).toFixed(1) : '—'],
          ['ADX', row.adx != null ? Number(row.adx).toFixed(1) : '—'],
          ['ATR', row.atr != null ? Number(row.atr).toFixed(2) : '—'],
          ['SMA 50 / 200', `${fmtMoney(row.sma_50)} / ${fmtMoney(row.sma_200)}`],
          ['EMA 21', fmtMoney(row.ema_21)],
          ['RS Rating', row.rs_rating != null ? Number(row.rs_rating).toFixed(0) : '—'],
          ['Mansfield RS', row.mansfield_rs != null ? Number(row.mansfield_rs).toFixed(2) : '—'],
          ['Avg vol 50d', fmtInt(row.avg_volume_50d)],
          ['Vol surge', row.volume_surge_pct != null ? fmtPct(row.volume_surge_pct) : '—'],
        ]} />
      </div>
    </div>
  );
}

// ─── inline sparkline ──────────────────────────────────────────────────────
function PriceSparkline({ symbol }) {
  const { data, isLoading } = useQuery({
    queryKey: ['sparkline', symbol],
    queryFn: () =>
      api.get(`/api/prices/history/${symbol}?timeframe=daily&limit=60`)
         .then(r => r.data?.data?.items || r.data?.items || []),
    staleTime: 300000,
  });

  if (isLoading) return <div className="muted t-xs">Loading chart…</div>;
  if (!data || data.length < 2) return <div className="muted t-xs">No price history available.</div>;

  const series = [...data]
    .map(d => ({ date: String(d.date).slice(0, 10), close: Number(d.close) }))
    .filter(d => !isNaN(d.close))
    .sort((a, b) => new Date(a.date) - new Date(b.date));

  const first = series[0]?.close ?? 0;
  const last = series[series.length - 1]?.close ?? 0;
  const change = first > 0 ? ((last - first) / first) * 100 : 0;
  const tone = change >= 0 ? 'var(--success)' : 'var(--danger)';

  return (
    <div className="panel" style={{ padding: 'var(--space-3) var(--space-4)' }}>
      <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
        <span className="eyebrow">{symbol} · last 60 days</span>
        <span className={`mono tnum t-xs ${change >= 0 ? 'up' : 'down'}`}>
          {change >= 0 ? '+' : ''}{change.toFixed(2)}%
        </span>
      </div>
      <div style={{ height: 90 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`sparkGrad-${symbol}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={tone} stopOpacity={0.4} />
                <stop offset="100%" stopColor={tone} stopOpacity={0} />
              </linearGradient>
            </defs>
            <Tooltip contentStyle={TOOLTIP_STYLE}
              formatter={(v) => [fmtMoney(v), 'Close']}
              labelFormatter={(d) => d} />
            <Area dataKey="close" type="monotone" stroke={tone} strokeWidth={1.5}
                  fill={`url(#sparkGrad-${symbol})`} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── detail group ──────────────────────────────────────────────────────────
function DetailGroup({ title, items }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 8 }}>{title}</div>
      <div className="flex flex-col" style={{ gap: 4 }}>
        {items.map(([label, value], i) => (
          <div key={i} className="flex" style={{ fontSize: 'var(--t-xs)' }}>
            <span className="muted" style={{ minWidth: 110 }}>{label}</span>
            <span className="strong mono tnum" style={{ flex: 1, textAlign: 'right' }}>{value || '—'}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── empty state ───────────────────────────────────────────────────────────
function Empty({ title, desc }) {
  return (
    <div className="empty">
      <Inbox />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
}
