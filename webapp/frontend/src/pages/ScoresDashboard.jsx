import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  RefreshCw, Search, Filter, Inbox, ChevronLeft, ChevronRight,
  Star, Activity, DollarSign, TrendingUp, Users, Shield, Layers,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer, Cell, LabelList,
  LineChart, Line,
} from 'recharts';
import { api } from '../services/api';

const num = (v, dp = 1) => (v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp));
const pct = (v, dp = 2) => (v == null || isNaN(Number(v)) ? '—' : `${Number(v).toFixed(dp)}%`);
const money = (v) => {
  if (v == null || isNaN(Number(v))) return '—';
  const n = Number(v);
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toFixed(2)}`;
};

const scoreClass = (v) => {
  if (v == null || isNaN(Number(v))) return 'badge';
  const n = Number(v);
  if (n >= 80) return 'badge-success';
  if (n >= 60) return 'badge-cyan';
  if (n >= 40) return 'badge-amber';
  return 'badge-danger';
};

const scoreColor = (v) => {
  if (v == null || isNaN(Number(v))) return 'var(--text-faint)';
  const n = Number(v);
  if (n >= 80) return 'var(--success)';
  if (n >= 60) return 'var(--cyan)';
  if (n >= 40) return 'var(--amber)';
  return 'var(--danger)';
};

const grade = (v) => {
  if (v == null) return '—';
  const n = Number(v);
  if (n >= 90) return 'A+';
  if (n >= 85) return 'A';
  if (n >= 80) return 'A-';
  if (n >= 75) return 'B+';
  if (n >= 70) return 'B';
  if (n >= 65) return 'B-';
  if (n >= 60) return 'C+';
  if (n >= 55) return 'C';
  if (n >= 50) return 'C-';
  if (n >= 45) return 'D+';
  if (n >= 40) return 'D';
  return 'F';
};

const SORT_FIELDS = [
  { value: 'composite_score',   label: 'Composite' },
  { value: 'momentum_score',    label: 'Momentum' },
  { value: 'quality_score',     label: 'Quality' },
  { value: 'value_score',       label: 'Value' },
  { value: 'growth_score',      label: 'Growth' },
  { value: 'positioning_score', label: 'Positioning' },
  { value: 'stability_score',   label: 'Stability' },
];

const FACTORS = [
  { key: 'quality',     label: 'Quality',     scoreKey: 'quality_score',     icon: Star,        tone: 'var(--brand)' },
  { key: 'momentum',    label: 'Momentum',    scoreKey: 'momentum_score',    icon: Activity,    tone: 'var(--amber)' },
  { key: 'value',       label: 'Value',       scoreKey: 'value_score',       icon: DollarSign,  tone: 'var(--cyan)' },
  { key: 'growth',      label: 'Growth',      scoreKey: 'growth_score',      icon: TrendingUp,  tone: 'var(--success)' },
  { key: 'positioning', label: 'Positioning', scoreKey: 'positioning_score', icon: Users,       tone: 'var(--purple)' },
  { key: 'stability',   label: 'Stability',   scoreKey: 'stability_score',   icon: Shield,      tone: 'var(--text-2)' },
];

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
  color: 'var(--text)',
};

export default function ScoresDashboard() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [sector, setSector] = useState('');
  const [sortBy, setSortBy] = useState('composite_score');
  const [sortOrder, setSortOrder] = useState('desc');
  const [minScore, setMinScore] = useState(0);
  const [tab, setTab] = useState('rankings');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [details, setDetails] = useState({});

  const { data: items, isLoading, refetch } = useQuery({
    queryKey: ['stock-scores'],
    queryFn: () =>
      api.get('/api/scores/stockscores?limit=5000&offset=0&sortBy=composite_score&sp500Only=true')
         .then(r => r.data?.items || []),
    refetchInterval: 60000,
  });

  useEffect(() => { setPage(1); }, [search, sector, sortBy, sortOrder, minScore]);

  const sectors = useMemo(() => {
    if (!items) return [];
    return Array.from(new Set(items.map(i => i.sector).filter(Boolean))).sort();
  }, [items]);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = search.trim().toUpperCase();
    const arr = items.filter(s => {
      if (q && !(s.symbol || '').toUpperCase().includes(q)) return false;
      if (sector && s.sector !== sector) return false;
      if (minScore > 0) {
        const v = s[sortBy];
        if (v == null || Number(v) < minScore) return false;
      }
      return true;
    });
    arr.sort((a, b) => {
      const av = a[sortBy], bv = b[sortBy];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return sortOrder === 'desc' ? Number(bv) - Number(av) : Number(av) - Number(bv);
    });
    return arr;
  }, [items, search, sector, sortBy, sortOrder, minScore]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageStart = (page - 1) * pageSize;
  const pageEnd = pageStart + pageSize;
  const pageRows = filtered.slice(pageStart, pageEnd);

  const stats = useMemo(() => {
    if (!items) return { total: 0, top: 0, avg: 0, gradeA: 0 };
    const top = items.filter(s => Number(s.composite_score) >= 80).length;
    const valid = items.filter(s => s.composite_score != null);
    const avg = valid.length ? valid.reduce((s, x) => s + Number(x.composite_score), 0) / valid.length : 0;
    const gradeA = items.filter(s => Number(s.composite_score) >= 80).length;
    return { total: items.length, top, avg, gradeA };
  }, [items]);

  const marketAvgs = useMemo(() => {
    const o = {};
    FACTORS.forEach(f => {
      const vals = (items || []).map(s => s[f.scoreKey]).filter(v => v != null).map(Number);
      o[f.key] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    });
    return o;
  }, [items]);

  const sectorAvgs = (sym) => {
    if (!items || !sym) return {};
    const stock = items.find(s => s.symbol === sym);
    if (!stock?.sector) return {};
    const peers = items.filter(s => s.sector === stock.sector);
    const o = {};
    FACTORS.forEach(f => {
      const vals = peers.map(s => s[f.scoreKey]).filter(v => v != null).map(Number);
      o[f.key] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    });
    return o;
  };

  const expandStock = async (symbol) => {
    if (selectedSymbol === symbol) { setSelectedSymbol(null); return; }
    setSelectedSymbol(symbol);
    if (!details[symbol]) {
      try {
        const r = await api.get(`/api/scores/stockscores?symbol=${symbol}&limit=1`);
        const item = r.data?.items?.[0];
        if (item) {
          setDetails(d => ({ ...d, [symbol]: item }));
        } else {
          console.warn(`[ScoresDashboard] No detail item returned for ${symbol}`, r.data);
        }
      } catch (err) {
        console.error(`[ScoresDashboard] Failed to load detail for ${symbol}:`, err?.message || err);
      }
    }
  };

  const clear = () => {
    setSearch(''); setSector(''); setSortBy('composite_score');
    setSortOrder('desc'); setMinScore(0);
  };

  const detailStock = selectedSymbol
    ? (details[selectedSymbol] || (items || []).find(s => s.symbol === selectedSymbol))
    : null;

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Scores</div>
          <div className="page-head-sub">
            Multi-factor stock scoring · composite + 6 factors · S&amp;P 500 universe · click row for full factor breakdown
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={() => refetch()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-4">
        <Kpi label="Universe" value={stats.total.toLocaleString()} sub="ranked stocks" />
        <Kpi label="Composite ≥ 80" value={stats.top.toLocaleString()}
             sub={`${stats.total ? Math.round(stats.top / stats.total * 100) : 0}% qualify`}
             tone={stats.top > 0 ? 'up' : ''} />
        <Kpi label="Market Avg" value={num(stats.avg, 1)} sub="composite score" />
        <Kpi label="Top Decile" value={num(filtered[0]?.composite_score, 1)}
             sub={filtered[0]?.symbol || '—'} tone="up" />
      </div>

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
            <select className="select" value={sortBy} onChange={e => setSortBy(e.target.value)}>
              {SORT_FIELDS.map(f => <option key={f.value} value={f.value}>Sort: {f.label}</option>)}
            </select>
            <select className="select" value={sortOrder} onChange={e => setSortOrder(e.target.value)}>
              <option value="desc">High → Low</option>
              <option value="asc">Low → High</option>
            </select>
            <select className="select" value={sector} onChange={e => setSector(e.target.value)}>
              <option value="">All sectors</option>
              {sectors.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select className="select" value={minScore} onChange={e => setMinScore(Number(e.target.value))}>
              <option value="0">Min score: any</option>
              <option value="50">≥ 50</option>
              <option value="60">≥ 60</option>
              <option value="70">≥ 70</option>
              <option value="80">≥ 80</option>
              <option value="90">≥ 90</option>
            </select>
            <button className="btn btn-ghost btn-sm" onClick={clear}>Clear</button>
            <span className="t-xs muted" style={{ marginLeft: 'auto' }}>
              <Filter size={12} style={{ verticalAlign: '-2px' }} /> {filtered.length} of {items?.length || 0}
            </span>
          </div>
        </div>
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: 'rankings',     label: 'Rankings' },
          { value: 'movers',       label: 'Top Movers' },
          { value: 'leaderboard',  label: 'A-Grade ≥ 80' },
          { value: 'heatmap',      label: 'Factor Heatmap' },
          { value: 'distribution', label: 'Distributions' },
          { value: 'correlation',  label: 'Correlations' },
          { value: 'leaders',      label: 'Category Leaders' },
          { value: 'laggards',     label: 'Laggards' },
          { value: 'sectors',      label: 'By Sector' },
        ]}
      />

      {tab === 'rankings' && (
        <RankingsTab
          rows={pageRows}
          all={items || []}
          isLoading={isLoading}
          page={page} setPage={setPage}
          pageSize={pageSize} setPageSize={setPageSize}
          totalPages={totalPages} totalRows={filtered.length}
          pageStart={pageStart} pageEnd={pageEnd}
          selectedSymbol={selectedSymbol}
          onExpand={expandStock}
          onNavigate={(s) => navigate(`/app/stock/${s}`)}
          detail={detailStock}
          marketAvgs={marketAvgs}
          sectorAvgs={selectedSymbol ? sectorAvgs(selectedSymbol) : {}}
        />
      )}

      {tab === 'movers' && (
        <MoversTab items={items || []} onClick={(s) => navigate(`/app/stock/${s}`)} />
      )}

      {tab === 'leaderboard' && (
        <LeaderboardTab items={items || []} sectorFilter={sector} onClick={(s) => navigate(`/app/stock/${s}`)} />
      )}

      {tab === 'heatmap' && (
        <HeatmapTab items={items || []} sectorFilter={sector} onClick={(s) => navigate(`/app/stock/${s}`)} />
      )}

      {tab === 'distribution' && (
        <DistributionTab items={items || []} />
      )}

      {tab === 'correlation' && (
        <CorrelationTab items={items || []} />
      )}

      {tab === 'leaders' && (
        <LeadersTab items={items || []} sectorFilter={sector} onClick={(s) => navigate(`/app/stock/${s}`)} />
      )}

      {tab === 'laggards' && (
        <LaggardsTab items={items || []} sectorFilter={sector} onClick={(s) => navigate(`/app/stock/${s}`)} />
      )}

      {tab === 'sectors' && (
        <SectorsTab items={items || []} sectors={sectors} onClick={(s) => navigate(`/app/stock/${s}`)} />
      )}

      <ScoreLegend />
    </div>
  );
}

// ─── tabs: rankings ────────────────────────────────────────────────────────
function RankingsTab({
  rows, isLoading, page, setPage, pageSize, setPageSize,
  totalPages, totalRows, pageStart, pageEnd,
  selectedSymbol, onExpand, onNavigate, detail, marketAvgs, sectorAvgs,
}) {
  if (isLoading) {
    return (
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body"><Empty title="Loading scores…" /></div>
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body">
          <Empty title="No stocks match your filters" desc="Try widening filters or refreshing the universe." />
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body" style={{ padding: 0 }}>
          <div style={{ overflow: 'auto', maxHeight: '70vh' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: 32 }} className="num">#</th>
                  <th>Symbol</th>
                  <th>Sector</th>
                  <th className="num">Composite</th>
                  <th>Grade</th>
                  <th className="num">Quality</th>
                  <th className="num">Mom</th>
                  <th className="num">Value</th>
                  <th className="num">Growth</th>
                  <th className="num">Pos</th>
                  <th className="num">Stab</th>
                  <th className="num">Price</th>
                  <th className="num">Δ</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s, i) => (
                  <tr
                    key={s.symbol}
                    onClick={() => onExpand(s.symbol)}
                    style={{
                      cursor: 'pointer',
                      background: selectedSymbol === s.symbol ? 'var(--surface-2)' : undefined,
                    }}
                  >
                    <td className="num mono tnum muted">{pageStart + i + 1}</td>
                    <td>
                      <span
                        style={{ fontWeight: 'var(--w-semibold)', cursor: 'pointer' }}
                        onClick={(e) => { e.stopPropagation(); onNavigate(s.symbol); }}
                      >
                        {s.symbol}
                      </span>
                      {s.company_name && (
                        <div className="t-xs muted" style={{
                          maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>
                          {s.company_name}
                        </div>
                      )}
                    </td>
                    <td className="t-xs muted" style={{
                      maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {s.sector || '—'}
                    </td>
                    <td className="num mono tnum" style={{ fontWeight: 'var(--w-semibold)' }}>
                      <span className={`badge ${scoreClass(s.composite_score)}`}>
                        {num(s.composite_score, 1)}
                      </span>
                    </td>
                    <td>
                      <span className="t-xs mono" style={{ color: scoreColor(s.composite_score), fontWeight: 'var(--w-semibold)' }}>
                        {grade(s.composite_score)}
                      </span>
                    </td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.quality_score) }}>{num(s.quality_score, 0)}</td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.momentum_score) }}>{num(s.momentum_score, 0)}</td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.value_score) }}>{num(s.value_score, 0)}</td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.growth_score) }}>{num(s.growth_score, 0)}</td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.positioning_score) }}>{num(s.positioning_score, 0)}</td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.stability_score) }}>{num(s.stability_score, 0)}</td>
                    <td className="num mono tnum t-xs">{s.price != null ? `$${num(s.price, 2)}` : '—'}</td>
                    <td className={`num mono tnum t-xs ${Number(s.change_percent) >= 0 ? 'up' : 'down'}`}>
                      {s.change_percent != null ? `${Number(s.change_percent) >= 0 ? '+' : ''}${num(s.change_percent, 2)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3" style={{
        marginTop: 'var(--space-3)', flexWrap: 'wrap', justifyContent: 'flex-end',
      }}>
        <span className="t-xs muted">
          {pageStart + 1}–{Math.min(pageEnd, totalRows)} of {totalRows.toLocaleString()}
        </span>
        <select className="select" value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}>
          <option value="25">25 / page</option>
          <option value="50">50 / page</option>
          <option value="100">100 / page</option>
          <option value="250">250 / page</option>
        </select>
        <button className="btn btn-ghost btn-icon" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
          <ChevronLeft size={14} />
        </button>
        <span className="t-xs mono">{page} / {totalPages}</span>
        <button className="btn btn-ghost btn-icon" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
          <ChevronRight size={14} />
        </button>
      </div>

      {detail && (
        <FactorDetail
          stock={detail}
          marketAvgs={marketAvgs}
          sectorAvgs={sectorAvgs}
          onNavigate={onNavigate}
          onClose={() => onExpand(detail.symbol)}
        />
      )}
    </>
  );
}

// ─── factor detail (expanded) ──────────────────────────────────────────────
function FactorDetail({ stock, marketAvgs, sectorAvgs, onNavigate, onClose }) {
  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">
            {stock.symbol}
            {stock.company_name && (
              <span className="t-sm muted" style={{ fontWeight: 'var(--w-medium)', marginLeft: 'var(--space-2)' }}>
                · {stock.company_name}
              </span>
            )}
          </div>
          <div className="card-sub">
            {stock.sector || '—'} · composite {num(stock.composite_score, 1)} · grade {grade(stock.composite_score)}
            {stock.last_updated && ` · updated ${new Date(stock.last_updated).toLocaleDateString()}`}
          </div>
        </div>
        <div className="card-actions">
          <button className="btn btn-outline btn-sm" onClick={() => onNavigate(stock.symbol)}>
            Open Stock →
          </button>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>Close</button>
        </div>
      </div>
      <div className="card-body">
        <div className="grid grid-3">
          {FACTORS.map(f => (
            <FactorScoreCard
              key={f.key}
              factor={f}
              stockScore={stock[f.scoreKey]}
              sectorAvg={sectorAvgs[f.key]}
              marketAvg={marketAvgs[f.key]}
              symbol={stock.symbol}
              sectorLabel={stock.sector || 'Sector'}
            />
          ))}
        </div>

        <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
          <FactorInputs title="Quality & Fundamentals" inputs={stock.quality_inputs} schema={QUALITY_SCHEMA} />
          <FactorInputs title="Momentum" inputs={stock.momentum_inputs} schema={MOMENTUM_SCHEMA} />
          <FactorInputs title="Value" inputs={stock.value_inputs} schema={VALUE_SCHEMA} />
          <FactorInputs title="Growth" inputs={stock.growth_inputs} schema={GROWTH_SCHEMA} />
          <FactorInputs title="Positioning" inputs={stock.positioning_inputs} schema={POSITIONING_SCHEMA} />
          <FactorInputs title="Stability" inputs={stock.stability_inputs} schema={STABILITY_SCHEMA} />
        </div>
      </div>
    </div>
  );
}

function FactorScoreCard({ factor, stockScore, sectorAvg, marketAvg, symbol, sectorLabel }) {
  const Icon = factor.icon;
  const data = [
    { name: symbol, value: stockScore != null ? Number(stockScore) : null, fill: factor.tone },
    { name: `${sectorLabel.slice(0, 12)} avg`, value: sectorAvg != null ? Number(sectorAvg) : null, fill: 'var(--cyan)' },
    { name: 'Market avg', value: marketAvg != null ? Number(marketAvg) : null, fill: 'var(--text-3)' },
  ].filter(d => d.value != null);

  return (
    <div className="card" style={{ background: 'var(--surface-2)' }}>
      <div className="card-body">
        <div className="flex items-center gap-2" style={{ marginBottom: 'var(--space-3)' }}>
          <Icon size={16} style={{ color: factor.tone }} />
          <div style={{ fontWeight: 'var(--w-semibold)' }}>{factor.label}</div>
          <span className={`badge ${scoreClass(stockScore)}`} style={{ marginLeft: 'auto' }}>
            {num(stockScore, 1)}
          </span>
        </div>
        {data.length > 0 ? (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={data} margin={{ top: 16, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: 'var(--text-3)', fontSize: 10 }} />
              <YAxis domain={[0, 100]} tick={{ fill: 'var(--text-3)', fontSize: 10 }} />
              <RTooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => num(v, 1)} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {data.map((d, i) => <Cell key={i} fill={d.fill} />)}
                <LabelList dataKey="value" position="top"
                           style={{ fontSize: 10, fontWeight: 600, fill: 'var(--text-2)' }}
                           formatter={(v) => num(v, 1)} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="t-xs muted" style={{ padding: 'var(--space-3)' }}>No comparison data</div>
        )}
      </div>
    </div>
  );
}

function FactorInputs({ title, inputs, schema }) {
  if (!inputs || typeof inputs !== 'object') {
    return (
      <div className="card">
        <div className="card-head"><div className="card-title">{title}</div></div>
        <div className="card-body"><div className="t-xs muted">No detailed metrics available</div></div>
      </div>
    );
  }
  const rows = schema
    .map(s => ({ ...s, value: inputs[s.key] }))
    .filter(r => r.value != null);
  if (rows.length === 0) {
    return (
      <div className="card">
        <div className="card-head"><div className="card-title">{title}</div></div>
        <div className="card-body"><div className="t-xs muted">No detailed metrics available</div></div>
      </div>
    );
  }
  return (
    <div className="card">
      <div className="card-head"><div className="card-title">{title}</div></div>
      <div className="card-body" style={{ padding: 0 }}>
        <table className="data-table">
          <tbody>
            {rows.map(r => (
              <tr key={r.key}>
                <td className="t-xs">{r.label}</td>
                <td className="num mono tnum t-xs">{r.fmt(r.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── tabs: leaders/laggards/sectors ────────────────────────────────────────
function LeadersTab({ items, sectorFilter, onClick }) {
  return (
    <div className="grid grid-3" style={{ marginTop: 'var(--space-4)' }}>
      {FACTORS.map(f => (
        <CategoryTable
          key={f.key}
          factor={f}
          rows={topBy(items, f.scoreKey, 10, sectorFilter, 'desc')}
          mode="leaders"
          onClick={onClick}
        />
      ))}
    </div>
  );
}

function LaggardsTab({ items, sectorFilter, onClick }) {
  return (
    <div className="grid grid-3" style={{ marginTop: 'var(--space-4)' }}>
      {FACTORS.map(f => (
        <CategoryTable
          key={f.key}
          factor={f}
          rows={topBy(items, f.scoreKey, 10, sectorFilter, 'asc')}
          mode="laggards"
          onClick={onClick}
        />
      ))}
    </div>
  );
}

function CategoryTable({ factor, rows, mode, onClick }) {
  const Icon = factor.icon;
  return (
    <div className="card">
      <div className="card-head">
        <div className="flex items-center gap-2">
          <Icon size={16} style={{ color: mode === 'laggards' ? 'var(--danger)' : factor.tone }} />
          <div className="card-title">{factor.label} {mode === 'laggards' ? 'Laggards' : 'Leaders'}</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {rows.length === 0 ? (
          <div className="empty" style={{ padding: 'var(--space-5)' }}>
            <Inbox size={28} />
            <div className="empty-title">No data</div>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 32 }} className="num">#</th>
                <th>Symbol</th>
                <th className="num">Score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s, i) => (
                <tr key={s.symbol} onClick={() => onClick(s.symbol)}>
                  <td className="num mono tnum muted">{i + 1}</td>
                  <td style={{ fontWeight: 'var(--w-semibold)' }}>{s.symbol}</td>
                  <td className="num">
                    <span className={`badge ${mode === 'laggards' ? 'badge-danger' : scoreClass(s[factor.scoreKey])}`}>
                      {num(s[factor.scoreKey], 1)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function SectorsTab({ items, sectors, onClick }) {
  if (sectors.length === 0) {
    return (
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body"><Empty title="No sector data" /></div>
      </div>
    );
  }
  return (
    <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
      {sectors.map(sec => {
        const rows = items
          .filter(s => s.sector === sec && s.composite_score != null)
          .sort((a, b) => Number(b.composite_score) - Number(a.composite_score))
          .slice(0, 8);
        return (
          <div className="card" key={sec}>
            <div className="card-head">
              <div className="flex items-center gap-2">
                <Layers size={16} style={{ color: 'var(--brand)' }} />
                <div className="card-title">{sec}</div>
                <span className="badge" style={{ marginLeft: 'auto' }}>{rows.length}</span>
              </div>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: 32 }} className="num">#</th>
                    <th>Symbol</th>
                    <th className="num">Composite</th>
                    <th>Grade</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s, i) => (
                    <tr key={s.symbol} onClick={() => onClick(s.symbol)}>
                      <td className="num mono tnum muted">{i + 1}</td>
                      <td style={{ fontWeight: 'var(--w-semibold)' }}>{s.symbol}</td>
                      <td className="num">
                        <span className={`badge ${scoreClass(s.composite_score)}`}>
                          {num(s.composite_score, 1)}
                        </span>
                      </td>
                      <td className="t-xs mono" style={{ color: scoreColor(s.composite_score), fontWeight: 'var(--w-semibold)' }}>
                        {grade(s.composite_score)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── tab: top movers ───────────────────────────────────────────────────────
function MoversTab({ items, onClick }) {
  // Without historical score data, derive proxy "movers" from price change_percent.
  // Two side-by-side cards: composite leaders vs composite laggards (by score),
  // and price-change gainers vs decliners. This is a real-data proxy view.
  const valid = items.filter((s) => s.composite_score != null);
  const topComposite  = [...valid].sort((a, b) => Number(b.composite_score) - Number(a.composite_score)).slice(0, 10);
  const botComposite  = [...valid].sort((a, b) => Number(a.composite_score) - Number(b.composite_score)).slice(0, 10);
  const validPx = items.filter((s) => s.change_percent != null);
  const gainers = [...validPx].sort((a, b) => Number(b.change_percent) - Number(a.change_percent)).slice(0, 10);
  const decliners = [...validPx].sort((a, b) => Number(a.change_percent) - Number(b.change_percent)).slice(0, 10);

  return (
    <>
      <div className="alert alert-info" style={{ marginTop: 'var(--space-4)' }}>
        <Activity size={16} />
        <div>
          Score-history is a snapshot table — these cards show <strong>composite leaders / laggards</strong>{' '}
          and <strong>1-day price gainers / decliners</strong> across the universe (proxy for momentum movers).
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <MoverCard title="Top Composite Leaders" rows={topComposite} field="composite_score" tone="up"   onClick={onClick} fmt={(v) => num(v, 1)} />
        <MoverCard title="Top Composite Laggards" rows={botComposite} field="composite_score" tone="down" onClick={onClick} fmt={(v) => num(v, 1)} />
        <MoverCard title="Today's Top Gainers (Price)"  rows={gainers}   field="change_percent" tone="up"   onClick={onClick} fmt={(v) => `${Number(v) >= 0 ? '+' : ''}${num(v, 2)}%`} />
        <MoverCard title="Today's Top Decliners (Price)" rows={decliners} field="change_percent" tone="down" onClick={onClick} fmt={(v) => `${Number(v) >= 0 ? '+' : ''}${num(v, 2)}%`} />
      </div>
    </>
  );
}

function MoverCard({ title, rows, field, tone, onClick, fmt }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="card">
        <div className="card-head"><div className="card-title">{title}</div></div>
        <div className="card-body"><Empty title="No data" /></div>
      </div>
    );
  }
  // Build a mini-bar per stock — values normalized for the sparkline-style display.
  const max = Math.max(...rows.map((r) => Math.abs(Number(r[field]) || 0)), 1);
  return (
    <div className="card">
      <div className="card-head">
        <div className="flex items-center gap-2">
          {tone === 'up' ? <TrendingUp size={16} style={{ color: 'var(--success)' }} />
                          : <Activity size={16} style={{ color: 'var(--danger)' }} />}
          <div className="card-title">{title}</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: 32 }} className="num">#</th>
              <th>Symbol</th>
              <th>Sector</th>
              <th className="num">Value</th>
              <th style={{ width: 110 }}>Bar</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s, i) => {
              const v = Number(s[field]) || 0;
              const w = Math.min(100, (Math.abs(v) / max) * 100);
              return (
                <tr key={s.symbol} onClick={() => onClick(s.symbol)} style={{ cursor: 'pointer' }}>
                  <td className="num mono tnum muted">{i + 1}</td>
                  <td style={{ fontWeight: 'var(--w-semibold)' }}>{s.symbol}</td>
                  <td className="t-xs muted" style={{
                    maxWidth: 110, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>{s.sector || '—'}</td>
                  <td className={`num mono tnum t-xs ${tone}`}>{fmt(s[field])}</td>
                  <td>
                    <div className="bar" style={{ width: 90 }}>
                      <div className="bar-fill" style={{
                        width: `${w}%`,
                        background: tone === 'up' ? 'var(--success)' : 'var(--danger)',
                      }} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── tab: leaderboard ≥ 80 ────────────────────────────────────────────────
function LeaderboardTab({ items, sectorFilter, onClick }) {
  const [activeSec, setActiveSec] = useState(sectorFilter || '');
  const eligible = items.filter((s) => Number(s.composite_score) >= 80);
  const sectors = Array.from(new Set(eligible.map((s) => s.sector).filter(Boolean))).sort();
  const rows = (activeSec ? eligible.filter((s) => s.sector === activeSec) : eligible)
    .sort((a, b) => Number(b.composite_score) - Number(a.composite_score));

  if (eligible.length === 0) {
    return (
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body">
          <Empty title="No A-grade names" desc="No symbols currently rank ≥ 80 on composite." />
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">A-Grade Leaderboard (Composite ≥ 80)</div>
            <div className="card-sub">{eligible.length} qualifying names · click chip to filter by sector</div>
          </div>
        </div>
        <div className="card-body" style={{ paddingBottom: 0 }}>
          <div className="flex items-center gap-2" style={{ flexWrap: 'wrap', marginBottom: 'var(--space-3)' }}>
            <button
              className={`btn ${activeSec === '' ? 'btn-primary' : 'btn-outline'} btn-sm`}
              onClick={() => setActiveSec('')}
            >
              All ({eligible.length})
            </button>
            {sectors.map((s) => {
              const c = eligible.filter((e) => e.sector === s).length;
              return (
                <button
                  key={s}
                  className={`btn ${activeSec === s ? 'btn-primary' : 'btn-outline'} btn-sm`}
                  onClick={() => setActiveSec(s)}
                >
                  {s} ({c})
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body" style={{ padding: 0 }}>
          <div style={{ overflow: 'auto', maxHeight: '70vh' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: 32 }} className="num">#</th>
                  <th>Symbol</th>
                  <th>Sector</th>
                  <th className="num">Composite</th>
                  <th>Grade</th>
                  <th className="num">Q</th>
                  <th className="num">M</th>
                  <th className="num">V</th>
                  <th className="num">G</th>
                  <th className="num">P</th>
                  <th className="num">S</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s, i) => (
                  <tr key={s.symbol} onClick={() => onClick(s.symbol)} style={{ cursor: 'pointer' }}>
                    <td className="num mono tnum muted">{i + 1}</td>
                    <td style={{ fontWeight: 'var(--w-semibold)' }}>
                      {s.symbol}
                      {s.company_name && (
                        <div className="t-xs muted" style={{
                          maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>{s.company_name}</div>
                      )}
                    </td>
                    <td className="t-xs muted">{s.sector || '—'}</td>
                    <td className="num">
                      <span className={`badge ${scoreClass(s.composite_score)}`}>
                        {num(s.composite_score, 1)}
                      </span>
                    </td>
                    <td className="t-xs mono" style={{ color: scoreColor(s.composite_score), fontWeight: 'var(--w-semibold)' }}>
                      {grade(s.composite_score)}
                    </td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.quality_score) }}>{num(s.quality_score, 0)}</td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.momentum_score) }}>{num(s.momentum_score, 0)}</td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.value_score) }}>{num(s.value_score, 0)}</td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.growth_score) }}>{num(s.growth_score, 0)}</td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.positioning_score) }}>{num(s.positioning_score, 0)}</td>
                    <td className="num mono tnum t-xs" style={{ color: scoreColor(s.stability_score) }}>{num(s.stability_score, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}

// ─── tab: factor heatmap ──────────────────────────────────────────────────
function HeatmapTab({ items, sectorFilter, onClick }) {
  // Show top 50 by composite (or filtered by sector). Cell = factor score, color encodes value.
  const arr = items.filter((s) => s.composite_score != null);
  const filtered = (sectorFilter ? arr.filter((s) => s.sector === sectorFilter) : arr)
    .sort((a, b) => Number(b.composite_score) - Number(a.composite_score))
    .slice(0, 50);

  if (filtered.length === 0) {
    return (
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body"><Empty title="No data" /></div>
      </div>
    );
  }

  const heatColor = (v) => {
    if (v == null || isNaN(Number(v))) return 'var(--surface-2)';
    const n = Number(v);
    // Stoplight gradient: red → amber → cyan → green
    if (n >= 80) return 'var(--success-soft)';
    if (n >= 60) return 'var(--cyan-soft)';
    if (n >= 40) return 'var(--amber-soft)';
    return 'var(--danger-soft)';
  };
  const textColor = (v) => {
    if (v == null) return 'var(--text-3)';
    return scoreColor(v);
  };

  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Factor Heatmap (Top 50 by Composite)</div>
          <div className="card-sub">Cell color = factor score 0-100 · click row → stock detail</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        <div style={{ overflow: 'auto', maxHeight: '70vh' }}>
          <table className="data-table" style={{ tableLayout: 'fixed' }}>
            <thead>
              <tr>
                <th style={{ width: 90 }}>Symbol</th>
                <th className="num" style={{ width: 70 }}>Comp</th>
                {FACTORS.map((f) => (
                  <th key={f.key} className="num" style={{ width: 90 }}>{f.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.symbol} onClick={() => onClick(s.symbol)} style={{ cursor: 'pointer' }}>
                  <td style={{ fontWeight: 'var(--w-semibold)' }}>{s.symbol}</td>
                  <td className="num">
                    <span className={`badge ${scoreClass(s.composite_score)}`}>
                      {num(s.composite_score, 0)}
                    </span>
                  </td>
                  {FACTORS.map((f) => {
                    const v = s[f.scoreKey];
                    return (
                      <td key={f.key}
                          title={`${f.label}: ${num(v, 1)}`}
                          style={{
                            background: heatColor(v),
                            textAlign: 'center',
                            fontFamily: 'var(--font-mono)',
                            fontVariantNumeric: 'tabular-nums',
                            fontWeight: 'var(--w-semibold)',
                            color: textColor(v),
                            fontSize: 'var(--t-xs)',
                          }}>
                        {v == null ? '—' : num(v, 0)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── tab: distributions per factor ────────────────────────────────────────
function DistributionTab({ items }) {
  const buckets = useMemo(() => {
    // 10-bucket histogram per factor, range [0, 100]
    const out = {};
    FACTORS.forEach((f) => {
      const counts = Array.from({ length: 10 }, (_, i) => ({
        bucket: `${i * 10}-${(i + 1) * 10}`,
        count: 0,
      }));
      items.forEach((s) => {
        const v = Number(s[f.scoreKey]);
        if (isNaN(v) || s[f.scoreKey] == null) return;
        const idx = Math.min(9, Math.max(0, Math.floor(v / 10)));
        counts[idx].count += 1;
      });
      out[f.key] = counts;
    });
    return out;
  }, [items]);

  if (!items || items.length === 0) {
    return (
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body"><Empty title="No data" /></div>
      </div>
    );
  }

  return (
    <div className="grid grid-3" style={{ marginTop: 'var(--space-4)' }}>
      {FACTORS.map((f) => {
        const data = buckets[f.key] || [];
        const max = Math.max(...data.map((d) => d.count), 1);
        const Icon = f.icon;
        return (
          <div className="card" key={f.key}>
            <div className="card-head">
              <div className="flex items-center gap-2">
                <Icon size={16} style={{ color: f.tone }} />
                <div className="card-title">{f.label}</div>
              </div>
            </div>
            <div className="card-body">
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="bucket" tick={{ fill: 'var(--text-3)', fontSize: 9 }} interval={0} />
                    <YAxis tick={{ fill: 'var(--text-3)', fontSize: 10 }} />
                    <RTooltip contentStyle={TOOLTIP_STYLE}
                              formatter={(v) => [v, 'Stocks']}
                              labelFormatter={(b) => `Score ${b}`} />
                    <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                      {data.map((d, i) => (
                        <Cell key={i} fill={i >= 8 ? 'var(--success)'
                                          : i >= 6 ? 'var(--cyan)'
                                          : i >= 4 ? 'var(--amber)'
                                          : 'var(--danger)'}
                              opacity={Math.max(0.45, d.count / max)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── tab: correlation matrix ──────────────────────────────────────────────
function CorrelationTab({ items }) {
  const matrix = useMemo(() => {
    if (!items || items.length === 0) return null;
    const keys = FACTORS.map((f) => f.scoreKey);
    // Pearson correlation across all stocks where both factors are non-null
    const corr = (a, b) => {
      const pairs = items
        .map((s) => [Number(s[a]), Number(s[b])])
        .filter(([x, y]) => !isNaN(x) && !isNaN(y));
      if (pairs.length < 2) return null;
      const n = pairs.length;
      const mx = pairs.reduce((s, [x]) => s + x, 0) / n;
      const my = pairs.reduce((s, [, y]) => s + y, 0) / n;
      let num = 0, dx = 0, dy = 0;
      pairs.forEach(([x, y]) => {
        num += (x - mx) * (y - my);
        dx  += (x - mx) ** 2;
        dy  += (y - my) ** 2;
      });
      const den = Math.sqrt(dx * dy);
      if (den === 0) return null;
      return num / den;
    };

    const m = {};
    keys.forEach((a) => {
      m[a] = {};
      keys.forEach((b) => {
        m[a][b] = a === b ? 1 : corr(a, b);
      });
    });
    return m;
  }, [items]);

  if (!matrix) {
    return (
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body"><Empty title="No data" /></div>
      </div>
    );
  }

  const corrColor = (v) => {
    if (v == null) return 'var(--surface-2)';
    if (v >= 0.6)  return 'var(--success-soft)';
    if (v >= 0.3)  return 'var(--cyan-soft)';
    if (v >= -0.3) return 'var(--surface-2)';
    if (v >= -0.6) return 'var(--amber-soft)';
    return 'var(--danger-soft)';
  };

  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Factor Correlation Matrix</div>
          <div className="card-sub">Pearson correlation across the universe · 1.0 = perfect, 0 = none, −1.0 = inverse</div>
        </div>
      </div>
      <div className="card-body">
        <div style={{ overflow: 'auto' }}>
          <table className="data-table" style={{ tableLayout: 'fixed', minWidth: 540 }}>
            <thead>
              <tr>
                <th style={{ width: 110 }}>&nbsp;</th>
                {FACTORS.map((f) => (
                  <th key={f.key} className="num" style={{ width: 90 }}>{f.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FACTORS.map((rf) => (
                <tr key={rf.key}>
                  <td style={{ fontWeight: 'var(--w-semibold)' }}>{rf.label}</td>
                  {FACTORS.map((cf) => {
                    const v = matrix[rf.scoreKey]?.[cf.scoreKey];
                    return (
                      <td key={cf.key}
                          title={`${rf.label} ↔ ${cf.label}: ${v == null ? '—' : v.toFixed(3)}`}
                          style={{
                            background: corrColor(v),
                            textAlign: 'center',
                            fontFamily: 'var(--font-mono)',
                            fontVariantNumeric: 'tabular-nums',
                            fontWeight: 'var(--w-semibold)',
                            fontSize: 'var(--t-xs)',
                            color: rf.scoreKey === cf.scoreKey ? 'var(--text-2)' : 'var(--text-1)',
                          }}>
                        {v == null ? '—' : v.toFixed(2)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-3" style={{
            marginTop: 'var(--space-4)', flexWrap: 'wrap',
          }}>
            <span className="t-xs muted">Legend:</span>
            <LegendChip color="var(--success-soft)" label="≥ 0.6 strong+" />
            <LegendChip color="var(--cyan-soft)"    label="0.3 – 0.6"    />
            <LegendChip color="var(--surface-2)"    label="−0.3 – 0.3"   />
            <LegendChip color="var(--amber-soft)"   label="−0.6 – −0.3"  />
            <LegendChip color="var(--danger-soft)"  label="< −0.6 strong−" />
          </div>
        </div>
      </div>
    </div>
  );
}

function ScoreLegend() {
  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Score Guide</div>
          <div className="card-sub">Each factor scored 0-100 from underlying fundamentals · composite is research-weighted blend</div>
        </div>
      </div>
      <div className="card-body">
        <div className="flex items-center gap-4" style={{ flexWrap: 'wrap' }}>
          <LegendChip color="var(--success)" label="80–100 Excellent" />
          <LegendChip color="var(--cyan)"    label="60–79 Good" />
          <LegendChip color="var(--amber)"   label="40–59 Fair" />
          <LegendChip color="var(--danger)"  label="0–39 Weak" />
          <span className="t-xs muted" style={{ marginLeft: 'auto' }}>
            Source: /api/scores/stockscores
          </span>
        </div>
      </div>
    </div>
  );
}

function LegendChip({ color, label }) {
  return (
    <div className="flex items-center gap-2">
      <div style={{ width: 28, height: 8, borderRadius: 4, background: color }} />
      <span className="t-xs">{label}</span>
    </div>
  );
}

// ─── shared ────────────────────────────────────────────────────────────────
function Tabs({ tabs, value, onChange }) {
  return (
    <div className="flex items-center gap-2" style={{
      marginTop: 'var(--space-4)', borderBottom: '1px solid var(--border-soft)',
    }}>
      {tabs.map(t => (
        <button
          key={t.value}
          className="btn btn-ghost btn-sm"
          onClick={() => onChange(t.value)}
          style={{
            borderBottom: value === t.value ? '2px solid var(--brand)' : '2px solid transparent',
            borderRadius: 0,
            color: value === t.value ? 'var(--text-1)' : 'var(--text-2)',
            fontWeight: value === t.value ? 'var(--w-semibold)' : 'var(--w-medium)',
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

function Kpi({ label, value, sub, tone }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="eyebrow">{label}</div>
      <div className={`mono ${tone || ''}`}
           style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
        {value}
      </div>
      {sub && <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>{sub}</div>}
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

// ─── helpers ───────────────────────────────────────────────────────────────
function topBy(items, field, count, sector, dir) {
  const arr = (sector ? items.filter(s => s.sector === sector) : items)
    .filter(s => s[field] != null);
  arr.sort((a, b) => dir === 'desc' ? Number(b[field]) - Number(a[field]) : Number(a[field]) - Number(b[field]));
  return arr.slice(0, count);
}

// ─── input schemas ─────────────────────────────────────────────────────────
const QUALITY_SCHEMA = [
  { key: 'return_on_equity_pct',           label: 'ROE',                      fmt: v => pct(v, 1) },
  { key: 'return_on_assets_pct',           label: 'ROA',                      fmt: v => pct(v, 1) },
  { key: 'return_on_invested_capital_pct', label: 'ROIC',                     fmt: v => pct(v, 1) },
  { key: 'gross_margin_pct',               label: 'Gross Margin',             fmt: v => pct(v, 1) },
  { key: 'operating_margin_pct',           label: 'Operating Margin',         fmt: v => pct(v, 1) },
  { key: 'profit_margin_pct',              label: 'Profit Margin',            fmt: v => pct(v, 1) },
  { key: 'ebitda_margin_pct',              label: 'EBITDA Margin',            fmt: v => pct(v, 1) },
  { key: 'fcf_to_net_income',              label: 'FCF / Net Income',         fmt: v => num(v, 2) },
  { key: 'operating_cf_to_net_income',     label: 'OCF / Net Income',         fmt: v => num(v, 2) },
  { key: 'debt_to_equity',                 label: 'Debt / Equity',            fmt: v => num(v, 2) },
  { key: 'current_ratio',                  label: 'Current Ratio',            fmt: v => num(v, 2) },
  { key: 'quick_ratio',                    label: 'Quick Ratio',              fmt: v => num(v, 2) },
  { key: 'earnings_surprise_avg',          label: 'Earnings Surprise (4Q)',   fmt: v => pct(v, 2) },
  { key: 'eps_growth_stability',           label: 'EPS Growth Stability',     fmt: v => num(v, 2) },
  { key: 'earnings_beat_rate',             label: 'Earnings Beat Rate',       fmt: v => pct(v, 1) },
  { key: 'consecutive_positive_quarters',  label: 'Consecutive +Q',           fmt: v => num(v, 0) },
  { key: 'estimate_revision_direction',    label: 'Revision Direction',      fmt: v => num(v, 1) },
  { key: 'revision_activity_30d',          label: 'Revision Activity 30d',    fmt: v => num(v, 1) },
  { key: 'estimate_momentum_60d',          label: 'Estimate Momentum 60d',    fmt: v => pct(v, 2) },
  { key: 'estimate_momentum_90d',          label: 'Estimate Momentum 90d',    fmt: v => pct(v, 2) },
  { key: 'revision_trend_score',           label: 'Revision Trend',           fmt: v => num(v, 1) },
  { key: 'payout_ratio',                   label: 'Payout Ratio',             fmt: v => pct(v, 1) },
  { key: 'free_cashflow',                  label: 'Free Cash Flow',           fmt: money },
  { key: 'operating_cashflow',             label: 'Operating Cash Flow',      fmt: money },
  { key: 'total_debt',                     label: 'Total Debt',               fmt: money },
  { key: 'total_cash',                     label: 'Total Cash',               fmt: money },
  { key: 'cash_per_share',                 label: 'Cash / Share',             fmt: v => `$${num(v, 2)}` },
  { key: 'earnings_growth_pct',            label: 'Earnings Growth',          fmt: v => pct(v, 2) },
  { key: 'revenue_growth_pct',             label: 'Revenue Growth',           fmt: v => pct(v, 2) },
  { key: 'earnings_growth_4q_avg',         label: 'Earnings Growth 4Q Avg',   fmt: v => pct(v, 2) },
];

const MOMENTUM_SCHEMA = [
  { key: 'price_vs_sma_50',  label: 'Price vs 50-SMA',  fmt: v => pct(v, 2) },
  { key: 'price_vs_sma_200', label: 'Price vs 200-SMA', fmt: v => pct(v, 2) },
  { key: 'momentum_3m',      label: '3-Month Return',   fmt: v => pct(v, 2) },
  { key: 'momentum_6m',      label: '6-Month Return',   fmt: v => pct(v, 2) },
  { key: 'momentum_12_3',    label: '12-3 Momentum',    fmt: v => pct(v, 2) },
  { key: 'price_vs_52w_high',label: 'Price vs 52w High',fmt: v => pct(v, 2) },
  { key: 'current_price',    label: 'Current Price',    fmt: v => `$${num(v, 2)}` },
  { key: 'rsi',              label: 'RSI (14)',         fmt: v => num(v, 1) },
  { key: 'macd',             label: 'MACD',             fmt: v => num(v, 3) },
];

const VALUE_SCHEMA = [
  { key: 'stock_pe',            label: 'P/E',          fmt: v => num(v, 2) },
  { key: 'stock_forward_pe',    label: 'Forward P/E',  fmt: v => num(v, 2) },
  { key: 'stock_pb',            label: 'P/B',          fmt: v => num(v, 2) },
  { key: 'stock_ps',            label: 'P/S',          fmt: v => num(v, 2) },
  { key: 'stock_ev_ebitda',     label: 'EV / EBITDA',  fmt: v => num(v, 2) },
  { key: 'stock_ev_revenue',    label: 'EV / Revenue', fmt: v => num(v, 2) },
  { key: 'peg_ratio',           label: 'PEG',          fmt: v => num(v, 2) },
  { key: 'stock_dividend_yield',label: 'Dividend Yield', fmt: v => pct(v, 2) },
];

const GROWTH_SCHEMA = [
  { key: 'revenue_growth_3y_cagr',     label: 'Revenue CAGR (3Y)',       fmt: v => pct(v, 2) },
  { key: 'eps_growth_3y_cagr',         label: 'EPS CAGR (3Y)',           fmt: v => pct(v, 2) },
  { key: 'net_income_growth_yoy',      label: 'Net Income Growth YoY',   fmt: v => pct(v, 2) },
  { key: 'operating_income_growth_yoy',label: 'Op Income Growth YoY',    fmt: v => pct(v, 2) },
  { key: 'gross_margin_trend',         label: 'Gross Margin Trend',      fmt: v => `${num(v, 2)} pp` },
  { key: 'operating_margin_trend',     label: 'Op Margin Trend',         fmt: v => `${num(v, 2)} pp` },
  { key: 'net_margin_trend',           label: 'Net Margin Trend',        fmt: v => `${num(v, 2)} pp` },
  { key: 'roe_trend',                  label: 'ROE Trend',               fmt: v => num(v, 2) },
  { key: 'sustainable_growth_rate',    label: 'Sustainable Growth Rate', fmt: v => pct(v, 2) },
  { key: 'quarterly_growth_momentum',  label: 'Quarterly Growth Mom',    fmt: v => `${num(v, 2)} pp` },
  { key: 'fcf_growth_yoy',             label: 'FCF Growth YoY',          fmt: v => pct(v, 2) },
  { key: 'ocf_growth_yoy',             label: 'OCF Growth YoY',          fmt: v => pct(v, 2) },
  { key: 'asset_growth_yoy',           label: 'Asset Growth YoY',        fmt: v => pct(v, 2) },
];

const POSITIONING_SCHEMA = [
  { key: 'institutional_ownership_pct', label: 'Institutional Own %', fmt: v => pct(v, 1) },
  { key: 'top_10_institutions_pct',     label: 'Top 10 Institutions %', fmt: v => pct(v, 1) },
  { key: 'institutional_holders_count', label: 'Institutional Holders', fmt: v => num(v, 0) },
  { key: 'insider_ownership_pct',       label: 'Insider Own %',       fmt: v => pct(v, 1) },
  { key: 'short_interest_pct',          label: 'Short Interest %',    fmt: v => pct(v, 2) },
  { key: 'short_percent_of_float',      label: 'Short % of Float',    fmt: v => pct(v, 1) },
  { key: 'short_ratio',                 label: 'Days to Cover',       fmt: v => Number(v) < 99999 ? num(v, 2) : '—' },
  { key: 'ad_rating',                   label: 'A/D Rating',          fmt: v => num(v, 1) },
];

const STABILITY_SCHEMA = [
  { key: 'volatility_12m',           label: 'Volatility (12M)',     fmt: v => pct(v, 2) },
  { key: 'downside_volatility',      label: 'Downside Volatility',  fmt: v => pct(v, 2) },
  { key: 'max_drawdown_52w',         label: 'Max Drawdown (52W)',   fmt: v => pct(v, 2) },
  { key: 'beta',                     label: 'Beta vs Market',       fmt: v => num(v, 2) },
  { key: 'volatility_risk_component',label: 'Volatility Risk Score',fmt: v => num(v, 1) },
  { key: 'volume_consistency',       label: 'Volume Consistency',   fmt: v => num(v, 1) },
  { key: 'turnover_velocity',        label: 'Turnover Velocity',    fmt: v => num(v, 1) },
  { key: 'volatility_volume_ratio',  label: 'Volatility / Volume',  fmt: v => num(v, 1) },
  { key: 'daily_spread',             label: 'Daily Spread',         fmt: v => num(v, 1) },
];
