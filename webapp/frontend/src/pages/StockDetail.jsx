/**
 * Stock Detail — institutional-grade per-symbol research view (/app/stock/:symbol).
 *
 * Tabs: Chart · Statistics · Algo · Financials · Analysts · Signals
 *
 * All real data; sections are dropped (not mocked) when an endpoint is missing.
 *
 * Pure JSX + theme.css classes (no MUI). Recharts for charts, theme tokens for color.
 */

import React, { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ResponsiveContainer, ComposedChart, Area, Line, Bar, Scatter, XAxis, YAxis,
  CartesianGrid, Tooltip as RTooltip, LineChart, BarChart, PieChart, Pie, Cell,
  ReferenceLine,
} from 'recharts';
import { ArrowLeft, RefreshCw, Inbox, TrendingUp, Activity, Target, Briefcase, BarChart3, Users } from 'lucide-react';
import { api } from '../services/api';

// ─── format helpers ─────────────────────────────────────────────────────────
const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);
const fmtMoney = (v) => v == null || isNaN(Number(v)) ? '—' : `$${Number(v).toFixed(2)}`;
const fmtPct = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : `${Number(v).toFixed(dp)}%`;
const fmtBig = (v) => {
  if (v == null || isNaN(Number(v))) return '—';
  const n = Number(v);
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3)  return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
};
const fmtVol = (v) => {
  if (v == null || isNaN(Number(v))) return '—';
  const n = Math.abs(Number(v));
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return `${n.toFixed(0)}`;
};
const sigClass = (v) => v == null || isNaN(Number(v)) ? 'flat' : Number(v) > 0 ? 'up' : Number(v) < 0 ? 'down' : 'flat';

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
  color: 'var(--text)',
};

// Compute SMAs over a price series
function computeSMA(series, period) {
  const out = new Array(series.length).fill(null);
  let sum = 0;
  for (let i = 0; i < series.length; i++) {
    sum += series[i].close;
    if (i >= period) sum -= series[i - period].close;
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

// Compute RSI (14-period default, Wilder)
function computeRSI(series, period = 14) {
  const out = new Array(series.length).fill(null);
  if (series.length < period + 1) return out;
  let gain = 0, loss = 0;
  for (let i = 1; i <= period; i++) {
    const ch = series[i].close - series[i - 1].close;
    if (ch > 0) gain += ch; else loss -= ch;
  }
  gain /= period; loss /= period;
  out[period] = 100 - (100 / (1 + gain / (loss || 1e-9)));
  for (let i = period + 1; i < series.length; i++) {
    const ch = series[i].close - series[i - 1].close;
    const g = ch > 0 ? ch : 0;
    const l = ch < 0 ? -ch : 0;
    gain = (gain * (period - 1) + g) / period;
    loss = (loss * (period - 1) + l) / period;
    out[i] = 100 - (100 / (1 + gain / (loss || 1e-9)));
  }
  return out;
}

// ─── Page ────────────────────────────────────────────────────────────────────
export default function StockDetail() {
  const { symbol } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState('chart');
  const [tf, setTf] = useState('6M'); // chart timeframe
  const [smaToggles, setSmaToggles] = useState({ sma20: true, sma50: true, sma200: true });

  // History limit by timeframe
  const histLimit = { '1M': 30, '3M': 65, '6M': 130, '1Y': 260, '5Y': 1260, 'All': 5200 }[tf] || 130;

  // ── Queries ──
  const { data: priceData, isLoading: priceLoading, refetch: refetchPrice } = useQuery({
    queryKey: ['stock-price', symbol, histLimit],
    queryFn: () => api.get(`/api/prices/history/${symbol}?timeframe=daily&limit=${histLimit}`)
      .then(r => r.data?.data?.items || r.data?.items || []),
    enabled: !!symbol,
    refetchInterval: 60_000,
  });

  const { data: profileData } = useQuery({
    queryKey: ['stock-profile', symbol],
    queryFn: () => api.get(`/api/stocks/${symbol}`).then(r => r.data?.data || r.data).catch(() => null),
    enabled: !!symbol,
  });

  // Scores w/ all factor inputs (single-symbol path triggers full enrichment)
  const { data: scoreRow } = useQuery({
    queryKey: ['stock-scores-detail', symbol],
    queryFn: async () => {
      const r = await api.get(`/api/scores/stockscores?symbol=${symbol}&limit=1`);
      const items = r.data?.data || r.data?.items || [];
      return items[0] || null;
    },
    enabled: !!symbol,
    refetchInterval: 60_000,
  });

  // Key metrics (sector/industry + market cap + ownership %)
  const { data: keyMetricsData } = useQuery({
    queryKey: ['stock-keymetrics', symbol],
    queryFn: () => api.get(`/api/financials/${symbol}/key-metrics`)
      .then(r => r.data?.data || r.data).catch(() => null),
    enabled: !!symbol,
  });

  // Signals (last 60d)
  const { data: signalsData } = useQuery({
    queryKey: ['stock-signals', symbol],
    queryFn: () => api.get(`/api/signals/stocks?symbol=${symbol}&timeframe=daily&limit=60`)
      .then(r => r.data?.items || r.data?.data || []).catch(() => []),
    enabled: !!symbol,
    refetchInterval: 60_000,
  });

  // Algo swing-score (full eval)
  const { data: swingScore } = useQuery({
    queryKey: ['stock-swing-score', symbol],
    queryFn: async () => {
      const r = await api.get(`/api/algo/swing-scores?limit=2000`).catch(() => null);
      const items = r?.data?.items || [];
      return items.find(it => it.symbol === symbol.toUpperCase()) || null;
    },
    enabled: !!symbol,
    refetchInterval: 60_000,
  });

  // Analyst sentiment
  const { data: analystData } = useQuery({
    queryKey: ['stock-analyst', symbol],
    queryFn: () => api.get(`/api/sentiment/analyst/insights/${symbol}`)
      .then(r => r.data?.data || r.data).catch(() => null),
    enabled: !!symbol,
  });

  // Income statement
  const { data: incomeData } = useQuery({
    queryKey: ['stock-income', symbol],
    queryFn: () => api.get(`/api/financials/${symbol}/income-statement?period=quarterly`)
      .then(r => r.data?.data?.financialData || r.data?.financialData || []).catch(() => []),
    enabled: !!symbol,
  });

  // Balance sheet
  const { data: balanceData } = useQuery({
    queryKey: ['stock-balance', symbol],
    queryFn: () => api.get(`/api/financials/${symbol}/balance-sheet?period=quarterly`)
      .then(r => r.data?.data?.financialData || r.data?.financialData || []).catch(() => []),
    enabled: !!symbol,
  });

  // Cash flow
  const { data: cashflowData } = useQuery({
    queryKey: ['stock-cashflow', symbol],
    queryFn: () => api.get(`/api/financials/${symbol}/cash-flow?period=quarterly`)
      .then(r => r.data?.data?.financialData || r.data?.financialData || []).catch(() => []),
    enabled: !!symbol,
  });

  // ── Derived chart series ──
  const priceSeries = useMemo(() => {
    if (!priceData?.length) return [];
    // Backend returns DESC; reverse for ascending.
    const rows = [...priceData].reverse().map(p => ({
      date: String(p.date).slice(0, 10),
      open: parseFloat(p.open),
      high: parseFloat(p.high),
      low:  parseFloat(p.low),
      close: parseFloat(p.close ?? p.adj_close),
      volume: parseFloat(p.volume || 0),
    })).filter(p => !isNaN(p.close));

    const sma20 = computeSMA(rows, 20);
    const sma50 = computeSMA(rows, 50);
    const sma200 = computeSMA(rows, 200);
    const rsi = computeRSI(rows, 14);

    // Map signal dates → marker on the chart
    const sigByDate = new Map();
    (signalsData || []).forEach(s => {
      const d = String(s.signal_triggered_date || s.date).slice(0, 10);
      sigByDate.set(d, s.signal);
    });

    return rows.map((r, i) => {
      const sig = sigByDate.get(r.date);
      return {
        ...r,
        sma20: sma20[i],
        sma50: sma50[i],
        sma200: sma200[i],
        rsi: rsi[i],
        // Position the marker just below the bar (BUY) or above the bar (SELL)
        buyMarker: sig === 'BUY' ? r.low * 0.985 : null,
        sellMarker: sig === 'SELL' ? r.high * 1.015 : null,
      };
    });
  }, [priceData, signalsData]);

  // ── Hero KPIs ──
  const last = priceSeries[priceSeries.length - 1];
  const prev = priceSeries[priceSeries.length - 2];
  const yearAgo = priceSeries[Math.max(0, priceSeries.length - 252)];
  const dayChg = last && prev ? ((last.close - prev.close) / prev.close) * 100 : null;
  const yearChg = last && yearAgo ? ((last.close - yearAgo.close) / yearAgo.close) * 100 : null;
  const high52 = useMemo(() => {
    if (!priceSeries.length) return null;
    const window = priceSeries.slice(-252);
    return window.reduce((m, p) => Math.max(m, p.high || p.close || 0), 0) || null;
  }, [priceSeries]);
  const low52 = useMemo(() => {
    if (!priceSeries.length) return null;
    const window = priceSeries.slice(-252);
    return window.reduce((m, p) => Math.min(m, p.low || p.close || Infinity), Infinity) || null;
  }, [priceSeries]);
  const distFromHigh = last && high52 ? ((last.close - high52) / high52) * 100 : null;

  // Derive identity (name/sector/industry/market_cap from key_metrics endpoint)
  const km = keyMetricsData?.metricsData || {};
  const companyInfo = km['Company Info']?.metrics || {};
  const valuation = km['Valuation']?.metrics || {};
  const ownership = km['Ownership']?.metrics || {};
  const profile = profileData || {};
  const companyName = companyInfo.Name || companyInfo['Full Name'] || profile.name || symbol;
  const sector = companyInfo.Sector || profile.sector || null;
  const industry = companyInfo.Industry || profile.industry || null;
  const marketCap = valuation['Market Cap'] || profile.market_cap || null;

  return (
    <div className="main-content">
      <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)} style={{ marginBottom: 8 }}>
        <ArrowLeft size={14} /> Back
      </button>

      {/* Sticky Hero header */}
      <div
        className="card"
        style={{
          borderLeft: '3px solid var(--brand)',
          padding: 'var(--space-5) var(--space-6)',
          position: 'sticky',
          top: 0,
          zIndex: 5,
          backdropFilter: 'blur(8px)',
        }}
      >
        <div
          className="grid"
          style={{
            gridTemplateColumns: '2.2fr 1fr 1fr 1fr 1fr 1fr',
            gap: 'var(--space-4)',
            alignItems: 'center',
          }}
        >
          <div>
            <div
              style={{
                fontSize: 'var(--t-3xl)',
                fontWeight: 'var(--w-extra)',
                letterSpacing: '-0.025em',
                color: 'var(--text)',
                lineHeight: 1,
              }}
            >
              {symbol}
            </div>
            <div className="muted t-sm" style={{ marginTop: 4, maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {companyName}
            </div>
            <div className="flex gap-2" style={{ marginTop: 8, flexWrap: 'wrap' }}>
              {sector && <span className="badge badge-brand">{sector}</span>}
              {industry && <span className="badge">{industry}</span>}
              {swingScore?.grade && (
                <span className={`badge ${
                  ['A+', 'A'].includes(swingScore.grade) ? 'badge-success'
                  : swingScore.grade === 'B' ? 'badge-cyan'
                  : swingScore.grade === 'C' ? 'badge-amber'
                  : 'badge-danger'
                }`}>{swingScore.grade}</span>
              )}
            </div>
          </div>
          <HeroStat label="Last" value={fmtMoney(last?.close)} sub={
            dayChg != null ? <span className={`mono tnum ${sigClass(dayChg)}`}>{dayChg >= 0 ? '+' : ''}{num(dayChg, 2)}%</span> : null
          } />
          <HeroStat label="1y Return" value={
            <span className={`mono tnum ${sigClass(yearChg)}`}>{yearChg != null ? (yearChg >= 0 ? '+' : '') + num(yearChg, 1) + '%' : '—'}</span>
          } />
          <HeroStat label="Market Cap" value={fmtBig(marketCap)} />
          <HeroStat label="52w High" value={fmtMoney(high52)} sub={
            distFromHigh != null ? <span className={`mono tnum ${sigClass(distFromHigh)}`}>{num(distFromHigh, 1)}%</span> : null
          } />
          <HeroStat label="Composite" value={
            scoreRow?.composite_score != null ? (
              <span className="mono tnum">{Number(scoreRow.composite_score).toFixed(1)}</span>
            ) : '—'
          } sub={<span className="muted t-xs">/ 100</span>} />
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginTop: 'var(--space-4)', gap: 0, overflowX: 'auto' }}>
        {[
          ['chart', 'Chart'],
          ['stats', 'Statistics'],
          ['algo', 'Algo'],
          ['financials', 'Financials'],
          ['analysts', 'Analysts'],
          ['signals', `Signals${signalsData?.length ? ` (${signalsData.length})` : ''}`],
        ].map(([v, l]) => (
          <button
            key={v}
            type="button"
            onClick={() => setTab(v)}
            style={{
              background: 'transparent', border: 'none',
              borderBottom: `2px solid ${tab === v ? 'var(--brand)' : 'transparent'}`,
              color: tab === v ? 'var(--brand-2)' : 'var(--text-muted)',
              fontWeight: tab === v ? 'var(--w-semibold)' : 'var(--w-medium)',
              fontSize: 'var(--t-sm)', padding: '12px 18px', cursor: 'pointer', marginBottom: -1, whiteSpace: 'nowrap',
            }}
          >{l}</button>
        ))}
      </div>

      <div style={{ marginTop: 'var(--space-4)' }}>
        {tab === 'chart' && (
          <ChartTab
            series={priceSeries}
            loading={priceLoading}
            tf={tf} setTf={setTf}
            smaToggles={smaToggles} setSmaToggles={setSmaToggles}
            refetch={refetchPrice}
          />
        )}
        {tab === 'stats' && (
          <StatsTab scoreRow={scoreRow} ownership={ownership} marketCap={marketCap}
                    high52={high52} low52={low52} last={last?.close} />
        )}
        {tab === 'algo' && <AlgoTab swing={swingScore} scoreRow={scoreRow} />}
        {tab === 'financials' && (
          <FinancialsTab income={incomeData} balance={balanceData} cashflow={cashflowData} />
        )}
        {tab === 'analysts' && <AnalystsTab data={analystData} last={last?.close} />}
        {tab === 'signals' && <SignalsTab signals={signalsData} />}
      </div>
    </div>
  );
}

// ─── Hero stat tile (compact) ──────────────────────────────────────────────
function HeroStat({ label, value, sub }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className="mono tnum" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 4, lineHeight: 1.1 }}>
        {value}
      </div>
      {sub && <div className="t-xs" style={{ marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

// ─── Chart tab ──────────────────────────────────────────────────────────────
function ChartTab({ series, loading, tf, setTf, smaToggles, setSmaToggles, refetch }) {
  const TFs = ['1M', '3M', '6M', '1Y', '5Y', 'All'];
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Price · {tf}</div>
          <div className="card-sub">SMA overlays · volume · RSI · BUY/SELL signal markers</div>
        </div>
        <div className="card-actions" style={{ flexWrap: 'wrap', gap: 'var(--space-2)' }}>
          <div className="flex gap-1" style={{ background: 'var(--bg-2)', padding: 2, borderRadius: 'var(--r-sm)' }}>
            {TFs.map(v => (
              <button key={v} type="button" onClick={() => setTf(v)}
                className="t-xs mono"
                style={{
                  padding: '4px 10px', cursor: 'pointer',
                  background: tf === v ? 'var(--brand)' : 'transparent',
                  color: tf === v ? 'var(--text-on-brand)' : 'var(--text-2)',
                  border: 'none', borderRadius: 'var(--r-xs)',
                  fontWeight: tf === v ? 'var(--w-bold)' : 'var(--w-medium)',
                }}>{v}</button>
            ))}
          </div>
          <div className="flex gap-1">
            {[['sma20', 'SMA20', 'var(--cyan)'], ['sma50', 'SMA50', 'var(--amber)'], ['sma200', 'SMA200', 'var(--purple)']].map(([k, l, c]) => (
              <button key={k} type="button" onClick={() => setSmaToggles(s => ({ ...s, [k]: !s[k] }))}
                className="t-xs"
                style={{
                  padding: '4px 8px', cursor: 'pointer',
                  background: smaToggles[k] ? c : 'transparent',
                  color: smaToggles[k] ? '#0a0c12' : 'var(--text-muted)',
                  border: `1px solid ${smaToggles[k] ? c : 'var(--border-2)'}`,
                  borderRadius: 'var(--r-xs)', fontWeight: 'var(--w-semibold)',
                }}>{l}</button>
            ))}
          </div>
          <button className="btn btn-icon btn-ghost" onClick={() => refetch?.()}><RefreshCw size={14} /></button>
        </div>
      </div>
      <div className="card-body" style={{ padding: 'var(--space-4)' }}>
        {loading ? <Empty title="Loading…" /> : !series.length ? (
          <Empty title="No price data" desc="No history available for this symbol." />
        ) : (
          <>
            <div style={{ height: 380 }}>
              <ResponsiveContainer>
                <ComposedChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                  <defs>
                    <linearGradient id="closeGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--brand-2)" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="var(--brand-2)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-faint)', fontSize: 11 }}
                         tickFormatter={d => String(d).slice(5)} minTickGap={32} />
                  <YAxis yAxisId="price" tick={{ fill: 'var(--text-faint)', fontSize: 11 }}
                         tickFormatter={v => `$${v}`} domain={['auto', 'auto']} width={56} />
                  <YAxis yAxisId="vol" orientation="right" tick={{ fill: 'var(--text-faint)', fontSize: 11 }}
                         tickFormatter={v => fmtVol(v)} width={48} />
                  <RTooltip contentStyle={TOOLTIP_STYLE}
                    formatter={(v, k) => {
                      if (k === 'volume') return [fmtVol(v), 'Vol'];
                      if (typeof v === 'number') return [fmtMoney(v), k];
                      return [v, k];
                    }} />
                  <Bar yAxisId="vol" dataKey="volume" fill="var(--border-2)" opacity={0.55} />
                  <Area yAxisId="price" type="monotone" dataKey="close" name="Close"
                    stroke="var(--brand-2)" strokeWidth={2} fill="url(#closeGrad)" />
                  {smaToggles.sma20 && <Line yAxisId="price" type="monotone" dataKey="sma20" name="SMA20"
                    stroke="var(--cyan)" strokeWidth={1.2} dot={false} isAnimationActive={false} />}
                  {smaToggles.sma50 && <Line yAxisId="price" type="monotone" dataKey="sma50" name="SMA50"
                    stroke="var(--amber)" strokeWidth={1.2} dot={false} isAnimationActive={false} />}
                  {smaToggles.sma200 && <Line yAxisId="price" type="monotone" dataKey="sma200" name="SMA200"
                    stroke="var(--purple)" strokeWidth={1.2} dot={false} isAnimationActive={false} />}
                  {/* BUY/SELL markers as scatter triangles */}
                  <Scatter yAxisId="price" dataKey="buyMarker" name="BUY"
                    fill="var(--success)" shape={<Triangle dir="up" />} isAnimationActive={false} />
                  <Scatter yAxisId="price" dataKey="sellMarker" name="SELL"
                    fill="var(--danger)" shape={<Triangle dir="down" />} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* RSI subpanel */}
            <div style={{ height: 110, marginTop: 'var(--space-3)' }}>
              <ResponsiveContainer>
                <LineChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                  <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-faint)', fontSize: 10 }}
                         tickFormatter={d => String(d).slice(5)} minTickGap={32} />
                  <YAxis tick={{ fill: 'var(--text-faint)', fontSize: 10 }} domain={[0, 100]} width={32} />
                  <ReferenceLine y={70} stroke="var(--danger)" strokeDasharray="2 3" />
                  <ReferenceLine y={30} stroke="var(--success)" strokeDasharray="2 3" />
                  <ReferenceLine y={50} stroke="var(--border-2)" strokeDasharray="1 2" />
                  <RTooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [num(v, 1), 'RSI']} />
                  <Line type="monotone" dataKey="rsi" stroke="var(--brand)" strokeWidth={1.4} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// Custom triangle marker for Scatter
function Triangle({ cx, cy, fill, dir }) {
  if (cx == null || cy == null) return null;
  const s = 6;
  const path = dir === 'up'
    ? `M${cx},${cy + s} L${cx - s},${cy} L${cx + s},${cy} Z`
    : `M${cx},${cy - s} L${cx - s},${cy} L${cx + s},${cy} Z`;
  return <path d={path} fill={fill} stroke={fill} strokeWidth={1} opacity={0.95} />;
}

// ─── Statistics tab ────────────────────────────────────────────────────────
function StatsTab({ scoreRow, ownership, marketCap, high52, low52, last }) {
  const v = scoreRow?.value_inputs || {};
  const q = scoreRow?.quality_inputs || {};
  const m = scoreRow?.momentum_inputs || {};
  const s = scoreRow?.stability_inputs || {};
  const p = scoreRow?.positioning_inputs || {};

  const distHigh = last && high52 ? ((last - high52) / high52) * 100 : null;
  const distLow = last && low52 ? ((last - low52) / low52) * 100 : null;

  const tiles = [
    ['Market Cap', fmtBig(marketCap)],
    ['P/E (TTM)', num(v.stock_pe ?? v.trailing_pe, 2)],
    ['Forward P/E', num(v.stock_forward_pe ?? v.forward_pe, 2)],
    ['P/S (TTM)', num(v.stock_ps ?? v.price_to_sales_ttm, 2)],
    ['P/B', num(v.stock_pb ?? v.price_to_book, 2)],
    ['EV / EBITDA', num(v.stock_ev_ebitda ?? v.ev_to_ebitda, 2)],
    ['EV / Revenue', num(v.stock_ev_revenue ?? v.ev_to_revenue, 2)],
    ['PEG', num(v.peg_ratio, 2)],
    ['Dividend Yield', v.stock_dividend_yield != null ? fmtPct(Number(v.stock_dividend_yield) * 100, 2) : (v.dividend_yield != null ? fmtPct(Number(v.dividend_yield) * 100, 2) : '—')],
    ['Payout Ratio', q.payout_ratio != null ? fmtPct(Number(q.payout_ratio) * 100, 1) : '—'],
    ['ROE', q.return_on_equity_pct != null ? fmtPct(q.return_on_equity_pct, 1) : '—'],
    ['ROA', q.return_on_assets_pct != null ? fmtPct(q.return_on_assets_pct, 1) : '—'],
    ['Gross Margin', q.gross_margin_pct != null ? fmtPct(q.gross_margin_pct, 1) : '—'],
    ['Op Margin', q.operating_margin_pct != null ? fmtPct(q.operating_margin_pct, 1) : '—'],
    ['Net Margin', q.profit_margin_pct != null ? fmtPct(q.profit_margin_pct, 1) : '—'],
    ['Debt / Equity', num(q.debt_to_equity, 2)],
    ['Current Ratio', num(q.current_ratio, 2)],
    ['Beta (12m)', num(s.beta, 2)],
    ['Volatility (12m)', s.volatility_12m != null ? fmtPct(s.volatility_12m, 1) : '—'],
    ['Max DD (52w)', s.max_drawdown_52w != null ? fmtPct(s.max_drawdown_52w, 1) : '—'],
    ['RSI (14)', num(scoreRow?.rsi ?? m.rsi, 1)],
    ['52w High', fmtMoney(high52)],
    ['52w Low', fmtMoney(low52)],
    ['Dist from High', distHigh != null ? fmtPct(distHigh, 1) : '—'],
    ['Dist from Low',  distLow  != null ? fmtPct(distLow,  1) : '—'],
    ['Inst Ownership', p.institutional_ownership_pct != null ? fmtPct(p.institutional_ownership_pct, 1) : (ownership['Institutional Ownership %'] != null ? fmtPct(Number(ownership['Institutional Ownership %']) * 100, 1) : '—')],
    ['Insider Ownership', p.insider_ownership_pct != null ? fmtPct(p.insider_ownership_pct, 1) : (ownership['Insider Ownership %'] != null ? fmtPct(Number(ownership['Insider Ownership %']) * 100, 1) : '—')],
    ['Short Float', p.short_percent_of_float != null ? fmtPct(p.short_percent_of_float, 1) : '—'],
    ['Short Ratio (DTC)', num(p.short_ratio, 2)],
  ];

  return (
    <>
      <div className="card card-pad">
        <div className="grid grid-4">
          {tiles.map(([label, val]) => (
            <div className="stile" key={label}>
              <div className="stile-label">{label}</div>
              <div className="stile-value">{val}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Composite Score Breakdown</div>
            <div className="card-sub">7 factors driving the master composite score</div>
          </div>
        </div>
        <div className="card-body">
          {!scoreRow ? <Empty title="No scores" /> : <ScoreBars scores={scoreRow} />}
        </div>
      </div>
    </>
  );
}

function ScoreBars({ scores }) {
  const items = [
    ['Composite', scores.composite_score],
    ['Quality', scores.quality_score],
    ['Momentum', scores.momentum_score],
    ['Value', scores.value_score],
    ['Growth', scores.growth_score],
    ['Stability', scores.stability_score],
    ['Positioning', scores.positioning_score],
  ];
  return (
    <div className="flex flex-col" style={{ gap: 'var(--space-3)' }}>
      {items.map(([label, value]) => {
        const v = value == null ? null : Number(value);
        const pct = v == null ? 0 : Math.max(0, Math.min(100, v));
        const fillClass = v == null ? '' : v >= 80 ? 'success' : v >= 60 ? '' : v >= 40 ? 'warn' : 'danger';
        return (
          <div key={label}>
            <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
              <span className="eyebrow">{label}</span>
              <span className="mono tnum t-sm strong">{v == null ? '—' : v.toFixed(1)}</span>
            </div>
            <div className="bar"><div className={`bar-fill ${fillClass}`} style={{ width: `${pct}%` }} /></div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Algo tab ──────────────────────────────────────────────────────────────
function AlgoTab({ swing, scoreRow }) {
  if (!swing) {
    return <Empty wrap title="No algo evaluation" desc="Stock not in latest swing-trader scoring run." />;
  }
  const c = swing.components || {};
  const d = swing.details || {};

  const radarRows = [
    ['Setup', c.setup, 25],
    ['Trend', c.trend, 20],
    ['Momentum', c.momentum, 15],
    ['Volume', c.volume, 10],
    ['Fundamentals', c.fundamentals, 15],
    ['Sector', c.sector, 8],
    ['Multi-TF', c.multi_tf, 7],
  ];

  return (
    <div className="grid grid-2">
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Swing Score · {num(swing.swing_score, 1)} / 100</div>
            <div className="card-sub">Eval {String(swing.eval_date).slice(0,10)} · Grade {swing.grade}</div>
          </div>
          <div className="card-actions">
            <span className={`badge badge-lg ${swing.pass_gates ? 'badge-success' : 'badge-danger'}`}>
              {swing.pass_gates ? 'PASS GATES' : 'GATED OUT'}
            </span>
          </div>
        </div>
        <div className="card-body">
          {!swing.pass_gates && swing.fail_reason && (
            <div className="alert alert-warn" style={{ marginBottom: 'var(--space-4)' }}>
              <div><strong>Why gated:</strong> <span className="muted">{swing.fail_reason}</span></div>
            </div>
          )}
          <div className="flex flex-col" style={{ gap: 'var(--space-3)' }}>
            {radarRows.map(([label, pts, max]) => {
              const v = pts == null ? null : Number(pts);
              const pct = v == null ? 0 : Math.max(0, Math.min(100, (v / max) * 100));
              return (
                <div key={label}>
                  <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
                    <span className="eyebrow">{label}</span>
                    <span className="mono tnum t-sm strong">{v == null ? '—' : v.toFixed(1)} / {max}</span>
                  </div>
                  <div className="bar"><div className="bar-fill" style={{ width: `${pct}%` }} /></div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Algo Snapshot</div>
            <div className="card-sub">Trend template · stage · RS · momentum context</div>
          </div>
        </div>
        <div className="card-body">
          <div className="grid grid-2">
            <Stile label="Trend Template (Minervini)" value={d.trend_template_score != null ? `${num(d.trend_template_score, 0)} / 8` : '—'}
              sub={d.trend_template_status || ''} />
            <Stile label="Weinstein Stage" value={d.weinstein_stage ?? d.stage ?? '—'}
              sub={d.stage_substage || ''} />
            <Stile label="Mansfield RS" value={num(d.mansfield_rs, 2)} sub="vs market" />
            <Stile label="RS Rating (IBD)" value={d.rs_rating != null ? `${d.rs_rating}` : '—'} sub="0-99 percentile" />
            <Stile label="Industry Rank" value={swing.industry || '—'} sub={swing.sector || ''} />
            <Stile label="Composite Score" value={scoreRow?.composite_score != null ? num(scoreRow.composite_score, 1) : '—'} sub="research-weighted" />
          </div>
          {d.notes && (
            <div className="alert alert-info" style={{ marginTop: 'var(--space-4)' }}>
              <div className="t-sm">{d.notes}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Financials tab ────────────────────────────────────────────────────────
function FinancialsTab({ income, balance, cashflow }) {
  const inc = (income || []).slice(0, 8).reverse();
  const bs  = (balance || []).slice(0, 8).reverse();
  const cf  = (cashflow || []).slice(0, 8).reverse();

  // Build joined quarterly series for charts
  const series = useMemo(() => {
    const byKey = {};
    const periodKey = (r) => `${r.fiscal_year}${r.fiscal_quarter ? `Q${r.fiscal_quarter}` : ''}`;
    inc.forEach(r => {
      const k = periodKey(r);
      byKey[k] = byKey[k] || { period: k };
      const rev = num1(r.total_revenue ?? r.revenue);
      const gp = num1(r.gross_profit);
      const op = num1(r.operating_income);
      const ni = num1(r.net_income);
      byKey[k].revenue = rev;
      if (rev) {
        if (gp != null) byKey[k].gross_margin = (gp / rev) * 100;
        if (op != null) byKey[k].op_margin = (op / rev) * 100;
        if (ni != null) byKey[k].net_margin = (ni / rev) * 100;
      }
      byKey[k].net_income = ni;
    });
    cf.forEach(r => {
      const k = periodKey(r);
      byKey[k] = byKey[k] || { period: k };
      const fcf = num1(r.free_cash_flow ?? (num1(r.operating_cash_flow) != null && num1(r.capital_expenditure) != null
        ? (num1(r.operating_cash_flow) + num1(r.capital_expenditure)) : null));
      byKey[k].fcf = fcf;
      if (byKey[k].revenue && fcf != null) byKey[k].fcf_margin = (fcf / byKey[k].revenue) * 100;
    });
    bs.forEach(r => {
      const k = periodKey(r);
      byKey[k] = byKey[k] || { period: k };
      const eq = num1(r.total_stockholder_equity ?? r.stockholders_equity);
      const debt = num1(r.total_debt ?? r.long_term_debt);
      if (eq && debt != null) byKey[k].de_ratio = debt / eq;
    });
    return Object.values(byKey).sort((a, b) => String(a.period).localeCompare(String(b.period)));
  }, [income, balance, cashflow]);

  if (!series.length) {
    return <Empty wrap title="No financials" desc="No income / balance / cash flow data found." />;
  }

  return (
    <div className="grid grid-2">
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Revenue · Quarterly</div>
            <div className="card-sub">{series.length} periods</div>
          </div>
        </div>
        <div className="card-body">
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={series} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="period" tick={{ fill: 'var(--text-faint)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--text-faint)', fontSize: 11 }} tickFormatter={(v) => fmtBig(v)} width={56} />
                <RTooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => fmtBig(v)} />
                <Bar dataKey="revenue" fill="var(--brand)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Margins · Quarterly</div>
            <div className="card-sub">Gross / Operating / Net / FCF</div>
          </div>
        </div>
        <div className="card-body">
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={series} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="period" tick={{ fill: 'var(--text-faint)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--text-faint)', fontSize: 11 }} tickFormatter={(v) => `${num(v, 0)}%`} width={48} />
                <RTooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => fmtPct(v, 1)} />
                <Line type="monotone" dataKey="gross_margin" name="Gross" stroke="var(--cyan)" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="op_margin" name="Op" stroke="var(--brand-2)" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="net_margin" name="Net" stroke="var(--success)" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="fcf_margin" name="FCF" stroke="var(--purple)" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card" style={{ gridColumn: 'span 2' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Quarterly Statements Summary</div>
            <div className="card-sub">Up to 8 most recent quarters</div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0, overflow: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Period</th>
                <th className="num">Revenue</th>
                <th className="num">Net Income</th>
                <th className="num">Gross %</th>
                <th className="num">Op %</th>
                <th className="num">Net %</th>
                <th className="num">FCF</th>
                <th className="num">FCF %</th>
                <th className="num">D/E</th>
              </tr>
            </thead>
            <tbody>
              {series.slice().reverse().map((s, i) => (
                <tr key={i}>
                  <td><span className="strong">{s.period}</span></td>
                  <td className="num mono tnum">{fmtBig(s.revenue)}</td>
                  <td className="num"><span className={`mono tnum ${sigClass(s.net_income)}`}>{fmtBig(s.net_income)}</span></td>
                  <td className="num mono tnum">{s.gross_margin != null ? fmtPct(s.gross_margin, 1) : '—'}</td>
                  <td className="num mono tnum">{s.op_margin != null ? fmtPct(s.op_margin, 1) : '—'}</td>
                  <td className="num mono tnum">{s.net_margin != null ? fmtPct(s.net_margin, 1) : '—'}</td>
                  <td className="num mono tnum">{fmtBig(s.fcf)}</td>
                  <td className="num mono tnum">{s.fcf_margin != null ? fmtPct(s.fcf_margin, 1) : '—'}</td>
                  <td className="num mono tnum">{num(s.de_ratio, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function num1(v) {
  if (v == null) return null;
  const n = Number(v);
  return isNaN(n) ? null : n;
}

// ─── Analysts tab ──────────────────────────────────────────────────────────
function AnalystsTab({ data, last }) {
  if (!data || (data.analyst_count ?? 0) === 0) {
    return <Empty wrap title="No analyst coverage data" desc="No analyst sentiment found for this symbol." />;
  }
  const target = data.target_price != null ? Number(data.target_price) : null;
  const upside = data.upside_downside_percent != null ? Number(data.upside_downside_percent) : null;

  const dist = [
    { name: 'Bullish', value: Number(data.bullish_count || 0), color: 'var(--success)' },
    { name: 'Neutral', value: Number(data.neutral_count || 0), color: 'var(--amber)' },
    { name: 'Bearish', value: Number(data.bearish_count || 0), color: 'var(--danger)' },
  ];

  return (
    <div className="grid grid-2">
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Analyst Coverage</div>
            <div className="card-sub">Consensus · {data.analyst_count} analysts</div>
          </div>
          <div className="card-actions">
            <span className={`badge badge-lg ${
              data.consensus === 'buy' ? 'badge-success'
              : data.consensus === 'sell' ? 'badge-danger'
              : 'badge-amber'
            }`}>{(data.consensus || 'hold').toUpperCase()}</span>
          </div>
        </div>
        <div className="card-body">
          <div style={{ height: 220 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={dist} dataKey="value" nameKey="name" cx="50%" cy="50%"
                     innerRadius={50} outerRadius={80} stroke="none">
                  {dist.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Pie>
                <RTooltip contentStyle={TOOLTIP_STYLE} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-3" style={{ marginTop: 'var(--space-3)' }}>
            <Stile label="Bullish" value={
              <span className="mono tnum up">{data.bullish_count} ({num(data.bullish_percent, 0)}%)</span>
            } />
            <Stile label="Neutral" value={
              <span className="mono tnum">{data.neutral_count} ({num(data.neutral_percent, 0)}%)</span>
            } />
            <Stile label="Bearish" value={
              <span className="mono tnum down">{data.bearish_count} ({num(data.bearish_percent, 0)}%)</span>
            } />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Price Target</div>
            <div className="card-sub">Implied upside vs current</div>
          </div>
        </div>
        <div className="card-body">
          <div className="grid grid-2">
            <Stile label="Current" value={fmtMoney(last ?? data.current_price)} />
            <Stile label="Avg Target" value={fmtMoney(target)} />
            <Stile label="Upside / Downside" value={
              <span className={`mono tnum ${sigClass(upside)}`}>{upside != null ? `${upside >= 0 ? '+' : ''}${num(upside, 1)}%` : '—'}</span>
            } sub="vs current price" />
            <Stile label="Coverage" value={`${data.analyst_count} analysts`} sub={data.date ? `as of ${String(data.date).slice(0,10)}` : ''} />
          </div>

          {target && last && (
            <div style={{ marginTop: 'var(--space-4)' }}>
              <div className="flex items-center justify-between" style={{ marginBottom: 6 }}>
                <span className="eyebrow">Current → Target</span>
                <span className="mono tnum t-sm">
                  {fmtMoney(last)} → {fmtMoney(target)}
                </span>
              </div>
              <div className="bar" style={{ height: 8 }}>
                <div className={`bar-fill ${upside > 0 ? 'success' : 'danger'}`}
                  style={{ width: `${Math.min(100, Math.abs(upside || 0))}%` }} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Signals tab ───────────────────────────────────────────────────────────
function SignalsTab({ signals }) {
  if (!signals?.length) return <Empty wrap title="No signals" desc="No buy/sell signals in the last 60 sessions" />;
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Recent Signals · {signals.length}</div>
          <div className="card-sub">Pine Script BUY/SELL events with full context</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0, overflow: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Signal</th>
              <th className="num">Close</th>
              <th className="num">Buy Lvl</th>
              <th className="num">Stop</th>
              <th>Stage</th>
              <th>Base Type</th>
              <th className="num">RS</th>
              <th className="num">R/R</th>
              <th className="num">RSI</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s, i) => (
              <tr key={i}>
                <td><span className="mono t-xs">{String(s.signal_triggered_date || s.date).slice(0, 10)}</span></td>
                <td>
                  <span className={`badge ${s.signal === 'BUY' ? 'badge-success' : 'badge-danger'}`}>{s.signal}</span>
                </td>
                <td className="num mono tnum">{fmtMoney(s.close)}</td>
                <td className="num mono tnum">{s.buylevel ? fmtMoney(s.buylevel) : '—'}</td>
                <td className="num mono tnum">{s.stoplevel ? fmtMoney(s.stoplevel) : '—'}</td>
                <td>{s.market_stage ? <span className="badge">{s.market_stage}</span> : <span className="muted t-xs">—</span>}</td>
                <td><span className="t-xs muted">{s.base_type || '—'}</span></td>
                <td className="num mono tnum">{s.rs_rating ?? '—'}</td>
                <td className="num mono tnum">{s.risk_reward_ratio ? Number(s.risk_reward_ratio).toFixed(2) : '—'}</td>
                <td className="num mono tnum">{num(s.rsi, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── shared little components ──────────────────────────────────────────────
function Stile({ label, value, sub }) {
  return (
    <div className="stile">
      <div className="stile-label">{label}</div>
      <div className="stile-value">{value}</div>
      {sub && <div className="stile-sub">{sub}</div>}
    </div>
  );
}

function Empty({ title, desc, wrap }) {
  const inner = (
    <div className="empty">
      <Inbox />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
  return wrap ? <div className="card card-pad">{inner}</div> : inner;
}
