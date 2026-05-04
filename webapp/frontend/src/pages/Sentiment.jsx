import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  RefreshCw, Inbox, Search, TrendingUp, TrendingDown, Minus,
  ArrowLeft, AlertCircle, MessageSquare, Activity,
} from 'lucide-react';
import {
  Cell, ResponsiveContainer, Tooltip as RechartsTooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine,
  BarChart, Bar, FunnelChart, Funnel, LabelList,
} from 'recharts';
import { api } from '../services/api';

const TT_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

const fmtDate = (d) => {
  if (!d) return '—';
  try { return new Date(d).toLocaleDateString(); } catch { return String(d); }
};
const num = (v, dp = 2) => (v == null || isNaN(Number(v))) ? '—' : Number(v).toFixed(dp);
const pct = (v, dp = 2) => (v == null || isNaN(Number(v))) ? '—' : `${Number(v).toFixed(dp)}%`;
const money = (v) => (v == null || isNaN(Number(v))) ? '—' : `$${Number(v).toFixed(2)}`;

const sentimentLabel = (score) => {
  if (score == null) return { label: 'Unknown', cls: '' };
  if (score > 0.3) return { label: 'Bullish', cls: 'badge-success' };
  if (score < -0.3) return { label: 'Bearish', cls: 'badge-danger' };
  return { label: 'Neutral', cls: 'badge-amber' };
};

const sentimentIcon = (score) => {
  if (score == null) return <Minus size={14} />;
  if (score > 0.3) return <TrendingUp size={14} />;
  if (score < -0.3) return <TrendingDown size={14} />;
  return <Minus size={14} />;
};

const scoreToBadge = (score) => {
  if (score == null) return 'badge';
  if (score > 0.2) return 'badge badge-success';
  if (score < -0.2) return 'badge badge-danger';
  return 'badge badge-amber';
};

const calcAnalystSentiment = (bullish, bearish, neutral, total) => {
  if (!total || total === 0) return null;
  return (bullish / total) - (bearish / total);
};

const detectDivergence = (...scores) => {
  const filtered = scores.filter((s) => s != null);
  if (filtered.length < 2) return null;
  const range = Math.max(...filtered) - Math.min(...filtered);
  if (range > 0.6) return { isDiverged: true, severity: range > 1 ? 'critical' : 'moderate', range };
  return { isDiverged: false };
};

const TABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'analyst', label: 'Analyst Detail' },
  { value: 'social', label: 'Social Detail' },
];

export default function Sentiment() {
  const [tab, setTab] = useState('overview');
  const [searchFilter, setSearchFilter] = useState('');
  const [filterSentiment, setFilterSentiment] = useState('all');
  const [sortBy, setSortBy] = useState('composite');
  const [selectedSymbol, setSelectedSymbol] = useState(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['sentiment-stocks'],
    queryFn: async () => {
      const res = await api.get('/api/sentiment/data?limit=5000&page=1');
      return res.data;
    },
    staleTime: 300000,
    refetchInterval: 300000,
  });

  // Cross-source aggregate sentiment (analyst + AAII retail + NAAIM pro + fear/greed)
  const summaryQ = useQuery({
    queryKey: ['sentiment-summary'],
    queryFn: () => api.get('/api/sentiment/summary').then((r) => r.data?.data || null),
    refetchInterval: 300000,
  });

  // Algo composite scores joined for contrarian-setup detection
  const scoresQ = useQuery({
    queryKey: ['sentiment-scores-overlay'],
    queryFn: () =>
      api.get('/api/scores/stockscores?limit=5000&offset=0&sortBy=composite_score&sp500Only=true')
         .then((r) => r.data?.items || []),
    refetchInterval: 300000,
  });

  // Per-symbol divergence time series (analyst-only proxy: bull% − bear% over last 90d)
  const divergenceQ = useQuery({
    queryKey: ['sentiment-divergence'],
    queryFn: () => api.get('/api/sentiment/divergence').then((r) => r.data?.items || []),
    refetchInterval: 300000,
  });

  const rawData = data?.items || data?.data || [];

  const stocksList = useMemo(() => {
    const grouped = rawData.reduce((acc, item) => {
      const sym = item.symbol;
      if (!acc[sym]) acc[sym] = { symbol: sym, analyst: [] };
      const analystScore = calcAnalystSentiment(
        item.bullish_count, item.bearish_count, item.neutral_count, item.analyst_count
      );
      acc[sym].analyst.push({ ...item, sentiment_score: analystScore, source: 'analyst' });
      return acc;
    }, {});

    return Object.values(grouped).map((stock) => {
      const latestAnalyst = stock.analyst[0] || null;
      const compositeScore = latestAnalyst?.sentiment_score ?? null;
      return {
        symbol: stock.symbol,
        compositeScore,
        analyst: stock.analyst,
        latestAnalyst,
        allData: [...stock.analyst].sort((a, b) => new Date(b.date) - new Date(a.date)),
        divergence: detectDivergence(latestAnalyst?.sentiment_score),
      };
    });
  }, [rawData]);

  const filtered = useMemo(() => {
    let list = stocksList.filter((s) => {
      const matchesSearch = s.symbol.toLowerCase().includes(searchFilter.toLowerCase());
      if (filterSentiment === 'all') return matchesSearch;
      if (filterSentiment === 'bullish') return matchesSearch && s.compositeScore > 0.3;
      if (filterSentiment === 'bearish') return matchesSearch && s.compositeScore < -0.3;
      if (filterSentiment === 'neutral')
        return matchesSearch && s.compositeScore >= -0.3 && s.compositeScore <= 0.3;
      return matchesSearch;
    });

    list.sort((a, b) => {
      if (sortBy === 'symbol') return a.symbol.localeCompare(b.symbol);
      const aScore = a.compositeScore;
      const bScore = b.compositeScore;
      if (aScore == null && bScore == null) return 0;
      if (aScore == null) return 1;
      if (bScore == null) return -1;
      return bScore - aScore;
    });

    return list;
  }, [stocksList, searchFilter, filterSentiment, sortBy]);

  const stats = useMemo(() => {
    let bull = 0, bear = 0, neutral = 0, unknown = 0;
    stocksList.forEach((s) => {
      if (s.compositeScore == null) unknown++;
      else if (s.compositeScore > 0.3) bull++;
      else if (s.compositeScore < -0.3) bear++;
      else neutral++;
    });
    return { total: stocksList.length, bull, bear, neutral, unknown };
  }, [stocksList]);

  const selectedStock = useMemo(
    () => stocksList.find((s) => s.symbol === selectedSymbol) || null,
    [stocksList, selectedSymbol]
  );

  // Composite gauge (0-100) — average across available sources, normalized.
  const compositeGauge = useMemo(() => {
    const sum = summaryQ.data || {};
    const components = [];
    if (sum.fear_greed?.value != null) {
      components.push({ name: 'Fear & Greed', value: Number(sum.fear_greed.value) });
    }
    if (sum.aaii) {
      const tot = (Number(sum.aaii.bullish) || 0) + (Number(sum.aaii.bearish) || 0)
                + (Number(sum.aaii.neutral) || 0);
      if (tot > 0) {
        const score = ((Number(sum.aaii.bullish) || 0) - (Number(sum.aaii.bearish) || 0)) / tot;
        components.push({ name: 'AAII Retail', value: 50 + score * 50 });
      }
    }
    if (sum.naaim?.naaim_number_mean != null) {
      // NAAIM ranges 0-100 (sometimes -100 to 200); clamp to 0-100
      const v = Number(sum.naaim.naaim_number_mean);
      components.push({ name: 'NAAIM Pro', value: Math.min(100, Math.max(0, v)) });
    }
    if (sum.analyst) {
      const tot = Number(sum.analyst.analyst_count) || 0;
      if (tot > 0) {
        const bull = Number(sum.analyst.bullish_count) || 0;
        const bear = Number(sum.analyst.bearish_count) || 0;
        components.push({ name: 'Analyst', value: 50 + ((bull - bear) / tot) * 50 });
      }
    }
    if (components.length === 0) return null;
    const score = components.reduce((s, c) => s + c.value, 0) / components.length;
    return { score: Math.round(score), components };
  }, [summaryQ.data]);

  // Sentiment 7d change leaders (analyst-derived, comparing latest vs 7-day-ago bull−bear %)
  const changeLeaders = useMemo(() => {
    const byDate = {};
    (divergenceQ.data || []).forEach((row) => {
      if (!row.symbol || !row.date) return;
      const sym = row.symbol;
      if (!byDate[sym]) byDate[sym] = [];
      byDate[sym].push(row);
    });
    const moves = [];
    Object.entries(byDate).forEach(([sym, rows]) => {
      rows.sort((a, b) => new Date(b.date) - new Date(a.date));
      if (rows.length < 2) return;
      const cur = rows[0];
      const prev = rows.find((r) => {
        const days = (new Date(cur.date) - new Date(r.date)) / 86400000;
        return days >= 5;
      }) || rows[rows.length - 1];
      const curScore = (Number(cur.bull_percent) || 0) - (Number(cur.bear_percent) || 0);
      const prevScore = (Number(prev.bull_percent) || 0) - (Number(prev.bear_percent) || 0);
      moves.push({ symbol: sym, change: curScore - prevScore, current: curScore });
    });
    moves.sort((a, b) => b.change - a.change);
    return {
      gainers: moves.slice(0, 8),
      decliners: moves.slice(-8).reverse(),
    };
  }, [divergenceQ.data]);

  // Contrarian setups: low analyst sentiment + high algo composite (potential undervalued)
  // and inverse (potential traps): high analyst sentiment + low algo composite.
  const contrarianSetups = useMemo(() => {
    const scoreMap = new Map();
    (scoresQ.data || []).forEach((s) => scoreMap.set(s.symbol, s));
    const merged = stocksList
      .filter((s) => s.compositeScore != null)
      .map((s) => {
        const algo = scoreMap.get(s.symbol);
        return algo ? {
          symbol: s.symbol,
          analystScore: s.compositeScore,
          algoComposite: Number(algo.composite_score),
          sector: algo.sector,
        } : null;
      })
      .filter((s) => s && !isNaN(s.algoComposite));
    const buys = merged
      .filter((s) => s.analystScore < 0 && s.algoComposite >= 70)
      .sort((a, b) => b.algoComposite - a.algoComposite)
      .slice(0, 8);
    const traps = merged
      .filter((s) => s.analystScore > 0.3 && s.algoComposite < 50)
      .sort((a, b) => a.algoComposite - b.algoComposite)
      .slice(0, 8);
    return { buys, traps };
  }, [stocksList, scoresQ.data]);

  // Analyst rating funnel across the universe
  const ratingFunnel = useMemo(() => {
    let strongBuy = 0, buy = 0, hold = 0, sell = 0, strongSell = 0;
    stocksList.forEach((s) => {
      const a = s.latestAnalyst;
      if (!a || !a.analyst_count) return;
      const total = Number(a.analyst_count) || 0;
      const bull = Number(a.bullish_count) || 0;
      const bear = Number(a.bearish_count) || 0;
      const neut = Number(a.neutral_count) || 0;
      if (total === 0) return;
      const bullPct = bull / total;
      const bearPct = bear / total;
      if (bullPct >= 0.7) strongBuy++;
      else if (bullPct >= 0.4) buy++;
      else if (bearPct >= 0.7) strongSell++;
      else if (bearPct >= 0.4) sell++;
      else hold++;
    });
    return [
      { name: 'Strong Buy',  value: strongBuy,  fill: 'var(--success)' },
      { name: 'Buy',         value: buy,        fill: 'var(--cyan)'    },
      { name: 'Hold',        value: hold,       fill: 'var(--amber)'   },
      { name: 'Sell',        value: sell,       fill: 'var(--purple)'  },
      { name: 'Strong Sell', value: strongSell, fill: 'var(--danger)'  },
    ];
  }, [stocksList]);

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Market Sentiment</div>
          <div className="page-head-sub">
            Analyst ratings · price targets · social discussion · composite scoring
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={() => refetch()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-4">
        <Kpi label="Symbols Tracked" value={<span className="mono tnum">{stats.total}</span>} />
        <Kpi label="Bullish"
             value={<span className="mono tnum up">{stats.bull}</span>}
             sub={stats.total ? pct((stats.bull / stats.total) * 100, 1) : '—'} />
        <Kpi label="Bearish"
             value={<span className="mono tnum down">{stats.bear}</span>}
             sub={stats.total ? pct((stats.bear / stats.total) * 100, 1) : '—'} />
        <Kpi label="Neutral / Unknown"
             value={<span className="mono tnum">{stats.neutral + stats.unknown}</span>}
             sub={stats.total ? pct(((stats.neutral + stats.unknown) / stats.total) * 100, 1) : '—'} />
      </div>

      <Tabs tabs={TABS} value={tab} onChange={setTab} />

      <div style={{ marginTop: 'var(--space-4)' }}>
        {error && (
          <div className="alert alert-danger">
            <AlertCircle size={16} />
            <div>Failed to load sentiment data: {error.message}</div>
          </div>
        )}

        {tab === 'overview' && (
          <OverviewTab
            isLoading={isLoading}
            filtered={filtered}
            searchFilter={searchFilter}
            setSearchFilter={setSearchFilter}
            filterSentiment={filterSentiment}
            setFilterSentiment={setFilterSentiment}
            sortBy={sortBy}
            setSortBy={setSortBy}
            selectedSymbol={selectedSymbol}
            setSelectedSymbol={setSelectedSymbol}
            selectedStock={selectedStock}
            compositeGauge={compositeGauge}
            changeLeaders={changeLeaders}
            contrarianSetups={contrarianSetups}
            ratingFunnel={ratingFunnel}
            divergenceData={divergenceQ.data || []}
          />
        )}

        {tab === 'analyst' && (
          <AnalystTab
            stocks={filtered}
            isLoading={isLoading}
            selectedSymbol={selectedSymbol}
            setSelectedSymbol={setSelectedSymbol}
          />
        )}

        {tab === 'social' && (
          <SocialTab
            stocks={filtered}
            isLoading={isLoading}
            selectedSymbol={selectedSymbol}
            setSelectedSymbol={setSelectedSymbol}
          />
        )}
      </div>
    </div>
  );
}

function OverviewTab({
  isLoading, filtered, searchFilter, setSearchFilter,
  filterSentiment, setFilterSentiment, sortBy, setSortBy,
  selectedSymbol, setSelectedSymbol, selectedStock,
  compositeGauge, changeLeaders, contrarianSetups, ratingFunnel,
  divergenceData,
}) {
  return (
    <>
      {/* Composite gauge + funnel + change leaders */}
      <div className="grid grid-2" style={{ marginBottom: 'var(--space-4)' }}>
        <CompositeGauge gauge={compositeGauge} />
        <RatingFunnel data={ratingFunnel} />
      </div>

      <div className="grid grid-2" style={{ marginBottom: 'var(--space-4)' }}>
        <ChangeLeadersCard title="Sentiment 7-Day Gainers" rows={changeLeaders.gainers} tone="up" setSel={setSelectedSymbol} />
        <ChangeLeadersCard title="Sentiment 7-Day Decliners" rows={changeLeaders.decliners} tone="down" setSel={setSelectedSymbol} />
      </div>

      <div className="grid grid-2" style={{ marginBottom: 'var(--space-4)' }}>
        <ContrarianCard title="Contrarian Buys (bearish sentiment, strong algo)"
                        desc="Analyst score < 0, composite ≥ 70 — potential mispricing"
                        rows={contrarianSetups.buys}
                        tone="up"
                        setSel={setSelectedSymbol} />
        <ContrarianCard title="Potential Traps (bullish sentiment, weak algo)"
                        desc="Analyst score > 0.3, composite < 50 — buyer-beware"
                        rows={contrarianSetups.traps}
                        tone="down"
                        setSel={setSelectedSymbol} />
      </div>

      <DivergenceTimeline rows={divergenceData} />

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body">
          <div className="flex items-center gap-3" style={{ flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: '1 1 240px', minWidth: 240 }}>
              <Search size={14}
                      style={{ position: 'absolute', left: 10, top: '50%',
                               transform: 'translateY(-50%)', color: 'var(--text-3)' }} />
              <input
                className="input"
                placeholder="Filter by symbol (e.g. AAPL)"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                style={{ paddingLeft: 32 }}
              />
            </div>
            <select className="select" value={filterSentiment}
                    onChange={(e) => setFilterSentiment(e.target.value)}>
              <option value="all">All sentiment</option>
              <option value="bullish">Bullish</option>
              <option value="neutral">Neutral</option>
              <option value="bearish">Bearish</option>
            </select>
            <select className="select" value={sortBy}
                    onChange={(e) => setSortBy(e.target.value)}>
              <option value="composite">Sort: Composite</option>
              <option value="symbol">Sort: Symbol A-Z</option>
            </select>
            <span className="t-xs muted" style={{ marginLeft: 'auto' }}>
              {filtered.length} symbol{filtered.length === 1 ? '' : 's'}
            </span>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Stock Sentiment Table</div>
            <div className="card-sub">Click a row to drill into per-symbol details</div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {isLoading ? (
            <Empty title="Loading sentiment…" />
          ) : filtered.length === 0 ? (
            <Empty title="No symbols match" desc={searchFilter ? `No data for "${searchFilter}"` : 'No sentiment data available'} />
          ) : (
            <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th className="num">Score</th>
                    <th>Sentiment</th>
                    <th className="num">Analysts</th>
                    <th className="num">Bull</th>
                    <th className="num">Neutral</th>
                    <th className="num">Bear</th>
                    <th className="num">Target</th>
                    <th className="num">Current</th>
                    <th className="num">Upside %</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((s) => {
                    const a = s.latestAnalyst || {};
                    const upside = parseFloat(a.upside_downside_percent);
                    const lab = sentimentLabel(s.compositeScore);
                    return (
                      <tr key={s.symbol}
                          onClick={() => setSelectedSymbol(s.symbol)}
                          style={{
                            cursor: 'pointer',
                            background: s.symbol === selectedSymbol ? 'var(--brand-soft)' : undefined,
                          }}>
                        <td><span className="strong">{s.symbol}</span></td>
                        <td className="num mono tnum">
                          {s.compositeScore != null ? s.compositeScore.toFixed(2) : '—'}
                        </td>
                        <td>
                          <span className={`badge ${lab.cls}`}>
                            {sentimentIcon(s.compositeScore)} {lab.label}
                          </span>
                        </td>
                        <td className="num mono tnum">{a.analyst_count ?? 0}</td>
                        <td className="num mono tnum up">{a.bullish_count ?? 0}</td>
                        <td className="num mono tnum muted">{a.neutral_count ?? 0}</td>
                        <td className="num mono tnum down">{a.bearish_count ?? 0}</td>
                        <td className="num mono tnum">{money(a.target_price)}</td>
                        <td className="num mono tnum">{money(a.current_price)}</td>
                        <td className="num">
                          <span className={`mono tnum ${upside > 0 ? 'up' : upside < 0 ? 'down' : 'muted'}`}>
                            {isNaN(upside) ? '—' : pct(upside)}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {selectedStock && <StockDetail stock={selectedStock} onClose={() => setSelectedSymbol(null)} />}
    </>
  );
}

function StockDetail({ stock, onClose }) {
  const a = stock.latestAnalyst || {};
  const total = a.analyst_count || 1;
  const bull = a.bullish_count || 0;
  const neut = a.neutral_count || 0;
  const bear = a.bearish_count || 0;
  const upside = parseFloat(a.upside_downside_percent);

  // Build a 30-day analyst sentiment time series
  const trend = useMemo(() => {
    const arr = (stock.allData || [])
      .map((r) => ({
        date: String(r.date).slice(0, 10),
        score: r.sentiment_score != null ? Number(r.sentiment_score) : null,
      }))
      .filter((d) => d.score != null && !isNaN(d.score))
      .sort((a, b) => new Date(a.date) - new Date(b.date))
      .slice(-30);
    return arr;
  }, [stock]);

  const lab = sentimentLabel(stock.compositeScore);

  return (
    <>
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">{stock.symbol} · Sentiment Detail</div>
            <div className="card-sub">
              Analyst-derived score · {stock.divergence?.isDiverged ? 'divergent sources' : 'aligned sources'}
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <ArrowLeft size={14} /> Close
          </button>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Composite Sentiment</div>
              <div className="card-sub">Bull-bear analyst spread</div>
            </div>
          </div>
          <div className="card-body">
            <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-3)' }}>
              <div className="mono"
                   style={{ fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)' }}>
                {stock.compositeScore != null ? stock.compositeScore.toFixed(2) : '—'}
              </div>
              <span className={`badge ${lab.cls} badge-lg`}>
                {sentimentIcon(stock.compositeScore)} {lab.label}
              </span>
            </div>
            <div className="t-xs muted">
              {a.analyst_count || 0} analysts · {bull} bullish · {neut} neutral · {bear} bearish
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">30-Day Sentiment Trend</div>
              <div className="card-sub">Daily bull-bear analyst score</div>
            </div>
          </div>
          <div className="card-body" style={{ height: 200 }}>
            {trend.length >= 2 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-3)', fontSize: 10 }}
                         tickFormatter={(d) => String(d).slice(5)} />
                  <YAxis tick={{ fill: 'var(--text-3)', fontSize: 10 }} domain={[-1, 1]} width={36} />
                  <ReferenceLine y={0} stroke="var(--border)" />
                  <RechartsTooltip contentStyle={TT_STYLE}
                                   formatter={(v) => [Number(v).toFixed(2), 'Score']} />
                  <Line type="monotone" dataKey="score" stroke="var(--brand)"
                        strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty">
                <Inbox size={28} />
                <div className="empty-title">Not enough history</div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Analyst Distribution</div>
              <div className="card-sub">Latest reading</div>
            </div>
          </div>
          <div className="card-body">
            <div className="grid grid-3">
              <div className="stile">
                <div className="stile-label">Bullish</div>
                <div className="stile-value up">{((bull / total) * 100).toFixed(1)}%</div>
                <div className="stile-sub">{bull} analysts</div>
              </div>
              <div className="stile">
                <div className="stile-label">Neutral</div>
                <div className="stile-value">{((neut / total) * 100).toFixed(1)}%</div>
                <div className="stile-sub">{neut} analysts</div>
              </div>
              <div className="stile">
                <div className="stile-label">Bearish</div>
                <div className="stile-value down">{((bear / total) * 100).toFixed(1)}%</div>
                <div className="stile-sub">{bear} analysts</div>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Price Targets</div>
              <div className="card-sub">Consensus vs current</div>
            </div>
          </div>
          <div className="card-body">
            <div className="grid grid-3">
              <div className="stile">
                <div className="stile-label">Target</div>
                <div className="stile-value">{money(a.target_price)}</div>
                <div className="stile-sub">consensus</div>
              </div>
              <div className="stile">
                <div className="stile-label">Current</div>
                <div className="stile-value">{money(a.current_price)}</div>
                <div className="stile-sub">market</div>
              </div>
              <div className="stile">
                <div className="stile-label">Upside</div>
                <div className={`stile-value ${upside > 0 ? 'up' : upside < 0 ? 'down' : ''}`}>
                  {isNaN(upside) ? '—' : pct(upside)}
                </div>
                <div className="stile-sub">vs current</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Recent Sentiment Data</div>
            <div className="card-sub">Latest readings for {stock.symbol}</div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {stock.allData.length === 0 ? (
            <Empty title="No history" />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Source</th>
                  <th className="num">Score</th>
                  <th className="num">Bull</th>
                  <th className="num">Neutral</th>
                  <th className="num">Bear</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {stock.allData.slice(0, 10).map((row, i) => (
                  <tr key={`${stock.symbol}-${i}`}>
                    <td className="t-xs muted">{fmtDate(row.date)}</td>
                    <td><span className="badge">{row.source || 'analyst'}</span></td>
                    <td className="num">
                      <span className={scoreToBadge(row.sentiment_score)}>
                        {num(row.sentiment_score)}
                      </span>
                    </td>
                    <td className="num mono tnum up">{row.bullish_count ?? row.positive_mentions ?? '—'}</td>
                    <td className="num mono tnum muted">{row.neutral_count ?? row.neutral_mentions ?? '—'}</td>
                    <td className="num mono tnum down">{row.bearish_count ?? row.negative_mentions ?? '—'}</td>
                    <td className="num mono tnum">{row.analyst_count ?? row.total_mentions ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}

function AnalystTab({ stocks, isLoading, selectedSymbol, setSelectedSymbol }) {
  if (isLoading) return <Empty title="Loading analyst data…" />;
  if (!selectedSymbol) {
    return (
      <>
        <div className="alert alert-info">
          <Activity size={16} />
          <div>Select a symbol to view comprehensive analyst metrics, price targets, and recent actions.</div>
        </div>
        <div className="card" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-body" style={{ padding: 0 }}>
            {stocks.length === 0 ? <Empty title="No symbols" /> : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Sentiment</th>
                    <th className="num">Score</th>
                    <th className="num">Analysts</th>
                  </tr>
                </thead>
                <tbody>
                  {stocks.slice(0, 50).map((s) => {
                    const lab = sentimentLabel(s.compositeScore);
                    return (
                      <tr key={s.symbol} onClick={() => setSelectedSymbol(s.symbol)}
                          style={{ cursor: 'pointer' }}>
                        <td><span className="strong">{s.symbol}</span></td>
                        <td><span className={`badge ${lab.cls}`}>{lab.label}</span></td>
                        <td className="num mono tnum">
                          {s.compositeScore != null ? s.compositeScore.toFixed(2) : '—'}
                        </td>
                        <td className="num mono tnum">{s.latestAnalyst?.analyst_count ?? 0}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </>
    );
  }
  return <AnalystInsights symbol={selectedSymbol} onClose={() => setSelectedSymbol(null)} />;
}

function AnalystInsights({ symbol, onClose }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['analyst-insights', symbol],
    queryFn: () => api.get(`/api/sentiment/analyst/insights/${symbol}`).then((r) => r.data).catch(() => null),
    enabled: !!symbol,
  });

  const metrics = data?.metrics || null;
  const momentum = data?.momentum || null;
  const priceTargets = data?.priceTargets || [];
  const coverage = data?.coverage || null;
  const recentUpgrades = data?.recentUpgrades || [];

  return (
    <>
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">{symbol} · Analyst Insights</div>
            <div className="card-sub">Distribution · momentum · price targets · coverage</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <ArrowLeft size={14} /> Back
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginTop: 'var(--space-4)' }}>
          <AlertCircle size={16} />
          <div>{error.message || 'Failed to load analyst insights'}</div>
        </div>
      )}

      {isLoading ? <Empty title="Loading analyst insights…" />
       : !data ? <Empty title="No analyst data" desc={`No insights available for ${symbol}`} />
       : (
        <>
          {metrics && (
            <div className="grid grid-4" style={{ marginTop: 'var(--space-4)' }}>
              <Stile label="Bullish" value={<span className="up">{metrics.bullishPercent}%</span>}
                     sub={`${metrics.bullish} analysts`} />
              <Stile label="Neutral" value={<span>{metrics.neutralPercent}%</span>}
                     sub={`${metrics.neutral} analysts`} />
              <Stile label="Bearish" value={<span className="down">{metrics.bearishPercent}%</span>}
                     sub={`${metrics.bearish} analysts`} />
              <Stile label="Coverage" value={metrics.totalAnalysts}
                     sub="analysts covering" />
            </div>
          )}

          {metrics?.avgPriceTarget != null && (
            <div className="grid grid-3" style={{ marginTop: 'var(--space-4)' }}>
              <Stile label="Avg Target"
                     value={`$${typeof metrics.avgPriceTarget === 'number'
                       ? metrics.avgPriceTarget.toFixed(2)
                       : parseFloat(metrics.avgPriceTarget).toFixed(2)}`}
                     sub="consensus" />
              {metrics.priceTargetVsCurrent != null && (
                <Stile label="Upside / Downside"
                       value={
                         <span className={metrics.priceTargetVsCurrent > 0 ? 'up' : 'down'}>
                           {metrics.priceTargetVsCurrent > 0 ? '+' : ''}
                           {typeof metrics.priceTargetVsCurrent === 'number'
                             ? metrics.priceTargetVsCurrent.toFixed(1)
                             : parseFloat(metrics.priceTargetVsCurrent).toFixed(1)}%
                         </span>
                       }
                       sub="vs current price" />
              )}
              {coverage && (
                <Stile label="Firms"
                       value={coverage.totalFirms || 0}
                       sub="firms covering" />
              )}
            </div>
          )}

          {momentum && (
            <div className="card" style={{ marginTop: 'var(--space-4)' }}>
              <div className="card-head">
                <div>
                  <div className="card-title">30-Day Analyst Actions</div>
                  <div className="card-sub">Upgrade / downgrade momentum</div>
                </div>
              </div>
              <div className="card-body">
                <div className="grid grid-3">
                  <Stile label="Upgrades" value={<span className="up">{momentum.upgrades30d ?? 0}</span>} />
                  <Stile label="Downgrades" value={<span className="down">{momentum.downgrades30d ?? 0}</span>} />
                  <Stile label="Net Momentum"
                         value={
                           <span className={
                             (momentum.upgrades30d - momentum.downgrades30d) > 0 ? 'up' :
                             (momentum.upgrades30d - momentum.downgrades30d) < 0 ? 'down' : ''
                           }>
                             {(momentum.upgrades30d - momentum.downgrades30d) > 0 ? '+' : ''}
                             {(momentum.upgrades30d ?? 0) - (momentum.downgrades30d ?? 0)}
                           </span>
                         } />
                </div>
              </div>
            </div>
          )}

          {priceTargets.length > 0 && (
            <div className="card" style={{ marginTop: 'var(--space-4)' }}>
              <div className="card-head">
                <div>
                  <div className="card-title">Price Targets by Firm</div>
                  <div className="card-sub">Latest from each analyst</div>
                </div>
              </div>
              <div className="card-body" style={{ padding: 0 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Firm</th>
                      <th className="num">Target</th>
                      <th className="num">Previous</th>
                      <th className="num">Change</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {priceTargets.slice(0, 10).map((t, i) => {
                      const cur = parseFloat(t.target_price);
                      const prev = parseFloat(t.previous_target_price);
                      const diff = !isNaN(cur) && !isNaN(prev) ? cur - prev : null;
                      return (
                        <tr key={`${t.analyst_firm}-${i}`}>
                          <td>{t.analyst_firm}</td>
                          <td className="num mono tnum">{money(cur)}</td>
                          <td className="num mono tnum muted">{money(prev)}</td>
                          <td className="num">
                            {diff == null ? <span className="muted">—</span> :
                              <span className={`badge ${diff > 0 ? 'badge-success' : 'badge-danger'}`}>
                                {diff > 0 ? '+' : ''}{diff.toFixed(2)}
                              </span>}
                          </td>
                          <td className="t-xs muted">{fmtDate(t.target_date)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {recentUpgrades.length > 0 && (
            <div className="card" style={{ marginTop: 'var(--space-4)' }}>
              <div className="card-head">
                <div>
                  <div className="card-title">Recent Analyst Actions</div>
                  <div className="card-sub">Upgrades · downgrades · maintains</div>
                </div>
              </div>
              <div className="card-body" style={{ padding: 0 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Firm</th>
                      <th>Action</th>
                      <th>From</th>
                      <th>To</th>
                      <th>Details</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentUpgrades.slice(0, 10).map((u, i) => {
                      const action = String(u.action || '').toLowerCase();
                      const cls = action === 'up' ? 'badge-success' :
                                  action === 'down' ? 'badge-danger' : '';
                      const arrow = action === 'up' ? <TrendingUp size={12} /> :
                                    action === 'down' ? <TrendingDown size={12} /> :
                                    <Minus size={12} />;
                      return (
                        <tr key={`${u.firm}-${i}`}>
                          <td>{u.firm}</td>
                          <td><span className={`badge ${cls}`}>{arrow} {u.action || '—'}</span></td>
                          <td className="t-xs muted">{u.from_grade || '—'}</td>
                          <td><span className="badge">{u.to_grade || '—'}</span></td>
                          <td className="t-xs">{u.details || '—'}</td>
                          <td className="t-xs muted">{fmtDate(u.date)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {coverage?.firms?.length > 0 && (
            <div className="card" style={{ marginTop: 'var(--space-4)' }}>
              <div className="card-head">
                <div>
                  <div className="card-title">Coverage ({coverage.totalFirms} firms)</div>
                  <div className="card-sub">Active analyst coverage</div>
                </div>
              </div>
              <div className="card-body">
                <div className="grid grid-3">
                  {coverage.firms.slice(0, 9).map((firm, i) => (
                    <div className="stile" key={`${firm.analyst_firm || firm.name}-${i}`}>
                      <div className="stile-label">{firm.analyst_firm || firm.name}</div>
                      <div className="stile-value t-sm">{firm.analyst_name || '—'}</div>
                      <div className="stile-sub">
                        <span className="badge">{firm.coverage_status || 'covering'}</span>
                        {firm.coverage_started && (
                          <span className="muted" style={{ marginLeft: 'var(--space-2)' }}>
                            Since {fmtDate(firm.coverage_started)}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

function SocialTab({ stocks, isLoading, selectedSymbol, setSelectedSymbol }) {
  if (isLoading) return <Empty title="Loading social data…" />;
  if (!selectedSymbol) {
    return (
      <>
        <div className="alert alert-info">
          <MessageSquare size={16} />
          <div>Select a symbol to view Reddit · news · search · viral metrics.</div>
        </div>
        <div className="card" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-body" style={{ padding: 0 }}>
            {stocks.length === 0 ? <Empty title="No symbols" /> : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Sentiment</th>
                    <th className="num">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {stocks.slice(0, 50).map((s) => {
                    const lab = sentimentLabel(s.compositeScore);
                    return (
                      <tr key={s.symbol} onClick={() => setSelectedSymbol(s.symbol)}
                          style={{ cursor: 'pointer' }}>
                        <td><span className="strong">{s.symbol}</span></td>
                        <td><span className={`badge ${lab.cls}`}>{lab.label}</span></td>
                        <td className="num mono tnum">
                          {s.compositeScore != null ? s.compositeScore.toFixed(2) : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </>
    );
  }
  return <SocialInsights symbol={selectedSymbol} onClose={() => setSelectedSymbol(null)} />;
}

function SocialInsights({ symbol, onClose }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['social-insights', symbol],
    queryFn: () => api.get(`/api/sentiment/social/insights/${symbol}`).then((r) => r.data).catch(() => null),
    enabled: !!symbol,
  });

  const metrics = data?.metrics || null;
  const trends = data?.trends || null;
  const historical = data?.historical || [];

  return (
    <>
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">{symbol} · Social Sentiment</div>
            <div className="card-sub">Reddit · news · search · viral score · 30-day history</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <ArrowLeft size={14} /> Back
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginTop: 'var(--space-4)' }}>
          <AlertCircle size={16} />
          <div>{error.message || 'Failed to load social insights'}</div>
        </div>
      )}

      {isLoading ? <Empty title="Loading social insights…" />
       : !metrics ? <Empty title="No social data" desc={`No social sentiment data for ${symbol}`} />
       : (
        <>
          <div className="grid grid-4" style={{ marginTop: 'var(--space-4)' }}>
            <Stile label="Reddit Sentiment"
                   value={
                     metrics.reddit?.sentiment_score
                       ? `${parseFloat(metrics.reddit.sentiment_score) > 0 ? '+' : ''}${parseFloat(metrics.reddit.sentiment_score).toFixed(3)}`
                       : '—'
                   }
                   sub={`${metrics.reddit?.mention_count ?? 0} mentions`} />
            <Stile label="News Sentiment"
                   value={
                     metrics.news?.sentiment_score
                       ? `${parseFloat(metrics.news.sentiment_score) > 0 ? '+' : ''}${parseFloat(metrics.news.sentiment_score).toFixed(3)}`
                       : '—'
                   }
                   sub={`${metrics.news?.article_count ?? 0} articles`} />
            <Stile label="Search Volume"
                   value={metrics.search?.volume_index ?? '—'}
                   sub={`7d ${metrics.search?.trend_7d_direction ?? ''}${
                     Math.abs(parseFloat(metrics.search?.trend_7d_percent || 0)).toFixed(1)
                   }% · 30d ${metrics.search?.trend_30d_direction ?? ''}${
                     Math.abs(parseFloat(metrics.search?.trend_30d_percent || 0)).toFixed(1)
                   }%`} />
            <Stile label="Social Volume"
                   value={`${metrics.social?.volume ?? 0} posts`}
                   sub={`Viral ${metrics.social?.viral_score
                     ? parseFloat(metrics.social.viral_score).toFixed(2) : '—'}`} />
          </div>

          {trends && (trends.news_sentiment || trends.reddit_sentiment || trends.search_volume) && (
            <div className="card" style={{ marginTop: 'var(--space-4)' }}>
              <div className="card-head">
                <div>
                  <div className="card-title">7-Day vs 30-Day Trend</div>
                  <div className="card-sub">Average comparison</div>
                </div>
              </div>
              <div className="card-body">
                <div className="grid grid-3">
                  {trends.reddit_sentiment && (
                    <TrendStile
                      label={`Reddit ${trends.reddit_sentiment.direction || ''}`}
                      cur={trends.reddit_sentiment.current_avg}
                      prd={trends.reddit_sentiment.period_avg}
                      dp={3}
                    />
                  )}
                  {trends.news_sentiment && (
                    <TrendStile
                      label={`News ${trends.news_sentiment.direction || ''}`}
                      cur={trends.news_sentiment.current_avg}
                      prd={trends.news_sentiment.period_avg}
                      dp={3}
                    />
                  )}
                  {trends.search_volume && (
                    <TrendStile
                      label={`Search ${trends.search_volume.direction || ''}`}
                      cur={trends.search_volume.current_avg}
                      prd={trends.search_volume.period_avg}
                      dp={0}
                    />
                  )}
                </div>
              </div>
            </div>
          )}

          {historical.length > 0 && (
            <div className="card" style={{ marginTop: 'var(--space-4)' }}>
              <div className="card-head">
                <div>
                  <div className="card-title">30-Day Historical Data</div>
                  <div className="card-sub">Daily readings across sources</div>
                </div>
              </div>
              <div className="card-body" style={{ padding: 0 }}>
                <div style={{ maxHeight: 360, overflow: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th className="num">Reddit</th>
                        <th className="num">News</th>
                        <th className="num">Search</th>
                        <th className="num">Viral</th>
                      </tr>
                    </thead>
                    <tbody>
                      {historical.slice(0, 30).map((row, i) => (
                        <tr key={`hist-${row.date}-${i}`}>
                          <td className="t-xs muted">{fmtDate(row.date)}</td>
                          <td className="num mono tnum">
                            {row.reddit_sentiment != null
                              ? parseFloat(row.reddit_sentiment).toFixed(2) : '—'}
                          </td>
                          <td className="num mono tnum">
                            {row.news_sentiment != null
                              ? parseFloat(row.news_sentiment).toFixed(2) : '—'}
                          </td>
                          <td className="num mono tnum">{row.search_volume ?? '—'}</td>
                          <td className="num mono tnum">
                            {row.viral_score != null
                              ? parseFloat(row.viral_score).toFixed(2) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

function TrendStile({ label, cur, prd, dp }) {
  const c = parseFloat(cur);
  const p = parseFloat(prd);
  return (
    <div className="stile">
      <div className="stile-label">{label}</div>
      <div className="stile-value">
        {isNaN(c) ? '—' : c.toFixed(dp)}
      </div>
      <div className="stile-sub">
        30d avg: <span className="mono tnum">{isNaN(p) ? '—' : p.toFixed(dp)}</span>
      </div>
    </div>
  );
}

// ─── new: composite sentiment gauge ─────────────────────────────────────
function CompositeGauge({ gauge }) {
  if (!gauge) {
    return (
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Composite Sentiment Gauge</div>
            <div className="card-sub">Cross-source aggregate (0-100)</div>
          </div>
        </div>
        <div className="card-body"><Empty title="No aggregate sources available" /></div>
      </div>
    );
  }
  const score = gauge.score;
  const tone = score >= 70 ? 'up' : score < 30 ? 'down' : '';
  const color = score >= 70 ? 'var(--success)'
              : score < 30 ? 'var(--danger)'
              : 'var(--amber)';
  const label = score >= 70 ? 'Greed / Bullish'
              : score < 30 ? 'Fear / Bearish'
              : 'Neutral';

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Composite Sentiment Gauge</div>
          <div className="card-sub">Cross-source aggregate · {gauge.components.length} sources</div>
        </div>
      </div>
      <div className="card-body">
        <div className="flex items-center" style={{ justifyContent: 'space-between' }}>
          <div>
            <div className="mono tnum" style={{
              fontSize: 'var(--t-3xl, 32px)', fontWeight: 'var(--w-bold)', color,
            }}>
              {score}
            </div>
            <div className={`badge ${score >= 70 ? 'badge-success'
                                  : score < 30 ? 'badge-danger'
                                  : 'badge-amber'}`}
                 style={{ marginTop: 'var(--space-2)' }}>
              {label}
            </div>
          </div>
          <div style={{ width: '60%', height: 130 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={gauge.components} layout="vertical"
                        margin={{ top: 4, right: 16, left: 4, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" horizontal={false} />
                <XAxis type="number" domain={[0, 100]}
                       tick={{ fill: 'var(--text-3)', fontSize: 10 }} />
                <YAxis type="category" dataKey="name" width={80}
                       tick={{ fill: 'var(--text-3)', fontSize: 10 }} />
                <RechartsTooltip contentStyle={TT_STYLE}
                                 formatter={(v) => [Number(v).toFixed(1), 'Score']} />
                <Bar dataKey="value" radius={[0, 3, 3, 0]} fill="var(--brand)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="bar" style={{ marginTop: 'var(--space-4)' }}>
          <div className="bar-fill" style={{ width: `${score}%`, background: color }} />
        </div>
        <div className="flex items-center justify-between" style={{
          marginTop: 'var(--space-2)', fontSize: 'var(--t-xs)', color: 'var(--text-3)',
        }}>
          <span>0 · Extreme Fear</span>
          <span>50</span>
          <span>100 · Extreme Greed</span>
        </div>
      </div>
    </div>
  );
}

// ─── new: rating funnel ────────────────────────────────────────────────
function RatingFunnel({ data }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) {
    return (
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Analyst Rating Distribution</div>
            <div className="card-sub">Across the universe</div>
          </div>
        </div>
        <div className="card-body"><Empty title="No analyst data" /></div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Analyst Rating Distribution</div>
          <div className="card-sub">{total} symbols by analyst consensus</div>
        </div>
      </div>
      <div className="card-body">
        <div style={{ height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <FunnelChart>
              <RechartsTooltip contentStyle={TT_STYLE}
                               formatter={(v, n) => [`${v} symbols (${((v / total) * 100).toFixed(1)}%)`, n]} />
              <Funnel dataKey="value" data={data} isAnimationActive={false}>
                <LabelList position="right" fill="var(--text-2)" stroke="none"
                           dataKey="name" style={{ fontSize: 11 }} />
                <LabelList position="right" fill="var(--text-3)" stroke="none"
                           dataKey="value" offset={64}
                           style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }} />
                {data.map((d, i) => <Cell key={i} fill={d.fill} />)}
              </Funnel>
            </FunnelChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

// ─── new: change leaders ──────────────────────────────────────────────
function ChangeLeadersCard({ title, rows, tone, setSel }) {
  return (
    <div className="card">
      <div className="card-head">
        <div className="flex items-center gap-2">
          {tone === 'up' ? <TrendingUp size={16} style={{ color: 'var(--success)' }} />
                          : <TrendingDown size={16} style={{ color: 'var(--danger)' }} />}
          <div className="card-title">{title}</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {!rows || rows.length === 0 ? (
          <Empty title="Insufficient history" desc="Need ≥ 7 days of analyst sentiment per symbol" />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="num">7d Δ</th>
                <th className="num">Current</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.symbol} onClick={() => setSel(r.symbol)} style={{ cursor: 'pointer' }}>
                  <td><span className="strong">{r.symbol}</span></td>
                  <td className={`num mono tnum ${r.change > 0 ? 'up' : r.change < 0 ? 'down' : 'muted'}`}>
                    {r.change > 0 ? '+' : ''}{r.change.toFixed(1)} pp
                  </td>
                  <td className="num mono tnum">{r.current.toFixed(1)} pp</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ─── new: contrarian setups ──────────────────────────────────────────
function ContrarianCard({ title, desc, rows, tone, setSel }) {
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">{title}</div>
          <div className="card-sub">{desc}</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {!rows || rows.length === 0 ? (
          <Empty title="No contrarian setups" />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Sector</th>
                <th className="num">Sentiment</th>
                <th className="num">Composite</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.symbol} onClick={() => setSel(r.symbol)} style={{ cursor: 'pointer' }}>
                  <td><span className="strong">{r.symbol}</span></td>
                  <td className="t-xs muted" style={{
                    maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>{r.sector || '—'}</td>
                  <td className={`num mono tnum ${r.analystScore > 0 ? 'up' : 'down'}`}>
                    {r.analystScore.toFixed(2)}
                  </td>
                  <td className="num">
                    <span className={`badge ${r.algoComposite >= 80 ? 'badge-success'
                                            : r.algoComposite >= 60 ? 'badge-cyan'
                                            : r.algoComposite >= 40 ? 'badge-amber'
                                            : 'badge-danger'}`}>
                      {r.algoComposite.toFixed(0)}
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

// ─── new: divergence timeline (universe-wide rolling avg of bull−bear) ─
function DivergenceTimeline({ rows }) {
  const series = useMemo(() => {
    if (!rows || rows.length === 0) return [];
    // Aggregate per date: average of (bull% - bear%) across all symbols
    const byDate = new Map();
    rows.forEach((r) => {
      if (!r.date) return;
      const key = String(r.date).slice(0, 10);
      const score = (Number(r.bull_percent) || 0) - (Number(r.bear_percent) || 0);
      if (!byDate.has(key)) byDate.set(key, { sum: 0, n: 0 });
      const v = byDate.get(key);
      v.sum += score;
      v.n += 1;
    });
    return Array.from(byDate.entries())
      .map(([date, v]) => ({ date, avg: v.sum / v.n }))
      .sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [rows]);

  if (series.length === 0) {
    return (
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Universe Sentiment Trend (90d)</div>
            <div className="card-sub">Average analyst bull% − bear% across all covered symbols</div>
          </div>
        </div>
        <div className="card-body"><Empty title="No history" /></div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Universe Sentiment Trend (90d)</div>
          <div className="card-sub">Average analyst (bull% − bear%) across {rows.length} readings</div>
        </div>
      </div>
      <div className="card-body">
        <div style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
              <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10}
                     tickFormatter={fmtDate} interval="preserveStartEnd" />
              <YAxis stroke="var(--text-3)" fontSize={10}
                     tickFormatter={(v) => `${Math.round(v)}`} />
              <RechartsTooltip contentStyle={TT_STYLE}
                               labelFormatter={(d) => fmtDate(d)}
                               formatter={(v) => [`${Number(v).toFixed(2)} pp`, 'Bull − Bear']} />
              <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="avg" stroke="var(--brand)"
                    strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

function Tabs({ tabs, value, onChange }) {
  return (
    <div className="flex items-center gap-2"
         style={{ marginTop: 'var(--space-4)', borderBottom: '1px solid var(--border-soft)' }}>
      {tabs.map((t) => (
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

function Kpi({ label, value, sub }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="eyebrow">{label}</div>
      <div className="mono"
           style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
        {value}
      </div>
      {sub && <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>{sub}</div>}
    </div>
  );
}

function Stile({ label, value, sub }) {
  return (
    <div className="stile">
      <div className="stile-label">{label}</div>
      <div className="stile-value">{value}</div>
      {sub && <div className="stile-sub">{sub}</div>}
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
