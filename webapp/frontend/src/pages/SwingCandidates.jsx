/**
 * Swing Candidates — full-universe analytical workbench.
 *
 * Sections:
 *   - KPI strip
 *   - Top performers strip (top 5 A+ candidates with sparklines)
 *   - Score-component radar (selected vs. universe avg vs. top-10 avg)
 *   - Sector concentration treemap (top-50 candidates)
 *   - Grade distribution + pass-gate funnel
 *   - 7-component correlation matrix
 *   - History tab (A/A+ counts over time)
 *   - Enriched table with click-row navigation
 *
 * Pure JSX + theme.css. Recharts for charts.
 */

import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  RefreshCw, Search, Inbox, CheckCircle, XCircle,
  TrendingUp, Filter,
} from 'lucide-react';
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  Treemap, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, LineChart, Line, AreaChart, Area, Legend,
} from 'recharts';
import { api } from '../services/api';

const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

const GRADE_CLASS = {
  'A+': 'badge-success',
  'A':  'badge-success',
  'B':  'badge-cyan',
  'C':  'badge-amber',
  'D':  'badge',
  'F':  'badge-danger',
};

const COMPONENTS = [
  ['setup', 'Setup'],
  ['trend', 'Trend'],
  ['momentum', 'Momentum'],
  ['volume', 'Volume'],
  ['fundamentals', 'Fundamentals'],
  ['sector', 'Sector'],
  ['multi_tf', 'Multi-TF'],
];

export default function SwingCandidates() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [grade, setGrade] = useState('');
  const [sector, setSector] = useState('');
  const [gateFilter, setGateFilter] = useState('');
  const [minScore, setMinScore] = useState(0);
  const [selectedSym, setSelectedSym] = useState(null);

  const { data: items, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['swing-candidates', minScore],
    queryFn: () =>
      api.get(`/api/algo/swing-scores?limit=500&min_score=${minScore}`)
         .then(r => r.data?.items || []),
    refetchInterval: 60000,
  });

  const { data: history } = useQuery({
    queryKey: ['swing-history-30'],
    queryFn: () =>
      api.get('/api/algo/swing-scores-history?days=30')
         .then(r => r.data?.items || []),
    refetchInterval: 300000,
    retry: 1,
  });

  const sectors = useMemo(() => {
    if (!items) return [];
    return Array.from(new Set(items.map(i => i.sector).filter(Boolean))).sort();
  }, [items]);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = search.trim().toUpperCase();
    return items.filter(i => {
      if (q && !(i.symbol || '').toUpperCase().includes(q)) return false;
      if (grade && i.grade !== grade) return false;
      if (sector && i.sector !== sector) return false;
      if (gateFilter === 'pass' && !i.pass_gates) return false;
      if (gateFilter === 'fail' && i.pass_gates) return false;
      return true;
    });
  }, [items, search, grade, sector, gateFilter]);

  const stats = useMemo(() => {
    if (!items) return { total: 0, passing: 0, gradeA: 0, top10Score: 0 };
    const passing = items.filter(i => i.pass_gates).length;
    const gradeA = items.filter(i => i.grade === 'A' || i.grade === 'A+').length;
    const top10 = items.slice(0, 10);
    const top10Score = top10.length === 0 ? 0
      : top10.reduce((s, i) => s + (i.swing_score || 0), 0) / top10.length;
    return { total: items.length, passing, gradeA, top10Score };
  }, [items]);

  const topAplus = useMemo(() =>
    (items || []).filter(i => i.grade === 'A+').slice(0, 5),
    [items]);

  const selected = useMemo(() => {
    if (!selectedSym || !items) return null;
    return items.find(i => i.symbol === selectedSym) || null;
  }, [selectedSym, items]);

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Swing Candidates</div>
          <div className="page-head-sub">
            Full-universe research-weighted scoring · setup · trend · momentum · volume · fundamentals · sector · multi-TF
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-4">
        <Kpi label="Total Universe" value={stats.total.toLocaleString()} sub="ranked candidates" />
        <Kpi label="Pass All Gates" value={stats.passing.toLocaleString()}
             sub={`${stats.total ? Math.round(stats.passing / stats.total * 100) : 0}% qualify`}
             tone={stats.passing > 0 ? 'up' : ''} />
        <Kpi label="Grade A / A+" value={stats.gradeA.toLocaleString()}
             sub="institutional-quality" tone={stats.gradeA > 0 ? 'up' : ''} />
        <Kpi label="Top-10 Avg" value={`${num(stats.top10Score, 1)}/100`} sub="composite score" />
      </div>

      {/* Top A+ strip */}
      {topAplus.length > 0 && (
        <div className="card" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-head">
            <div>
              <div className="card-title">Top A+ Candidates</div>
              <div className="card-sub">5 highest-graded names with 60-day price action</div>
            </div>
          </div>
          <div className="card-body">
            <div className="grid grid-4" style={{ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' }}>
              {topAplus.map(c => (
                <TopCard key={c.symbol} c={c}
                  onClick={() => navigate(`/app/stock/${c.symbol}`)} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Charts row 1 — radar + sector treemap */}
      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <ComponentRadar items={items} selected={selected} />
        <SectorTreemap items={items} onSectorClick={(s) => setSector(s)} />
      </div>

      {/* Charts row 2 — funnel + correlation */}
      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <GradeFunnel items={items} />
        <ComponentCorrelation items={items} />
      </div>

      {/* History */}
      {history && history.length > 1 && (
        <div className="card" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-head">
            <div>
              <div className="card-title">A/A+ Grade Trend</div>
              <div className="card-sub">High-quality candidate count over the last 30 days</div>
            </div>
          </div>
          <div className="card-body" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="histGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--success)" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="var(--success)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="eval_date"
                  tickFormatter={(d) => String(d).slice(5, 10)}
                  stroke="var(--text-3)" fontSize={11} tickLine={false} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false} allowDecimals={false} width={32} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 'var(--t-xs)' }} />
                <Area type="monotone" dataKey="grade_aplus" name="A+"
                      stroke="var(--success)" strokeWidth={2} fill="url(#histGrad)" />
                <Line type="monotone" dataKey="grade_a" name="A" stroke="var(--cyan)" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="pass_count" name="Pass gates" stroke="var(--brand)" strokeWidth={1.5} strokeDasharray="3 3" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Filters bar */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body">
          <div className="flex items-center gap-3" style={{ flexWrap: 'wrap' }}>
            <div className="flex items-center gap-2" style={{ flex: '1 1 220px', minWidth: 200 }}>
              <Search size={14} className="muted" />
              <input
                className="input"
                placeholder="Search symbol…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ flex: 1 }}
              />
            </div>
            <select className="select" value={grade} onChange={e => setGrade(e.target.value)}>
              <option value="">All grades</option>
              <option value="A+">A+</option>
              <option value="A">A</option>
              <option value="B">B</option>
              <option value="C">C</option>
              <option value="D">D</option>
              <option value="F">F</option>
            </select>
            <select className="select" value={sector} onChange={e => setSector(e.target.value)}>
              <option value="">All sectors</option>
              {sectors.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select className="select" value={gateFilter} onChange={e => setGateFilter(e.target.value)}>
              <option value="">All gates</option>
              <option value="pass">Pass only</option>
              <option value="fail">Fail only</option>
            </select>
            <select className="select" value={minScore} onChange={e => setMinScore(Number(e.target.value))}>
              <option value="0">Score ≥ 0</option>
              <option value="40">Score ≥ 40</option>
              <option value="60">Score ≥ 60</option>
              <option value="75">Score ≥ 75</option>
              <option value="85">Score ≥ 85</option>
            </select>
            <span className="t-xs muted" style={{ marginLeft: 'auto' }}>
              <Filter size={12} style={{ verticalAlign: '-2px' }} /> {filtered.length} of {items?.length || 0}
            </span>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body" style={{ padding: 0 }}>
          {isLoading ? (
            <Empty title="Loading universe…" />
          ) : filtered.length === 0 ? (
            <Empty title="No candidates match filters"
                   desc="Loosen filters or wait for the next eval cycle." />
          ) : (
            <div style={{ overflow: 'auto', maxHeight: '70vh' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: 32 }} className="num">#</th>
                    <th>Symbol</th>
                    <th>Sector</th>
                    <th>Grade</th>
                    <th className="num">Score</th>
                    <th className="num">Setup</th>
                    <th className="num">Trend</th>
                    <th className="num">Mom</th>
                    <th className="num">Vol</th>
                    <th className="num">Fund</th>
                    <th className="num">Sector</th>
                    <th className="num">MTF</th>
                    <th>Gates</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((c, i) => (
                    <Row key={c.symbol} c={c} rank={i + 1}
                         active={selectedSym === c.symbol}
                         onClick={(e) => {
                           // single click: select for radar; double-click navigates
                           if (e.detail === 2) navigate(`/app/stock/${c.symbol}`);
                           else setSelectedSym(c.symbol);
                         }}
                         onNavigate={() => navigate(`/app/stock/${c.symbol}`)} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Component legend */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Score Components</div>
            <div className="card-sub">Click a row to update the radar · double-click to open detail</div>
          </div>
        </div>
        <div className="card-body">
          <div className="grid grid-4">
            <Legend1 name="Setup" desc="VCP / cup-with-handle / flat-base / pivot proximity" />
            <Legend1 name="Trend" desc="8-point trend template + market stage" />
            <Legend1 name="Momentum" desc="ADX / RSI sweet spot / multi-TF alignment" />
            <Legend1 name="Volume" desc="Pocket-pivot count / dry-up + breakout volume" />
            <Legend1 name="Fundamentals" desc="EPS / sales / margin growth + ROE filter" />
            <Legend1 name="Sector" desc="Relative Strength + sector rotation tier" />
            <Legend1 name="Multi-TF" desc="Daily + weekly + monthly alignment" />
            <Legend1 name="Gates" desc="Trend + SQS + advanced filters all pass" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── top A+ card with sparkline ────────────────────────────────────────────
function TopCard({ c, onClick }) {
  const { data } = useQuery({
    queryKey: ['spark', c.symbol],
    queryFn: () =>
      api.get(`/api/prices/history/${c.symbol}?timeframe=daily&limit=60`)
         .then(r => r.data?.data?.items || r.data?.items || []),
    staleTime: 600000,
  });

  const series = useMemo(() => {
    if (!data) return [];
    return [...data]
      .map(d => ({ date: String(d.date).slice(0, 10), close: Number(d.close) }))
      .filter(d => !isNaN(d.close))
      .sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [data]);

  const change = series.length >= 2
    ? ((series[series.length - 1].close - series[0].close) / series[0].close) * 100
    : 0;
  const tone = change >= 0 ? 'var(--success)' : 'var(--danger)';

  return (
    <div className="card card-hover" style={{ cursor: 'pointer', padding: 'var(--space-4)' }} onClick={onClick}>
      <div className="flex items-center justify-between" style={{ marginBottom: 6 }}>
        <span className="strong" style={{ fontWeight: 'var(--w-bold)' }}>{c.symbol}</span>
        <span className="badge badge-success">{c.grade}</span>
      </div>
      <div className="t-2xs muted" style={{ marginBottom: 8, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {c.sector || '—'}
      </div>
      <div style={{ height: 44, marginBottom: 6 }}>
        {series.length >= 2 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`tcg-${c.symbol}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={tone} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={tone} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area dataKey="close" type="monotone" stroke={tone} strokeWidth={1.4}
                    fill={`url(#tcg-${c.symbol})`} />
            </AreaChart>
          </ResponsiveContainer>
        ) : <div className="muted t-2xs">no price data</div>}
      </div>
      <div className="flex items-center justify-between">
        <span className="mono tnum t-xs strong">{num(c.swing_score, 1)}/100</span>
        <span className={`mono tnum t-xs ${change >= 0 ? 'up' : 'down'}`}>
          {change >= 0 ? '+' : ''}{change.toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

// ─── component radar ───────────────────────────────────────────────────────
function ComponentRadar({ items, selected }) {
  const data = useMemo(() => {
    if (!items || items.length === 0) return [];
    const universeAvg = {}, top10Avg = {};
    COMPONENTS.forEach(([k]) => { universeAvg[k] = 0; top10Avg[k] = 0; });
    items.forEach(i => {
      COMPONENTS.forEach(([k]) => {
        universeAvg[k] += Number(i.components?.[k] || 0);
      });
    });
    const top10 = items.slice(0, 10);
    top10.forEach(i => {
      COMPONENTS.forEach(([k]) => {
        top10Avg[k] += Number(i.components?.[k] || 0);
      });
    });
    return COMPONENTS.map(([k, lbl]) => {
      const sel = selected ? Number(selected.components?.[k] || 0) : null;
      return {
        component: lbl,
        Selected: sel,
        Universe: items.length ? universeAvg[k] / items.length : 0,
        'Top 10': top10.length ? top10Avg[k] / top10.length : 0,
      };
    });
  }, [items, selected]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Score Component Radar</div>
          <div className="card-sub">
            {selected ? `${selected.symbol} vs. universe avg vs. top-10 avg` : 'Click a row to compare a name against benchmarks'}
          </div>
        </div>
      </div>
      <div className="card-body">
        {data.length === 0 ? (
          <Empty title="No data" />
        ) : (
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={data} outerRadius="75%">
                <PolarGrid stroke="var(--border-soft)" />
                <PolarAngleAxis dataKey="component" stroke="var(--text-3)" fontSize={10} />
                <PolarRadiusAxis stroke="var(--text-3)" fontSize={9} angle={90} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v) => [Number(v).toFixed(1), '']} />
                {selected && (
                  <Radar name="Selected" dataKey="Selected"
                    stroke="var(--brand)" fill="var(--brand)" fillOpacity={0.4} />
                )}
                <Radar name="Top 10" dataKey="Top 10"
                  stroke="var(--success)" fill="var(--success)" fillOpacity={0.15} />
                <Radar name="Universe" dataKey="Universe"
                  stroke="var(--text-3)" fill="var(--text-3)" fillOpacity={0.10} />
                <Legend wrapperStyle={{ fontSize: 'var(--t-xs)' }} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── sector treemap ────────────────────────────────────────────────────────
function SectorTreemap({ items, onSectorClick }) {
  const data = useMemo(() => {
    if (!items) return [];
    const top50 = items.slice(0, 50);
    const buckets = {};
    top50.forEach(i => {
      const s = i.sector || 'Unknown';
      buckets[s] = (buckets[s] || 0) + 1;
    });
    return Object.entries(buckets)
      .map(([name, value]) => ({ name, size: value }))
      .sort((a, b) => b.size - a.size);
  }, [items]);

  const COLORS = ['var(--brand)', 'var(--cyan)', 'var(--purple)', 'var(--success)',
                  'var(--amber)', 'var(--brand-2)', 'var(--danger)', 'var(--text-3)'];

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Sector Concentration</div>
          <div className="card-sub">Top-50 candidates by sector · click to filter</div>
        </div>
      </div>
      <div className="card-body">
        {data.length === 0 ? (
          <Empty title="No sector data" />
        ) : (
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <Treemap data={data} dataKey="size" stroke="var(--surface)" fill="var(--brand)"
                content={<TreemapCell colors={COLORS} onClick={onSectorClick} />}>
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v, _, p) => [`${v} candidates`, p?.payload?.name || '']} />
              </Treemap>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

function TreemapCell({ x, y, width, height, name, size, colors, onClick, index }) {
  if (width < 1 || height < 1) return null;
  const fill = colors[(index || 0) % colors.length];
  return (
    <g style={{ cursor: 'pointer' }} onClick={() => onClick && onClick(name)}>
      <rect x={x} y={y} width={width} height={height} fill={fill} fillOpacity={0.6}
        stroke="var(--surface)" strokeWidth={2} />
      {width > 60 && height > 30 && (
        <>
          <text x={x + 6} y={y + 16} fill="var(--text)" fontSize={11}
            fontWeight="600" style={{ pointerEvents: 'none' }}>
            {name && name.length > 18 ? name.slice(0, 16) + '…' : name}
          </text>
          <text x={x + 6} y={y + 32} fill="var(--text-2)" fontSize={10}
            style={{ pointerEvents: 'none' }}>
            {size}
          </text>
        </>
      )}
    </g>
  );
}

// ─── grade distribution + funnel ───────────────────────────────────────────
function GradeFunnel({ items }) {
  const data = useMemo(() => {
    if (!items) return { grades: [], funnel: [] };
    const order = ['A+', 'A', 'B', 'C', 'D', 'F'];
    const grades = order.map(g => ({
      grade: g,
      count: items.filter(i => i.grade === g).length,
    }));

    // Build pass-gate funnel (uses fail_reason buckets when available)
    const total = items.length;
    const buckets = {
      'Universe': total,
      'Has data': items.filter(i => i.swing_score != null).length,
      'Score ≥ 40': items.filter(i => Number(i.swing_score) >= 40).length,
      'Score ≥ 60': items.filter(i => Number(i.swing_score) >= 60).length,
      'Grade B+': items.filter(i => ['B', 'A', 'A+'].includes(i.grade)).length,
      'Pass gates': items.filter(i => i.pass_gates).length,
    };
    const funnel = Object.entries(buckets).map(([stage, count]) => ({ stage, count }));
    return { grades, funnel };
  }, [items]);

  const GRADE_COLORS = {
    'A+': 'var(--success)', 'A': 'var(--success)', 'B': 'var(--cyan)',
    'C': 'var(--amber)', 'D': 'var(--text-3)', 'F': 'var(--danger)',
  };

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Grade Distribution + Pass-Gate Funnel</div>
          <div className="card-sub">How the universe filters down to tradable candidates</div>
        </div>
      </div>
      <div className="card-body">
        {data.grades.length === 0 ? (
          <Empty title="No data" />
        ) : (
          <>
            <div style={{ height: 110 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.grades} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                  <XAxis dataKey="grade" stroke="var(--text-3)" fontSize={11} tickLine={false} />
                  <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false} allowDecimals={false} width={32} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'var(--surface-2)' }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {data.grades.map((g, i) =>
                      <Cell key={i} fill={GRADE_COLORS[g.grade]} fillOpacity={0.8} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="eyebrow" style={{ marginTop: 12, marginBottom: 6 }}>Funnel</div>
            <div className="flex flex-col" style={{ gap: 4 }}>
              {data.funnel.map((f, i) => {
                const pct = data.funnel[0].count > 0 ? (f.count / data.funnel[0].count) * 100 : 0;
                return (
                  <div key={i}>
                    <div className="flex justify-between" style={{ fontSize: 'var(--t-xs)', marginBottom: 2 }}>
                      <span className="muted">{f.stage}</span>
                      <span className="mono tnum strong">{f.count}</span>
                    </div>
                    <div className="bar">
                      <div className={`bar-fill ${i >= 4 ? 'success' : ''}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── component correlation matrix ──────────────────────────────────────────
function ComponentCorrelation({ items }) {
  const matrix = useMemo(() => {
    if (!items || items.length < 5) return null;
    // Build columns of values
    const cols = {};
    COMPONENTS.forEach(([k]) => cols[k] = []);
    items.forEach(i => {
      COMPONENTS.forEach(([k]) => cols[k].push(Number(i.components?.[k] || 0)));
    });
    const mean = (a) => a.reduce((s, x) => s + x, 0) / a.length;
    const std = (a, m) => Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / a.length);
    const means = {}, stds = {};
    COMPONENTS.forEach(([k]) => { means[k] = mean(cols[k]); stds[k] = std(cols[k], means[k]); });

    const cells = [];
    COMPONENTS.forEach(([ka, la], rowIdx) => {
      COMPONENTS.forEach(([kb, lb], colIdx) => {
        let r = 0;
        if (stds[ka] > 0 && stds[kb] > 0) {
          let cov = 0;
          for (let i = 0; i < cols[ka].length; i++) {
            cov += (cols[ka][i] - means[ka]) * (cols[kb][i] - means[kb]);
          }
          cov /= cols[ka].length;
          r = cov / (stds[ka] * stds[kb]);
        }
        cells.push({ rowIdx, colIdx, ka: la, kb: lb, r });
      });
    });
    return cells;
  }, [items]);

  if (!matrix) {
    return (
      <div className="card">
        <div className="card-head"><div><div className="card-title">Component Correlation Matrix</div></div></div>
        <div className="card-body"><Empty title="Need ≥5 candidates for correlation" /></div>
      </div>
    );
  }

  const shade = (r) => {
    // -1 → red, 0 → neutral, +1 → success
    if (r > 0) return `rgba(34, 197, 94, ${Math.abs(r) * 0.7 + 0.05})`;
    if (r < 0) return `rgba(239, 68, 68, ${Math.abs(r) * 0.7 + 0.05})`;
    return 'transparent';
  };

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Component Correlation Matrix</div>
          <div className="card-sub">Pearson r between the 7 score components</div>
        </div>
      </div>
      <div className="card-body" style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 'var(--t-2xs)', width: '100%' }}>
          <thead>
            <tr>
              <th style={{ padding: 4 }} />
              {COMPONENTS.map(([_, l]) => (
                <th key={l} style={{ padding: 4, color: 'var(--text-muted)', fontWeight: 'var(--w-medium)' }}>
                  {l.slice(0, 5)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {COMPONENTS.map(([_, la], rIdx) => (
              <tr key={la}>
                <td style={{ padding: 4, color: 'var(--text-muted)', fontWeight: 'var(--w-medium)' }}>
                  {la}
                </td>
                {COMPONENTS.map(([__, lb], cIdx) => {
                  const cell = matrix.find(m => m.rowIdx === rIdx && m.colIdx === cIdx);
                  const r = cell?.r ?? 0;
                  return (
                    <td key={lb} title={`${la} × ${lb} = ${r.toFixed(2)}`}
                      style={{
                        padding: '8px 4px',
                        textAlign: 'center',
                        background: shade(r),
                        border: '1px solid var(--border-soft)',
                        fontFamily: 'var(--font-mono)',
                        fontVariantNumeric: 'tabular-nums',
                        color: Math.abs(r) > 0.5 ? 'var(--text)' : 'var(--text-2)',
                      }}>
                      {r.toFixed(2)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── row ───────────────────────────────────────────────────────────────────
function Row({ c, rank, active, onClick, onNavigate }) {
  const cmp = c.components || {};
  return (
    <tr onClick={onClick}
        style={{
          cursor: 'pointer',
          background: active ? 'var(--brand-soft)' : undefined,
        }}>
      <td className="num mono tnum muted">{rank}</td>
      <td>
        <span className="strong" style={{ fontWeight: 'var(--w-semibold)' }}>{c.symbol}</span>
      </td>
      <td className="t-xs muted" style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {c.sector || '—'}
      </td>
      <td>
        <span className={`badge ${GRADE_CLASS[c.grade] || 'badge'}`}>{c.grade || '—'}</span>
      </td>
      <td className="num mono tnum" style={{ fontWeight: 'var(--w-semibold)' }}>
        {num(c.swing_score, 1)}
      </td>
      <td className="num mono tnum t-xs">{num(cmp.setup, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.trend, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.momentum, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.volume, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.fundamentals, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.sector, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.multi_tf, 1)}</td>
      <td>
        {c.pass_gates ? (
          <span className="badge badge-success">
            <CheckCircle size={11} style={{ verticalAlign: '-2px' }} /> PASS
          </span>
        ) : (
          <span className="badge badge-danger" title={c.fail_reason || ''}>
            <XCircle size={11} style={{ verticalAlign: '-2px' }} /> {c.fail_reason ? c.fail_reason.slice(0, 18) : 'FAIL'}
          </span>
        )}
      </td>
    </tr>
  );
}

// ─── small ─────────────────────────────────────────────────────────────────
function Kpi({ label, value, sub, tone }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="flex items-center justify-between">
        <div className="eyebrow">{label}</div>
        <TrendingUp size={16} className="muted" />
      </div>
      <div className={`mono ${tone || ''}`}
           style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
        {value}
      </div>
      {sub && <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>{sub}</div>}
    </div>
  );
}

function Legend1({ name, desc }) {
  return (
    <div className="stile">
      <div className="stile-label">{name}</div>
      <div className="t-xs muted" style={{ marginTop: 4 }}>{desc}</div>
    </div>
  );
}

function Empty({ title, desc }) {
  return (
    <div className="empty">
      <Inbox size={36} />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
}
