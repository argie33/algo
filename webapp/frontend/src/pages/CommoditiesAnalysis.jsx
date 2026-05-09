/**
 * Commodities Intelligence — prices, technicals, macro drivers, events, seasonality.
 * Pure JSX + theme.css classes.
 */

import React, { useState, useMemo } from 'react';
import { RefreshCw, Inbox, AlertCircle, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import {
  LineChart, Line, BarChart, Bar, ComposedChart, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts';
import { useCommodities } from '../hooks/useDataApi';
import { useApiQuery } from '../hooks/useApiQuery';
import { extractData } from '../utils/responseNormalizer';
import { api } from '../services/api';

const fmtMoney = (v) =>
  v == null || isNaN(Number(v)) ? '—' : `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const pct = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : `${Number(v).toFixed(dp)}%`;
const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);

const TT_STYLE = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)', fontSize: 'var(--t-xs)', padding: 'var(--space-2) var(--space-3)',
};

const TABS = [
  { value: 'overview',    label: 'Overview' },
  { value: 'technicals',  label: 'Technicals' },
  { value: 'cot',         label: 'COT Positioning' },
  { value: 'correlations',label: 'Correlations' },
  { value: 'macro',       label: 'Macro Drivers' },
  { value: 'events',      label: 'Events' },
  { value: 'seasonality', label: 'Seasonality' },
];

export default function CommoditiesAnalysis() {
  const [tab, setTab] = useState('overview');
  const [selectedSymbol, setSelectedSymbol] = useState('GC=F');
  const [filterCategory, setFilterCategory] = useState('all');

  // Use domain-specific hooks instead of manual useQuery
  const prices = useCommodities({ limit: 100 });

  const cats = useApiQuery(
    ['commodities-categories'],
    () => api.get('/api/commodities/categories'),
    { staleTime: 5 * 60 * 1000 }
  );

  const technicals = useApiQuery(
    ['commodities-technicals', selectedSymbol],
    () => api.get(`/api/commodities/technicals/${selectedSymbol}`),
    { enabled: tab === 'technicals' }
  );

  const macro = useApiQuery(
    ['commodities-macro'],
    () => api.get('/api/commodities/macro'),
    { enabled: tab === 'macro' }
  );

  const events = useApiQuery(
    ['commodities-events'],
    () => api.get('/api/commodities/events'),
    { enabled: tab === 'events' }
  );

  const seasonality = useApiQuery(
    ['commodities-seasonality', selectedSymbol],
    () => api.get(`/api/commodities/seasonality/${selectedSymbol}`),
    { enabled: tab === 'seasonality' }
  );

  const cot = useApiQuery(
    ['commodities-cot', selectedSymbol],
    () => api.get(`/api/commodities/cot/${selectedSymbol}`),
    { enabled: tab === 'cot' }
  );

  const correlations = useApiQuery(
    ['commodities-correlations'],
    () => api.get('/api/commodities/correlations'),
    { enabled: tab === 'correlations' }
  );

  const marketSummary = useApiQuery(
    ['commodities-market-summary'],
    () => api.get('/api/commodities/market-summary'),
    { staleTime: 2 * 60 * 1000 }
  );

  const categories = useMemo(() => {
    if (!cats.data) return [];
    return Array.from(new Set(cats.data.map(c => c.category).filter(Boolean))).sort();
  }, [cats.data]);

  const filteredCommodities = useMemo(() => {
    const list = Array.isArray(prices.data) ? prices.data : [];
    if (filterCategory === 'all') return list;
    return list.filter(p => {
      const cat = cats.data?.find(c => c.symbol === p.symbol);
      return cat?.category === filterCategory;
    });
  }, [prices.data, cats.data, filterCategory]);

  const selectedData = useMemo(
    () => (prices.data || []).find(c => c.symbol === selectedSymbol),
    [prices.data, selectedSymbol]
  );
  const selectedCat = useMemo(
    () => cats.data?.find(c => c.symbol === selectedSymbol),
    [cats.data, selectedSymbol]
  );

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Commodities</div>
          <div className="page-head-sub">Prices · Technicals · Macro drivers · Events · Seasonality</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={() => prices.refetch()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-4">
        <Kpi label="Active Commodities" value={filteredCommodities.length} />
        <Kpi label="Categories" value={categories.length} />
        <Kpi label="Selected"
             value={<span className="mono">{selectedSymbol}</span>}
             sub={selectedCat?.category} />
        <Kpi label="Last Update" value={new Date().toLocaleTimeString()} sub="auto-refresh 2 min" />
      </div>

      {/* Market summary — top gainers / losers */}
      {marketSummary.data && (
        <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card">
            <div className="card-head"><div><div className="card-title">Top Gainers</div></div></div>
            <div className="card-body" style={{ padding: 0 }}>
              <table className="data-table">
                <thead><tr><th>Symbol</th><th>Name</th><th className="num">Chg %</th><th className="num">Price</th></tr></thead>
                <tbody>
                  {(marketSummary.data.topGainers || []).map(c => (
                    <tr key={c.symbol} onClick={() => setSelectedSymbol(c.symbol)} style={{ cursor: 'pointer' }}>
                      <td className="strong">{c.symbol}</td>
                      <td>{c.name}</td>
                      <td className="num mono tnum up"><ArrowUpRight size={11} style={{ verticalAlign: '-2px' }} /> {pct(c.change)}</td>
                      <td className="num mono tnum">{fmtMoney(c.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="card">
            <div className="card-head"><div><div className="card-title">Top Losers</div></div></div>
            <div className="card-body" style={{ padding: 0 }}>
              <table className="data-table">
                <thead><tr><th>Symbol</th><th>Name</th><th className="num">Chg %</th><th className="num">Price</th></tr></thead>
                <tbody>
                  {(marketSummary.data.topLosers || []).map(c => (
                    <tr key={c.symbol} onClick={() => setSelectedSymbol(c.symbol)} style={{ cursor: 'pointer' }}>
                      <td className="strong">{c.symbol}</td>
                      <td>{c.name}</td>
                      <td className="num mono tnum down"><ArrowDownRight size={11} style={{ verticalAlign: '-2px' }} /> {pct(Math.abs(c.change))}</td>
                      <td className="num mono tnum">{fmtMoney(c.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      <Tabs tabs={TABS} value={tab} onChange={setTab} />

      <div style={{ marginTop: 'var(--space-4)' }}>
        {tab === 'overview' && (
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">Overview</div>
                <div className="card-sub">Click a row to drill into technicals</div>
              </div>
              <select className="select" value={filterCategory}
                      onChange={(e) => setFilterCategory(e.target.value)}>
                <option value="all">All categories</option>
                {categories.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              {prices.loading ? <Empty title="Loading commodities…" /> :
               filteredCommodities.length === 0 ? <Empty title="No commodities" /> : (
                <div style={{ overflow: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th>Name</th>
                        <th>Category</th>
                        <th className="num">Price</th>
                        <th className="num">Change %</th>
                        <th className="num">52W High</th>
                        <th className="num">52W Low</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredCommodities.map(c => {
                        const cat = cats.data?.find(x => x.symbol === c.symbol);
                        const ch = Number(c.change_percent) || 0;
                        return (
                          <tr key={c.symbol}
                              onClick={() => { setSelectedSymbol(c.symbol); setTab('technicals'); }}
                              style={{ cursor: 'pointer',
                                       background: c.symbol === selectedSymbol ? 'var(--brand-soft)' : undefined }}>
                            <td><span className="strong">{c.symbol}</span></td>
                            <td>{c.name}</td>
                            <td><span className="badge">{cat?.category || '—'}</span></td>
                            <td className="num mono tnum">{fmtMoney(c.price)}</td>
                            <td className="num">
                              <span className={`mono tnum ${ch >= 0 ? 'up' : 'down'}`}>
                                {ch >= 0 ? <ArrowUpRight size={11} style={{ verticalAlign: '-2px' }} /> : <ArrowDownRight size={11} style={{ verticalAlign: '-2px' }} />}
                                {' '}{pct(ch)}
                              </span>
                            </td>
                            <td className="num mono tnum muted">{fmtMoney(c.high_52w)}</td>
                            <td className="num mono tnum muted">{fmtMoney(c.low_52w)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === 'technicals' && (
          <TechnicalsView data={technicals.data} loading={technicals.isLoading}
                          symbol={selectedSymbol} symbolData={selectedData} category={selectedCat} />
        )}

        {tab === 'cot' && (
          <CotView data={cot.data} loading={cot.isLoading} symbol={selectedSymbol} symbolData={selectedData} />
        )}

        {tab === 'correlations' && (
          <CorrelationsView data={correlations.data} loading={correlations.isLoading} onSelect={(sym) => { setSelectedSymbol(sym); setTab('technicals'); }} />
        )}

        {tab === 'macro' && (
          macro.isLoading ? <Empty title="Loading macro drivers…" /> :
          (!macro.data || macro.data.length === 0) ? <Empty title="No macro drivers loaded" /> : (
            <div className="grid grid-2">
              {macro.data.map(s => (
                <div className="card" key={s.seriesId}>
                  <div className="card-head">
                    <div>
                      <div className="card-title">{s.seriesName}</div>
                      <div className="card-sub">
                        Latest: {s.history?.[s.history.length - 1]?.value ?? '—'}
                      </div>
                    </div>
                  </div>
                  <div className="card-body" style={{ height: 220 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={s.history || []} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                        <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11} />
                        <YAxis stroke="var(--text-3)" fontSize={11} />
                        <Tooltip contentStyle={TT_STYLE} />
                        <Line type="monotone" dataKey="value" stroke="var(--brand)" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              ))}
            </div>
          )
        )}

        {tab === 'events' && (
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">Economic Event Calendar</div>
                <div className="card-sub">Upcoming reports and releases</div>
              </div>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              {events.isLoading ? <Empty title="Loading events…" /> :
               (!events.data || events.data.length === 0) ? <Empty title="No upcoming events" /> : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date & Time</th>
                      <th>Event</th>
                      <th>Type</th>
                      <th>Description</th>
                      <th>Impact</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.data.slice(0, 30).map((e, i) => (
                      <tr key={i}>
                        <td className="t-xs muted">{new Date(e.date).toLocaleString()}</td>
                        <td><span className="strong">{e.name}</span></td>
                        <td><span className="badge">{e.type}</span></td>
                        <td className="t-xs">{e.description}</td>
                        <td>
                          <span className={`badge ${e.impact === 'CRITICAL' ? 'badge-danger' : e.impact === 'HIGH' ? 'badge-amber' : ''}`}>
                            {e.impact}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {tab === 'seasonality' && (
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">{selectedData?.name || selectedSymbol} Seasonality</div>
                <div className="card-sub">Average monthly return</div>
              </div>
            </div>
            <div className="card-body" style={{ height: 320 }}>
              {seasonality.isLoading ? <Empty title="Loading seasonality…" /> :
               (!seasonality.data || seasonality.data.length === 0) ?
                  <Empty title="No seasonality data available" /> : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={seasonality.data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                    <XAxis dataKey="monthName" stroke="var(--text-3)" fontSize={11} />
                    <YAxis stroke="var(--text-3)" fontSize={11}
                           tickFormatter={(v) => `${v}%`} />
                    <Tooltip contentStyle={TT_STYLE} formatter={(v) => [pct(v), 'Avg Return']} />
                    <Bar dataKey="avgReturn">
                      {seasonality.data.map((d, i) => (
                        <Cell key={i} fill={d.avgReturn > 0 ? 'var(--success)' : 'var(--danger)'}
                              fillOpacity={0.85} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Technicals view ───────────────────────────────────────────────────────
function TechnicalsView({ data, loading, symbol, symbolData, category }) {
  if (loading) return <Empty title="Loading technicals…" />;
  if (!symbolData) return <Empty title="Select a commodity from Overview" />;
  const hasTech = Array.isArray(data) && data.length > 0;

  return (
    <>
      {/* Header card */}
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">{symbolData.name} ({symbol})</div>
            <div className="card-sub">{category?.category || 'Unknown'} · {category?.exchange || '—'}</div>
          </div>
        </div>
        <div className="card-body">
          <div className="grid grid-4">
            <Stile label="Current Price" value={<span className="mono tnum">{fmtMoney(symbolData.price)}</span>} />
            <Stile label="24h Change"
                   value={<span className={`mono tnum ${symbolData.change_percent >= 0 ? 'up' : 'down'}`}>
                     {pct(symbolData.change_percent)}</span>} />
            <Stile label="52W High" value={<span className="mono tnum">{fmtMoney(symbolData.high_52w)}</span>} />
            <Stile label="52W Low" value={<span className="mono tnum">{fmtMoney(symbolData.low_52w)}</span>} />
          </div>
        </div>
      </div>

      {!hasTech ? (
        <div style={{ marginTop: 'var(--space-4)' }}>
          <Empty title="No technicals data" desc="This commodity has no computed technicals yet." />
        </div>
      ) : (
        <>
          <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
            <div className="card">
              <div className="card-head">
                <div>
                  <div className="card-title">RSI (14)</div>
                  <div className="card-sub">Overbought &gt;70 · Oversold &lt;30</div>
                </div>
              </div>
              <div className="card-body" style={{ height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                    <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11} />
                    <YAxis domain={[0, 100]} stroke="var(--text-3)" fontSize={11} />
                    <Tooltip contentStyle={TT_STYLE} />
                    <ReferenceLine y={70} stroke="var(--danger)" strokeDasharray="3 3" />
                    <ReferenceLine y={30} stroke="var(--success)" strokeDasharray="3 3" />
                    <Line type="monotone" dataKey="rsi" stroke="var(--brand)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card">
              <div className="card-head">
                <div>
                  <div className="card-title">MACD</div>
                  <div className="card-sub">Histogram + signal line crossovers</div>
                </div>
              </div>
              <div className="card-body" style={{ height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                    <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11} />
                    <YAxis stroke="var(--text-3)" fontSize={11} />
                    <Tooltip contentStyle={TT_STYLE} />
                    <Bar dataKey="macdHist">
                      {data.map((e, i) => (
                        <Cell key={i} fill={e.macdHist > 0 ? 'var(--success)' : 'var(--danger)'} fillOpacity={0.7} />
                      ))}
                    </Bar>
                    <Line type="monotone" dataKey="macd" stroke="var(--amber)" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="macdSignal" stroke="var(--cyan)" strokeWidth={2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 'var(--space-4)' }}>
            <div className="card-head">
              <div>
                <div className="card-title">Price &amp; Moving Averages</div>
                <div className="card-sub">SMA 20 / 50 / 200</div>
              </div>
            </div>
            <div className="card-body" style={{ height: 320 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                  <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11} />
                  <YAxis stroke="var(--text-3)" fontSize={11} />
                  <Tooltip contentStyle={TT_STYLE} />
                  <Legend />
                  <Line type="monotone" dataKey="sma20" stroke="var(--amber)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="sma50" stroke="var(--brand)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="sma200" stroke="var(--success)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </>
  );
}

// ─── shared ────────────────────────────────────────────────────────────────
function Tabs({ tabs, value, onChange }) {
  return (
    <div className="flex items-center gap-2" style={{ marginTop: 'var(--space-4)', borderBottom: '1px solid var(--border-soft)' }}>
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

function Kpi({ label, value, sub }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="eyebrow">{label}</div>
      <div className="mono" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
        {value}
      </div>
      {sub && <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>{sub}</div>}
    </div>
  );
}

function Stile({ label, value }) {
  return (
    <div className="stile">
      <div className="stile-label">{label}</div>
      <div className="stile-value">{value}</div>
    </div>
  );
}

// ─── COT (Commitment of Traders) ──────────────────────────────────────────
function CotView({ data, loading, symbol, symbolData }) {
  if (loading) return <Empty title="Loading COT data…" />;
  if (!data) return <Empty title="Select a commodity and wait for data" desc="COT data sourced from CFTC weekly reports." />;

  const history = data.cotHistory || [];
  const analysis = data.analysis || {};
  const sentColor = (s) => s === 'bullish' ? 'up' : s === 'bearish' ? 'down' : '';

  return (
    <>
      {/* Header */}
      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">{data.commodityName || symbol} — Commitment of Traders</div>
            <div className="card-sub">CFTC positioning data · Latest: {data.latestReportDate || '—'}</div>
          </div>
        </div>
        <div className="card-body">
          <div className="grid grid-4">
            <Stile label="Commercial Sentiment"
              value={<span className={sentColor(analysis.commercialSentiment)}>{analysis.commercialSentiment || '—'}</span>} />
            <Stile label="Speculator Sentiment"
              value={<span className={sentColor(analysis.speculatorSentiment)}>{analysis.speculatorSentiment || '—'}</span>} />
            <Stile label="Divergence" value={analysis.divergence || '—'} />
            <Stile label="Commercial Net"
              value={<span className={analysis.latestCommercialNet > 0 ? 'up' : 'down'}>
                {analysis.latestCommercialNet != null ? analysis.latestCommercialNet.toLocaleString() : '—'}
              </span>} />
          </div>
          <div className="t-xs muted" style={{ marginTop: 'var(--space-3)' }}>
            Commercials (hedgers) are "smart money" — when they are net long, prices tend to rise.
            Non-commercials (speculators/funds) follow momentum and can signal overcrowded trades.
          </div>
        </div>
      </div>

      {/* COT net positioning chart */}
      {history.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
          <div className="card-head">
            <div>
              <div className="card-title">Net Positioning History</div>
              <div className="card-sub">Commercial net (hedgers) vs Non-commercial net (speculators) — weekly CFTC</div>
            </div>
          </div>
          <div className="card-body" style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={history} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="reportDate" stroke="var(--text-3)" fontSize={10} interval="preserveStartEnd"
                  tickFormatter={d => d ? new Date(d).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) : ''} />
                <YAxis stroke="var(--text-3)" fontSize={10} tickFormatter={v => v?.toLocaleString()} />
                <Tooltip contentStyle={TT_STYLE}
                  formatter={(v, n) => [v?.toLocaleString(), n === 'commercial.net' ? 'Commercial Net' : 'Speculator Net']} />
                <Legend wrapperStyle={{ fontSize: 11 }}
                  formatter={n => n === 'commercialNet' ? 'Commercial (Hedgers)' : 'Non-Commercial (Speculators)'} />
                <ReferenceLine y={0} stroke="var(--border-2)" strokeDasharray="3 3" />
                <Bar dataKey="commercial.net" name="commercialNet" fill="var(--brand)" fillOpacity={0.6} />
                <Line type="monotone" dataKey="nonCommercial.net" name="nonCommercialNet"
                  stroke="var(--amber)" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Open interest */}
      {history.length > 0 && (
        <div className="card">
          <div className="card-head"><div><div className="card-title">Open Interest</div><div className="card-sub">Total outstanding contracts</div></div></div>
          <div className="card-body" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="oiGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--purple)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--purple)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="reportDate" stroke="var(--text-3)" fontSize={10} interval="preserveStartEnd"
                  tickFormatter={d => d ? new Date(d).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) : ''} />
                <YAxis stroke="var(--text-3)" fontSize={10} tickFormatter={v => v?.toLocaleString()} />
                <Tooltip contentStyle={TT_STYLE} formatter={v => [v?.toLocaleString(), 'Open Interest']} />
                <Area type="monotone" dataKey="openInterest" stroke="var(--purple)" strokeWidth={2} fill="url(#oiGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Correlations ──────────────────────────────────────────────────────────
function CorrelationsView({ data, loading, onSelect }) {
  if (loading) return <Empty title="Computing correlations…" />;
  if (!data?.correlations?.length) return <Empty title="No correlation data" desc="Requires price history for multiple commodities." />;

  const correlations = data.correlations || [];
  const corrColor = (c) => {
    const abs = Math.abs(c);
    if (abs >= 0.8) return c > 0 ? '#22c55e' : '#ef4444';
    if (abs >= 0.5) return c > 0 ? '#86efac' : '#fca5a5';
    return 'var(--text-muted)';
  };

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Commodity Correlations</div>
          <div className="card-sub">
            {data.timeframe} rolling correlation · min |r| = {data.minCorrelation} ·
            Strong &gt; 0.8 · Moderate 0.5–0.8
          </div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Pair</th>
              <th>Symbol 1</th>
              <th>Symbol 2</th>
              <th className="num">Correlation</th>
              <th>Strength</th>
              <th>Direction</th>
            </tr>
          </thead>
          <tbody>
            {correlations.map((r, i) => (
              <tr key={i}>
                <td><span className="strong">{r.pair}</span></td>
                <td>
                  <button className="btn btn-ghost btn-sm" onClick={() => onSelect(r.symbol1)}
                    style={{ padding: '2px 6px' }}>
                    {r.symbol1}
                  </button>
                </td>
                <td>
                  <button className="btn btn-ghost btn-sm" onClick={() => onSelect(r.symbol2)}
                    style={{ padding: '2px 6px' }}>
                    {r.symbol2}
                  </button>
                </td>
                <td className="num mono tnum" style={{ color: corrColor(r.coefficient), fontWeight: 'var(--w-semibold)' }}>
                  {r.coefficient != null ? r.coefficient.toFixed(3) : '—'}
                </td>
                <td>
                  <span className={`badge ${Math.abs(r.coefficient) >= 0.8 ? 'badge-danger' : Math.abs(r.coefficient) >= 0.5 ? 'badge-amber' : ''}`}>
                    {r.strength || '—'}
                  </span>
                </td>
                <td className={r.coefficient > 0 ? 'up' : 'down'}>
                  {r.coefficient > 0 ? 'Positive' : 'Negative'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
