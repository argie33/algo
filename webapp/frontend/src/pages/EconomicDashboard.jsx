import React, { useMemo, useState } from 'react';
import {
  RefreshCw, TrendingUp, TrendingDown, Minus, Activity,
  AlertCircle, Inbox, CalendarDays, BarChart2, Zap, DollarSign, Home,
} from 'lucide-react';
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar, ComposedChart,
  XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip,
  ReferenceLine, Legend, Cell,
} from 'recharts';
import { useApiQuery } from '../hooks/useApiQuery';
import { api } from '../services/api';

const TT = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)', fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

const num   = (v, dp = 2) => (v == null || isNaN(+v)) ? '—' : (+v).toFixed(dp);
const pct   = (v, dp = 2) => (v == null || isNaN(+v)) ? '—' : `${(+v).toFixed(dp)}%`;
const bps   = (v)         => (v == null || isNaN(+v)) ? '—' : `${Math.round(+v * 100)} bps`;
const fmtD  = (s)         => s ? new Date(s).toLocaleDateString() : '—';
const fmtM  = (s)         => s ? new Date(s).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) : '';
const up    = (v)         => v > 0 ? 'up' : v < 0 ? 'down' : 'flat';

const TABS = [
  { id: 'overview',  label: 'Overview',       icon: <BarChart2 size={13} /> },
  { id: 'cycle',     label: 'Business Cycle', icon: <Activity size={13} /> },
  { id: 'rates',     label: 'Rates & Fed',    icon: <DollarSign size={13} /> },
  { id: 'labor',     label: 'Labor Market',   icon: <Activity size={13} /> },
  { id: 'inflation', label: 'Inflation',      icon: <TrendingUp size={13} /> },
  { id: 'growth',    label: 'Growth',         icon: <Zap size={13} /> },
  { id: 'housing',   label: 'Housing & Consumer', icon: <Home size={13} /> },
  { id: 'calendar',  label: 'Calendar',       icon: <CalendarDays size={13} /> },
];

// ── Regime computation ───────────────────────────────────────────────────────
function deriveRegime(indicators, yieldData, recessionProb) {
  const gdp    = indicators.find(i => i.name === 'GDP Growth');
  const unrate = indicators.find(i => i.name === 'Unemployment Rate');
  const indpro = indicators.find(i => i.name === 'Industrial Production');
  const spread = yieldData?.spreads?.T10Y2Y;

  const gdpVal    = gdp?.rawValue;
  const unrateVal = unrate?.rawValue;
  const indproTrend = indpro?.trend;

  if (recessionProb != null && recessionProb >= 60)
    return { label: 'Contraction Risk', color: 'var(--danger)', desc: 'Multiple recession signals active — risk-off positioning warranted.' };
  if (recessionProb != null && recessionProb >= 35)
    return { label: 'Late Cycle', color: 'var(--amber)', desc: 'Growth slowing, credit tightening. Monitor leading indicators closely.' };
  if (spread != null && spread < 0 && (unrateVal ?? 5) < 5)
    return { label: 'Late Cycle', color: 'var(--amber)', desc: 'Curve inverted but labor still resilient. Historically within 6–18 months of peak.' };
  if (gdpVal != null && gdpVal > 0 && indproTrend !== 'down')
    return { label: 'Expansion', color: 'var(--success)', desc: 'Broad-based growth with improving fundamentals. Risk appetite supported.' };
  return { label: 'Uncertain', color: 'var(--text-muted)', desc: 'Mixed signals — maintain balanced positioning.' };
}

export default function EconomicDashboard() {
  const [tab, setTab] = useState('overview');

  const leadQ  = useApiQuery(['economic-leading'],   () => api.get('/api/economic/leading-indicators'), { refetchInterval: 120000 });
  const yldQ   = useApiQuery(['economic-yield'],     () => api.get('/api/economic/yield-curve-full'),   { refetchInterval: 120000 });
  const calQ   = useApiQuery(['economic-calendar'],  () => api.get('/api/economic/calendar'),           { refetchInterval: 120000 });
  const naaimQ = useApiQuery(['market-naaim'],       () => api.get('/api/market/naaim'),                { refetchInterval: 120000 });

  const isLoading = leadQ.loading || yldQ.loading;
  const refetch   = () => { leadQ.refetch(); yldQ.refetch(); calQ.refetch(); naaimQ.refetch(); };

  const leading    = leadQ.data   || {};
  const yieldData  = yldQ.data    || null;
  const indicators = leading.indicators || [];
  const calRaw     = calQ.data?.events ?? (Array.isArray(calQ.data) ? calQ.data : []);
  const naaimData  = naaimQ.data  || null;

  // helper to find indicator by partial name
  const ind = (name) => indicators.find(i => (i.name || '').toLowerCase().includes(name.toLowerCase()));

  // ── Recession nowcasting ──────────────────────────────────────────────────
  const recession = useMemo(() => {
    const tiles = [];
    const unrate = ind('Unemployment Rate');
    if (unrate?.history?.length >= 12) {
      const hist = unrate.history.slice(-12).map(p => +p.value).filter(v => !isNaN(v));
      if (hist.length >= 3) {
        const sahm = hist.slice(-3).reduce((s, v) => s + v, 0) / 3 - Math.min(...hist);
        tiles.push({
          label: 'Sahm Rule', value: `${sahm >= 0 ? '+' : ''}${sahm.toFixed(2)} pp`,
          threshold: '≥ 0.50 triggers', desc: '3-mo unemployment MA vs trailing 12-mo low',
          status: sahm >= 0.5 ? 'red' : sahm >= 0.3 ? 'amber' : 'green',
          weight: sahm >= 0.5 ? 100 : sahm >= 0.3 ? 60 : Math.max(0, sahm * 100),
        });
      }
    }
    const t10y3m = yieldData?.spreads?.T10Y3M;
    const t10y2y = yieldData?.spreads?.T10Y2Y;
    const spread = t10y3m ?? t10y2y;
    if (spread != null) {
      const spr_bps = Math.round(spread * 100);
      tiles.push({
        label: t10y3m != null ? '10Y−3M Curve' : '10Y−2Y Curve',
        value: `${spr_bps >= 0 ? '+' : ''}${spr_bps} bps`,
        threshold: '< 0 inverts', desc: 'Inversion preceded last 8 US recessions',
        status: spread < -0.5 ? 'red' : spread < 0 ? 'amber' : 'green',
        weight: spread < -0.5 ? 100 : spread < 0 ? 70 : Math.max(0, 50 - spread * 25),
      });
    }
    const hyHist = yieldData?.credit?.history?.['BAMLH0A0HYM2'] || [];
    const hyVal  = hyHist.at?.(-1)?.value;
    if (hyVal != null) {
      tiles.push({
        label: 'HY Credit Spread', value: `${(+hyVal).toFixed(2)}%`,
        threshold: '> 5% elevated', desc: 'ICE BofA US High Yield OAS — default risk barometer',
        status: +hyVal > 8 ? 'red' : +hyVal > 5 ? 'amber' : 'green',
        weight: +hyVal > 8 ? 100 : +hyVal > 5 ? 60 : Math.max(0, +hyVal * 10),
      });
    }
    const claims = ind('Jobless Claims') || ind('Initial Claims');
    if (claims?.history?.length >= 26) {
      const cur  = +claims.rawValue;
      const past = +(claims.history.at(-27)?.value ?? 0);
      if (!isNaN(cur) && past > 0) {
        const chg = ((cur - past) / past) * 100;
        tiles.push({
          label: 'Jobless Claims 6m Δ', value: `${chg >= 0 ? '+' : ''}${chg.toFixed(1)}%`,
          threshold: '> +20% warning', desc: '6-month change in initial unemployment claims',
          status: chg > 30 ? 'red' : chg > 20 ? 'amber' : 'green',
          weight: chg > 30 ? 100 : chg > 20 ? 60 : Math.max(0, chg * 2),
        });
      }
    }
    const vixHist = yieldData?.credit?.history?.['VIXCLS'] || [];
    const vixVal  = vixHist.at?.(-1)?.value;
    if (vixVal != null) {
      tiles.push({
        label: 'VIX Volatility', value: (+vixVal).toFixed(1),
        threshold: '> 25 elevated', desc: 'CBOE Volatility Index — equity fear gauge',
        status: +vixVal > 35 ? 'red' : +vixVal > 25 ? 'amber' : 'green',
        weight: +vixVal > 35 ? 100 : +vixVal > 25 ? 60 : Math.max(0, +vixVal * 2),
      });
    }
    const igHist = yieldData?.credit?.history?.['BAMLC0A0CM'] || [];
    const igVal  = igHist.at?.(-1)?.value;
    if (igVal != null) {
      tiles.push({
        label: 'IG Credit Spread', value: `${(+igVal).toFixed(2)}%`,
        threshold: '> 1.5% caution', desc: 'Investment grade OAS — financial stress indicator',
        status: +igVal > 2.5 ? 'red' : +igVal > 1.5 ? 'amber' : 'green',
        weight: +igVal > 2.5 ? 100 : +igVal > 1.5 ? 50 : Math.max(0, +igVal * 20),
      });
    }
    if (!tiles.length) return null;
    const composite = Math.round(tiles.reduce((s, t) => s + t.weight, 0) / tiles.length);
    return { tiles, composite };
  }, [indicators, yieldData]);

  // ── Financial conditions ──────────────────────────────────────────────────
  const fci = useMemo(() => {
    if (!yieldData?.credit?.history) return [];
    const vixSeries  = yieldData.credit.history['VIXCLS'] || [];
    const hySeries   = yieldData.credit.history['BAMLH0A0HYM2'] || [];
    const igSeries   = yieldData.credit.history['BAMLC0A0CM'] || [];
    const curveSeries = (yieldData.history?.T10Y2Y || []);
    if (vixSeries.length < 10 || hySeries.length < 10) return [];
    const map = new Map();
    const addSeries = (series, key) => series.forEach(p => {
      if (!p?.date) return;
      const k = String(p.date).slice(0, 10);
      const cur = map.get(k) || { date: k };
      cur[key] = +p.value;
      map.set(k, cur);
    });
    addSeries(vixSeries, 'vix');
    addSeries(hySeries, 'hy');
    addSeries(igSeries, 'ig');
    addSeries(curveSeries, 'curve');
    const arr = [...map.values()].filter(d => d.vix != null && d.hy != null).sort((a, b) => new Date(a.date) - new Date(b.date));
    if (arr.length === 0) return [];
    const mean = (arr, k) => arr.reduce((s, d) => s + (d[k] ?? 0), 0) / arr.filter(d => d[k] != null).length;
    const sd   = (arr, k, m) => Math.sqrt(arr.filter(d => d[k] != null).reduce((s, d) => s + (d[k] - m) ** 2, 0) / arr.length) || 1;
    const mV = mean(arr, 'vix'); const sV = sd(arr, 'vix', mV);
    const mH = mean(arr, 'hy');  const sH = sd(arr, 'hy', mH);
    const mI = mean(arr, 'ig');  const sI = sd(arr, 'ig', mI);
    return arr.map(d => ({
      date: d.date,
      fci: ((d.vix - mV) / sV) + ((d.hy - mH) / sH) + ((d.ig != null ? (d.ig - mI) / sI : 0)) - (d.curve ?? 0),
    }));
  }, [yieldData]);

  // ── Yield curve ───────────────────────────────────────────────────────────
  const yieldCurve = useMemo(() => {
    if (!yieldData?.currentCurve) return [];
    const order = ['3M', '6M', '1Y', '2Y', '3Y', '5Y', '7Y', '10Y', '20Y', '30Y'];
    return order.filter(k => yieldData.currentCurve[k] != null).map(k => ({
      maturity: k, yield: yieldData.currentCurve[k],
    }));
  }, [yieldData]);

  const spreadHist = useMemo(() => {
    const h = yieldData?.history;
    if (!h) return [];
    const src = h['T10Y2Y'] || h['spread_10y2y'] || [];
    return [...src].sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [yieldData]);

  // ── Regime ────────────────────────────────────────────────────────────────
  const regime = useMemo(() =>
    deriveRegime(indicators, yieldData, recession?.composite),
  [indicators, yieldData, recession]);

  // ── Calendar ──────────────────────────────────────────────────────────────
  const calendar = useMemo(() => {
    if (!Array.isArray(calRaw)) return [];
    return calRaw.map(e => ({
      date: e.event_date || e.date,
      event: e.event_name || e.Event || e.event,
      importance: e.importance || e.Importance,
      forecast: e.forecast_value ?? e.Forecast,
      previous: e.previous_value ?? e.Previous,
      category: e.category || e.Category,
    })).sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [calRaw]);

  const fedRate    = ind('Fed Funds');
  const cpiInd     = ind('CPI') || ind('Inflation');
  const gdpInd     = ind('GDP');
  const unrateInd  = ind('Unemployment');
  const claimsInd  = ind('Jobless') || ind('Initial Claims');
  const payrollInd = ind('Payroll') || ind('Employment');
  const indproInd  = ind('Industrial Production');
  const housingInd = ind('Housing Starts') || ind('Housing');
  const michInd    = ind('Consumer Sentiment') || ind('Michigan');

  return (
    <div className="main-content">
      {/* Header */}
      <div className="page-head">
        <div>
          <div className="page-head-title">Economic Dashboard</div>
          <div className="page-head-sub">Recession models · Credit conditions · Leading indicators · Fed policy</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={refetch} disabled={isLoading}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Error banner */}
      {(leadQ.error || yldQ.error) && (
        <div className="alert alert-danger" style={{ marginBottom: 'var(--space-4)' }}>
          <AlertCircle size={16} />
          <div>{leadQ.error?.message || yldQ.error?.message || 'Failed to load economic data'}</div>
        </div>
      )}

      {/* Cycle Regime Banner */}
      <div className="card" style={{ marginBottom: 'var(--space-4)', borderLeft: `4px solid ${regime.color}` }}>
        <div className="card-body" style={{ padding: 'var(--space-4) var(--space-6)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-6)', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
            <div>
              <div className="eyebrow" style={{ marginBottom: 2 }}>Economic Regime</div>
              <div style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', color: regime.color }}>
                {regime.label}
              </div>
            </div>
            <div className="t-sm" style={{ color: 'var(--text-2)', maxWidth: 380 }}>{regime.desc}</div>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-6)', flexWrap: 'wrap' }}>
            <RegimeStat label="Recession Risk" value={recession?.composite != null ? `${recession.composite}%` : '—'}
              color={recession?.composite >= 60 ? 'var(--danger)' : recession?.composite >= 35 ? 'var(--amber)' : 'var(--success)'} />
            <RegimeStat label="Fed Funds Rate" value={fedRate?.value || '—'} color="var(--brand)" />
            <RegimeStat label="10Y−2Y Spread"
              value={yieldData?.spreads?.T10Y2Y != null ? bps(yieldData.spreads.T10Y2Y) : '—'}
              color={yieldData?.isInverted ? 'var(--danger)' : 'var(--success)'} />
            <RegimeStat label="HY Spread"
              value={(() => { const v = yieldData?.credit?.history?.['BAMLH0A0HYM2']?.at?.(-1)?.value; return v != null ? `${(+v).toFixed(2)}%` : '—'; })()}
              color="var(--text)" />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <TabBar tabs={TABS} value={tab} onChange={setTab} />

      <div style={{ marginTop: 'var(--space-5)' }}>

        {/* ── OVERVIEW ─────────────────────────────────────────────────── */}
        {tab === 'overview' && (
          <>
            {/* Recession nowcasting */}
            {recession && (
              <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
                <div className="card-head">
                  <div>
                    <div className="card-title">Recession Nowcasting Model</div>
                    <div className="card-sub">
                      Composite probability across {recession.tiles.length} indicators — Sahm rule, yield curve, credit spreads, labor stress, vol regime
                    </div>
                  </div>
                  <span className={`badge ${recession.composite >= 60 ? 'badge-danger' : recession.composite >= 35 ? 'badge-amber' : 'badge-success'}`}>
                    {recession.composite}% probability
                  </span>
                </div>
                <div className="card-body">
                  <div className="bar" style={{ marginBottom: 'var(--space-5)', height: 8, borderRadius: 'var(--r-pill)' }}>
                    <div className="bar-fill" style={{
                      width: `${recession.composite}%`,
                      background: recession.composite >= 60 ? 'var(--danger)' : recession.composite >= 35 ? 'var(--amber)' : 'var(--success)',
                      borderRadius: 'var(--r-pill)',
                    }} />
                  </div>
                  <div className="grid grid-3">
                    {recession.tiles.map(t => (
                      <RecessionTile key={t.label} {...t} />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Key macro KPIs */}
            <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>
              <MacroKpi label="GDP Growth" ind={gdpInd} unit="%" />
              <MacroKpi label="Unemployment" ind={unrateInd} unit="%" invertGood />
              <MacroKpi label="CPI (YoY)" ind={cpiInd} unit="%" invertGood />
              <MacroKpi label="Industrial Prod." ind={indproInd} unit="" />
            </div>

            {/* FCI + Spread side by side */}
            <div className="grid grid-2" style={{ marginBottom: 'var(--space-4)' }}>
              {fci.length > 0 && (
                <div className="card">
                  <div className="card-head">
                    <div>
                      <div className="card-title">Financial Conditions Index</div>
                      <div className="card-sub">Z-score: VIX + HY spread + IG spread − yield curve · higher = tighter</div>
                    </div>
                  </div>
                  <div className="card-body" style={{ height: 260 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={fci} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="fciUp" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="var(--danger)" stopOpacity={0.4} />
                            <stop offset="100%" stopColor="var(--danger)" stopOpacity={0} />
                          </linearGradient>
                          <linearGradient id="fciDn" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="var(--success)" stopOpacity={0.3} />
                            <stop offset="100%" stopColor="var(--success)" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                        <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM} interval="preserveStartEnd" />
                        <YAxis stroke="var(--text-3)" fontSize={10} tickFormatter={v => (+v).toFixed(1)} />
                        <Tooltip contentStyle={TT} labelFormatter={fmtD} formatter={v => [`${(+v).toFixed(2)} σ`, 'FCI']} />
                        <ReferenceLine y={0} stroke="var(--border-2)" strokeDasharray="4 4" />
                        <Area type="monotone" dataKey="fci" stroke="var(--purple)" strokeWidth={2}
                          fill={fci.at(-1)?.fci > 0 ? 'url(#fciUp)' : 'url(#fciDn)'} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {spreadHist.length > 0 && (
                <div className="card">
                  <div className="card-head">
                    <div>
                      <div className="card-title">10Y − 2Y Yield Spread</div>
                      <div className="card-sub">Below zero = inverted · preceded last 8 recessions</div>
                    </div>
                    <span className={`badge ${yieldData?.isInverted ? 'badge-danger' : 'badge-success'}`}>
                      {yieldData?.isInverted ? 'INVERTED' : 'NORMAL'}
                    </span>
                  </div>
                  <div className="card-body" style={{ height: 260 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={spreadHist} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="spreadGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.4} />
                            <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                        <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM} interval="preserveStartEnd" />
                        <YAxis stroke="var(--text-3)" fontSize={10} tickFormatter={v => `${Math.round(v * 100)}`} />
                        <Tooltip contentStyle={TT} labelFormatter={fmtD}
                          formatter={v => [`${Math.round(+v * 100)} bps`, 'Spread']} />
                        <ReferenceLine y={0} stroke="var(--danger)" strokeDasharray="4 4" />
                        <Area type="monotone" dataKey="value" stroke="var(--brand)" strokeWidth={2} fill="url(#spreadGrad)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>

            {/* NAAIM professional positioning */}
            {naaimData && <NaaimPanel naaim={naaimData} />}

            {/* Credit spreads history */}
            <CreditSpreadsPanel yieldData={yieldData} />
          </>
        )}

        {/* ── RATES & FED ──────────────────────────────────────────────── */}
        {tab === 'rates' && (
          <>
            <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>
              <MacroKpi label="Fed Funds Rate" ind={fedRate} unit="%" />
              {['3M', '2Y', '10Y', '30Y'].map(k => (
                <div key={k} className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
                  <div className="eyebrow">{k} Treasury</div>
                  <div className="mono" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
                    {yieldData?.currentCurve?.[k] != null ? pct(yieldData.currentCurve[k]) : '—'}
                  </div>
                </div>
              ))}
            </div>

            {/* Yield curve snapshot */}
            {yieldCurve.length > 0 && (
              <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
                <div className="card-head">
                  <div>
                    <div className="card-title">Treasury Yield Curve</div>
                    <div className="card-sub">Current snapshot across all maturities</div>
                  </div>
                  <span className={`badge ${yieldData?.isInverted ? 'badge-danger' : 'badge-success'}`}>
                    {yieldData?.isInverted ? 'INVERTED CURVE' : 'NORMAL CURVE'}
                  </span>
                </div>
                <div className="card-body" style={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={yieldCurve} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                      <XAxis dataKey="maturity" stroke="var(--text-3)" fontSize={11} />
                      <YAxis stroke="var(--text-3)" fontSize={11} domain={[0, 'auto']} tickFormatter={v => `${v}%`} />
                      <Tooltip contentStyle={TT} formatter={v => [`${(+v).toFixed(3)}%`, 'Yield']} />
                      <Line type="monotone" dataKey="yield" stroke="var(--brand)" strokeWidth={2.5}
                        dot={{ fill: 'var(--brand)', r: 4 }} activeDot={{ r: 6 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Fed Funds history */}
            {fedRate && (
              <IndHistory ind={fedRate} title="Federal Funds Rate History"
                sub="Target rate set by FOMC — primary monetary policy tool" color="var(--cyan)" />
            )}

            {/* Spread history */}
            {spreadHist.length > 0 && (
              <div className="card" style={{ marginTop: 'var(--space-4)' }}>
                <div className="card-head">
                  <div>
                    <div className="card-title">10Y − 2Y Yield Spread (Historical)</div>
                    <div className="card-sub">Duration of inversions and recovery shape</div>
                  </div>
                </div>
                <div className="card-body" style={{ height: 280 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={spreadHist} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="spr2" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.4} />
                          <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                      <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM} interval="preserveStartEnd" />
                      <YAxis stroke="var(--text-3)" fontSize={10} tickFormatter={v => `${Math.round(+v * 100)}`} />
                      <Tooltip contentStyle={TT} labelFormatter={fmtD}
                        formatter={v => [`${Math.round(+v * 100)} bps`, 'Spread']} />
                      <ReferenceLine y={0} stroke="var(--danger)" strokeDasharray="4 4" />
                      <Area type="monotone" dataKey="value" stroke="var(--brand)" strokeWidth={2} fill="url(#spr2)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </>
        )}

        {/* ── LABOR MARKET ─────────────────────────────────────────────── */}
        {tab === 'labor' && (
          <>
            <div className="grid grid-3" style={{ marginBottom: 'var(--space-4)' }}>
              <MacroKpi label="Unemployment Rate" ind={unrateInd} unit="%" invertGood />
              <MacroKpi label="Initial Jobless Claims" ind={claimsInd} unit="K" invertGood />
              <MacroKpi label="Non-Farm Payrolls" ind={payrollInd} unit="K" />
            </div>

            {/* Sahm Rule live calculation */}
            {recession?.tiles?.find(t => t.label === 'Sahm Rule') && (
              <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
                <div className="card-head">
                  <div>
                    <div className="card-title">Sahm Rule Indicator</div>
                    <div className="card-sub">Created by ex-Fed economist Claudia Sahm — triggers at +0.50pp rise in unemployment 3-mo MA vs prior year low</div>
                  </div>
                  <RecessionBadge status={recession.tiles.find(t => t.label === 'Sahm Rule').status} />
                </div>
                <div className="card-body">
                  <div className="stile" style={{ maxWidth: 240 }}>
                    <div className="stile-label">Current Reading</div>
                    <div className="stile-value">{recession.tiles.find(t => t.label === 'Sahm Rule').value}</div>
                    <div className="stile-sub muted t-xs">≥ 0.50pp historically signals recession has started</div>
                  </div>
                </div>
              </div>
            )}

            {unrateInd && <IndHistory ind={unrateInd} title="Unemployment Rate" sub="Bureau of Labor Statistics — monthly" color="var(--amber)" />}
            <div style={{ marginTop: 'var(--space-4)' }}>
              {claimsInd && <IndHistory ind={claimsInd} title="Initial Jobless Claims" sub="Weekly new unemployment insurance filings" color="var(--cyan)" />}
            </div>
            {payrollInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={payrollInd} title="Non-Farm Payrolls" sub="Monthly job additions (thousands)" color="var(--success)" /></div>}
          </>
        )}

        {/* ── INFLATION ─────────────────────────────────────────────────── */}
        {tab === 'inflation' && (
          <>
            <div className="grid grid-3" style={{ marginBottom: 'var(--space-4)' }}>
              <MacroKpi label="CPI (YoY)" ind={cpiInd} unit="%" invertGood />
              <MacroKpi label="Fed Funds Rate" ind={fedRate} unit="%" />
              <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
                <div className="eyebrow">Real Rate (10Y − CPI)</div>
                <div className="mono" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
                  {yieldData?.currentCurve?.['10Y'] != null && cpiInd?.rawValue != null
                    ? pct(yieldData.currentCurve['10Y'] - cpiInd.rawValue)
                    : '—'}
                </div>
                <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>Positive = restrictive policy</div>
              </div>
            </div>

            {/* Inflation vs Fed funds overlay */}
            {cpiInd?.history?.length > 0 && fedRate?.history?.length > 0 && (
              <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
                <div className="card-head">
                  <div>
                    <div className="card-title">CPI vs Federal Funds Rate</div>
                    <div className="card-sub">Fed policy relative to inflation — gap signals real rate environment</div>
                  </div>
                </div>
                <div className="card-body" style={{ height: 300 }}>
                  <RateVsInflationChart cpiHist={cpiInd.history} fedHist={fedRate.history} />
                </div>
              </div>
            )}

            {cpiInd && <IndHistory ind={cpiInd} title="CPI Inflation (YoY)" sub="Consumer Price Index — all items" color="var(--danger)" />}
          </>
        )}

        {/* ── BUSINESS CYCLE ────────────────────────────────────────────── */}
        {tab === 'cycle' && (
          <>
            <div className="grid grid_2" style={{ marginBottom: 'var(--space-4)' }}>
              <MacroKpi label="ISM Manufacturing" ind={ind('ISM Manufacturing')} unit="Index" />
              <MacroKpi label="ISM Services" ind={ind('ISM Services')} unit="Index" />
            </div>

            {/* Economic Regime Clock */}
            <EconomicRegimeClock indicators={indicators} yieldData={yieldData} />

            {/* Growth-Labor Barometer */}
            <GrowthLaborBarometer indicators={indicators} />

            {ind('ISM Manufacturing') && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={ind('ISM Manufacturing')} title="ISM Manufacturing PMI" sub="Institute for Supply Management — >50 = expansion, <50 = contraction" color="var(--brand)" /></div>}
            {ind('ISM Services') && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={ind('ISM Services')} title="ISM Services PMI" sub="Non-manufacturing activity index — employment, new orders, prices" color="var(--cyan)" /></div>}
          </>
        )}

        {/* ── GROWTH ─────────────────────────────────────────────────────── */}
        {tab === 'growth' && (
          <>
            <div className="grid grid-3" style={{ marginBottom: 'var(--space-4)' }}>
              <MacroKpi label="GDP Growth" ind={gdpInd} unit="%" />
              <MacroKpi label="Industrial Prod." ind={indproInd} unit="" />
              <MacroKpi label="Business Loans" ind={ind('Business Loans')} unit="B" />
            </div>

            {gdpInd && <IndHistory ind={gdpInd} title="Real GDP Growth" sub="Quarterly annualized real GDP — BEA" color="var(--success)" />}
            {indproInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={indproInd} title="Industrial Production" sub="Federal Reserve industrial output index" color="var(--brand)" /></div>}
          </>
        )}

        {/* ── HOUSING & CONSUMER ───────────────────────────────────────── */}
        {tab === 'housing' && (
          <>
            <div className="grid grid-3" style={{ marginBottom: 'var(--space-4)' }}>
              <MacroKpi label="Housing Starts" ind={housingInd} unit="K" />
              <MacroKpi label="Consumer Sentiment" ind={michInd} unit="" />
              <MacroKpi label="30Y Mortgage Rate" ind={null} unit="%" />
            </div>

            {housingInd && <IndHistory ind={housingInd} title="Housing Starts" sub="New residential construction — Census Bureau (thousands)" color="var(--cyan)" />}
            {michInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={michInd} title="U. Michigan Consumer Sentiment" sub="Monthly consumer survey — leading indicator for spending" color="var(--amber)" /></div>}
          </>
        )}

        {/* ── CALENDAR ──────────────────────────────────────────────────── */}
        {tab === 'calendar' && (
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">Economic Calendar</div>
                <div className="card-sub">Upcoming releases &amp; key events — next 120 days</div>
              </div>
              <CalendarDays size={16} className="muted" />
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              {calQ.loading ? <Empty title="Loading…" /> :
               calendar.length === 0 ? <Empty title="No upcoming events" desc="Run the economic calendar loader." /> : (
                <div style={{ overflow: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Event</th>
                        <th>Category</th>
                        <th>Importance</th>
                        <th className="num">Forecast</th>
                        <th className="num">Previous</th>
                      </tr>
                    </thead>
                    <tbody>
                      {calendar.map((e, i) => (
                        <tr key={i}>
                          <td className="t-xs muted">{fmtD(e.date)}</td>
                          <td><span className="strong">{e.event}</span></td>
                          <td className="t-xs muted">{e.category || '—'}</td>
                          <td>
                            <span className={`badge ${e.importance?.toLowerCase() === 'high' ? 'badge-danger' : e.importance?.toLowerCase() === 'medium' ? 'badge-amber' : ''}`}>
                              {e.importance || '—'}
                            </span>
                          </td>
                          <td className="num mono tnum">{e.forecast ?? '—'}</td>
                          <td className="num mono tnum muted">{e.previous ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function TabBar({ tabs, value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 'var(--space-1)', borderBottom: '1px solid var(--border-soft)', overflowX: 'auto' }}>
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: 'var(--space-3) var(--space-4)',
            border: 'none', borderBottom: value === t.id ? '2px solid var(--brand)' : '2px solid transparent',
            background: 'transparent', cursor: 'pointer',
            color: value === t.id ? 'var(--text)' : 'var(--text-muted)',
            fontWeight: value === t.id ? 'var(--w-semibold)' : 'var(--w-medium)',
            fontSize: 'var(--t-sm)', borderRadius: 0, whiteSpace: 'nowrap',
            transition: 'color var(--t-base)',
          }}>
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  );
}

function RegimeStat({ label, value, color }) {
  return (
    <div>
      <div style={{ fontSize: 'var(--t-2xs)', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)', color: color || 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
    </div>
  );
}

function RecessionTile({ label, value, threshold, desc, status }) {
  const color = status === 'red' ? 'var(--danger)' : status === 'amber' ? 'var(--amber)' : 'var(--success)';
  const badge = status === 'red' ? 'badge-danger' : status === 'amber' ? 'badge-amber' : 'badge-success';
  const label2 = status === 'red' ? 'TRIGGERED' : status === 'amber' ? 'ELEVATED' : 'NORMAL';
  return (
    <div className="stile">
      <div className="stile-label">{label}</div>
      <div className="stile-value" style={{ color }}>{value}</div>
      <div className="stile-sub">
        <span className={`badge ${badge}`}>{label2}</span>{' '}
        <span className="muted">{threshold}</span>
      </div>
      <div className="t-2xs muted" style={{ marginTop: 'var(--space-1)' }}>{desc}</div>
    </div>
  );
}

function RecessionBadge({ status }) {
  const badge = status === 'red' ? 'badge-danger' : status === 'amber' ? 'badge-amber' : 'badge-success';
  const label = status === 'red' ? 'TRIGGERED' : status === 'amber' ? 'ELEVATED' : 'NORMAL';
  return <span className={`badge ${badge}`}>{label}</span>;
}

function MacroKpi({ label, ind, unit, invertGood }) {
  if (!ind) return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="eyebrow">{label}</div>
      <div className="mono" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>—</div>
    </div>
  );
  const tone = invertGood ? (ind.trend === 'up' ? 'down' : ind.trend === 'down' ? 'up' : 'flat') : (ind.trend || 'flat');
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="eyebrow">{label}</div>
      <div className={`mono ${tone}`}
        style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
        {ind.value || '—'}
      </div>
      {ind.change != null && (
        <div className={`t-xs mono ${up(ind.change)}`} style={{ marginTop: 'var(--space-1)' }}>
          {ind.change > 0 ? '+' : ''}{(+ind.change).toFixed(2)}% MoM
        </div>
      )}
    </div>
  );
}

function IndHistory({ ind, title, sub, color }) {
  if (!ind?.history?.length) return null;
  const data = [...ind.history].sort((a, b) => new Date(a.date) - new Date(b.date));
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">{title}</div>
          <div className="card-sub">{sub}</div>
        </div>
        {ind.signal && (
          <span className={`badge ${ind.signal === 'Positive' ? 'badge-success' : ind.signal === 'Negative' ? 'badge-danger' : 'badge-cyan'}`}>
            {ind.signal}
          </span>
        )}
      </div>
      <div className="card-body">
        <div className="stile" style={{ display: 'inline-block', marginBottom: 'var(--space-4)' }}>
          <div className="stile-label">Latest</div>
          <div className="stile-value">{ind.value}</div>
          {ind.date && <div className="t-2xs muted">{fmtD(ind.date)}</div>}
        </div>
        <div style={{ height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`grad-${title.replace(/\s+/g, '')}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color || 'var(--brand)'} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={color || 'var(--brand)'} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM}
                interval={Math.max(0, Math.floor(data.length / 6))} />
              <YAxis stroke="var(--text-3)" fontSize={10} width={50} />
              <Tooltip contentStyle={TT} labelFormatter={fmtD}
                formatter={v => [v != null ? (+v).toFixed(2) : '—', title]} />
              <Area type="monotone" dataKey="value" stroke={color || 'var(--brand)'}
                strokeWidth={2} fill={`url(#grad-${title.replace(/\s+/g, '')})`} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

function CreditSpreadsPanel({ yieldData }) {
  const credit = yieldData?.credit;
  if (!credit?.currentSpreads && !credit?.history) return null;
  const hyHist = credit?.history?.['BAMLH0A0HYM2'] || [];
  const igHist = credit?.history?.['BAMLC0A0CM'] || [];
  if (!hyHist.length && !igHist.length) return null;
  const combined = (() => {
    const map = new Map();
    hyHist.forEach(p => { const k = String(p.date).slice(0, 10); const cur = map.get(k) || { date: k }; cur.hy = +p.value; map.set(k, cur); });
    igHist.forEach(p => { const k = String(p.date).slice(0, 10); const cur = map.get(k) || { date: k }; cur.ig = +p.value; map.set(k, cur); });
    return [...map.values()].sort((a, b) => new Date(a.date) - new Date(b.date));
  })();
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Credit Spread Monitor</div>
          <div className="card-sub">High yield OAS vs investment grade OAS — widening signals stress</div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
          {hyHist.length > 0 && (
            <div className="stile" style={{ textAlign: 'right' }}>
              <div className="stile-label">HY Spread</div>
              <div className="stile-value">{pct(hyHist.at(-1)?.value)}</div>
            </div>
          )}
          {igHist.length > 0 && (
            <div className="stile" style={{ textAlign: 'right' }}>
              <div className="stile-label">IG Spread</div>
              <div className="stile-value">{pct(igHist.at(-1)?.value)}</div>
            </div>
          )}
        </div>
      </div>
      <div className="card-body" style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={combined} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
            <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM} interval="preserveStartEnd" />
            <YAxis stroke="var(--text-3)" fontSize={10} tickFormatter={v => `${(+v).toFixed(1)}%`} />
            <Tooltip contentStyle={TT} labelFormatter={fmtD}
              formatter={(v, n) => [`${(+v).toFixed(2)}%`, n === 'hy' ? 'High Yield OAS' : 'IG OAS']} />
            <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-muted)' }} formatter={n => n === 'hy' ? 'High Yield OAS' : 'IG OAS'} />
            <Line type="monotone" dataKey="hy" name="hy" stroke="var(--danger)" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="ig" name="ig" stroke="var(--brand)" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="card-body" style={{ paddingTop: 0 }}>
        <div className="t-xs muted">
          HY spread &gt;5%: stress zone · &gt;8%: systemic risk · IG spread &gt;1.5%: caution · widening divergence = credit deterioration
        </div>
      </div>
    </div>
  );
}

function RateVsInflationChart({ cpiHist, fedHist }) {
  const map = new Map();
  [...cpiHist].sort((a, b) => new Date(a.date) - new Date(b.date)).forEach(p => {
    const k = String(p.date).slice(0, 7);
    map.set(k, { date: k, cpi: +p.value });
  });
  [...fedHist].sort((a, b) => new Date(a.date) - new Date(b.date)).forEach(p => {
    const k = String(p.date).slice(0, 7);
    const cur = map.get(k) || { date: k };
    cur.fed = +p.value;
    map.set(k, cur);
  });
  const data = [...map.values()].sort((a, b) => new Date(a.date) - new Date(b.date)).slice(-48);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
        <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} interval="preserveStartEnd" />
        <YAxis stroke="var(--text-3)" fontSize={10} tickFormatter={v => `${(+v).toFixed(1)}%`} />
        <Tooltip contentStyle={TT} formatter={(v, n) => [`${(+v).toFixed(2)}%`, n === 'cpi' ? 'CPI' : 'Fed Funds']} />
        <Legend wrapperStyle={{ fontSize: 11 }} formatter={n => n === 'cpi' ? 'CPI (YoY)' : 'Fed Funds Rate'} />
        <Line type="monotone" dataKey="cpi" name="cpi" stroke="var(--danger)" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="fed" name="fed" stroke="var(--cyan)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function NaaimPanel({ naaim }) {
  const current = naaim?.current ?? naaim?.naaim_number_mean;
  if (current == null) return null;

  const val = +current;
  // Zone classification: <30 very defensive, 30-50 defensive, 50-75 healthy, >75 extended
  const zone = val > 80 ? 'extended' : val >= 50 ? 'healthy' : val >= 30 ? 'defensive' : 'very_defensive';
  const zoneColor = zone === 'healthy' ? 'var(--success)' : zone === 'extended' ? 'var(--amber)' : 'var(--danger)';
  const zoneLabel = zone === 'healthy' ? 'Healthy Risk Appetite' : zone === 'extended' ? 'Extended — Watch for Reversion' : zone === 'defensive' ? 'Defensive Positioning' : 'Very Defensive — Capitulation Risk';

  const history = naaim?.history || [];
  const chartData = [...history].sort((a, b) => new Date(a.date) - new Date(b.date));

  return (
    <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">NAAIM Exposure Index</div>
          <div className="card-sub">Professional active manager equity exposure · 0 = fully out, 100 = fully invested, 200 = leveraged long</div>
        </div>
        <span className="badge" style={{ background: `${zoneColor}20`, color: zoneColor, border: `1px solid ${zoneColor}50` }}>
          {val.toFixed(1)}
        </span>
      </div>
      <div className="card-body">
        <div style={{ display: 'flex', gap: 'var(--space-6)', alignItems: 'flex-start', marginBottom: 'var(--space-4)', flexWrap: 'wrap' }}>
          <div className="stile">
            <div className="stile-label">Current Reading</div>
            <div className="stile-value" style={{ color: zoneColor }}>{val.toFixed(1)}</div>
            <div className="stile-sub muted t-xs">{zoneLabel}</div>
          </div>
          <div className="stile">
            <div className="stile-label">Interpretation</div>
            <div className="t-sm" style={{ marginTop: 4, maxWidth: 340, color: 'var(--text-2)' }}>
              {zone === 'extended'
                ? 'Pros are heavily long. Mean-reversion risk elevated — high exposure often precedes choppiness.'
                : zone === 'healthy'
                ? 'Professional managers have healthy exposure. Confirms market confidence without being over-leveraged.'
                : zone === 'defensive'
                ? 'Managers cutting equity. Watch for further selling or a contrarian buy signal if combined with fear extremes.'
                : 'Extreme defensiveness — historically a contrarian bullish signal when other indicators confirm. Capitulation zone.'}
            </div>
          </div>
        </div>

        {chartData.length > 1 && (
          <div style={{ height: 180 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="naaimGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={zoneColor} stopOpacity={0.4} />
                    <stop offset="100%" stopColor={zoneColor} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM}
                  interval={Math.max(0, Math.floor(chartData.length / 6))} />
                <YAxis stroke="var(--text-3)" fontSize={10} domain={[0, 120]} />
                <Tooltip contentStyle={TT} labelFormatter={fmtD}
                  formatter={v => [v != null ? (+v).toFixed(1) : '—', 'NAAIM Exposure']} />
                <ReferenceLine y={100} stroke="var(--border-2)" strokeDasharray="4 4" />
                <ReferenceLine y={50} stroke="var(--border-2)" strokeDasharray="2 6" />
                <Area type="monotone" dataKey="naaim_number_mean" stroke={zoneColor}
                  strokeWidth={2} fill="url(#naaimGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="t-xs muted" style={{ marginTop: 'var(--space-3)' }}>
          Source: National Association of Active Investment Managers · Weekly survey · Long-run avg ~65-70
        </div>
      </div>
    </div>
  );
}

function EconomicRegimeClock({ indicators, yieldData }) {
  const gdp = indicators?.find(i => (i.name || '').toLowerCase().includes('gdp'));
  const indpro = indicators?.find(i => (i.name || '').toLowerCase().includes('industrial'));
  const cpi = indicators?.find(i => (i.name || '').toLowerCase().includes('cpi'));
  const ism = indicators?.find(i => (i.name || '').toLowerCase().includes('ism manufacturing'));

  // Growth axis: GDP trend (positive = expansion) + ISM manufacturing (>50 = expansion)
  const gdpTrend = gdp?.trend === 'up' ? 1 : gdp?.trend === 'down' ? -1 : 0;
  const ismVal = ism?.rawValue ? +ism.rawValue : 50;
  const ismTrend = ismVal > 50 ? 1 : ismVal < 50 ? -1 : 0;
  const growthScore = (gdpTrend + ismTrend) / 2;

  // Inflation axis: CPI relative to 2% Fed target (positive = above target = inflationary)
  const cpiVal = cpi?.rawValue ? +cpi.rawValue : 2;
  const inflationScore = Math.max(-1, Math.min(1, (cpiVal - 2) / 4));

  // Determine regime quadrant
  const regime = growthScore > 0 && inflationScore < 0.5 ? 'Goldilocks' :
                 growthScore > 0 && inflationScore >= 0.5 ? 'Overheat' :
                 growthScore <= 0 && inflationScore >= 0.5 ? 'Stagflation' :
                 'Slowdown';

  const regimeColor = regime === 'Goldilocks' ? 'var(--success)' :
                     regime === 'Overheat' ? 'var(--danger)' :
                     regime === 'Stagflation' ? 'var(--danger)' :
                     'var(--amber)';

  const regimeDesc = regime === 'Goldilocks' ? 'Strong growth, moderate inflation — ideal policy conditions' :
                    regime === 'Overheat' ? 'High growth + high inflation — Fed tightening, erosion risk' :
                    regime === 'Stagflation' ? 'Weak growth + high inflation — no policy solution, defensive positioning' :
                    'Weak growth, deflation pressure — easy policy, opportunity zone';

  return (
    <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Economic Regime Clock</div>
          <div className="card-sub">Growth vs Inflation — positioning for current economic phase</div>
        </div>
        <span className="badge" style={{ background: `${regimeColor}20`, color: regimeColor, border: `1px solid ${regimeColor}50` }}>
          {regime}
        </span>
      </div>
      <div className="card-body" style={{ paddingBottom: 0 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
          {/* 2x2 Grid Visualization */}
          <div style={{ gridColumn: '1 / -1', height: 260, position: 'relative', border: '1px solid var(--border-soft)', borderRadius: 'var(--r-sm)', overflow: 'hidden' }}>
            {/* Quadrants */}
            <div style={{ position: 'absolute', inset: 0, display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr', pointerEvents: 'none' }}>
              {/* Top-Left: Slowdown */}
              <div style={{ borderRight: '1px solid var(--border-soft)', borderBottom: '1px solid var(--border-soft)', background: 'var(--amber)08', padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-start' }}>
                <div className="t-xs strong" style={{ color: 'var(--amber)' }}>Slowdown</div>
              </div>
              {/* Top-Right: Overheat */}
              <div style={{ borderBottom: '1px solid var(--border-soft)', background: 'var(--danger)08', padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-start' }}>
                <div className="t-xs strong" style={{ color: 'var(--danger)' }}>Overheat</div>
              </div>
              {/* Bottom-Left: Goldilocks */}
              <div style={{ borderRight: '1px solid var(--border-soft)', background: 'var(--success)08', padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
                <div className="t-xs strong" style={{ color: 'var(--success)' }}>Goldilocks</div>
              </div>
              {/* Bottom-Right: Stagflation */}
              <div style={{ background: 'var(--danger)08', padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
                <div className="t-xs strong" style={{ color: 'var(--danger)' }}>Stagflation</div>
              </div>
            </div>

            {/* Current Position Dot */}
            <div style={{
              position: 'absolute',
              left: `${50 + growthScore * 40}%`,
              top: `${50 - inflationScore * 40}%`,
              transform: 'translate(-50%, -50%)',
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: regimeColor,
              boxShadow: `0 0 0 8px ${regimeColor}30`,
              zIndex: 10,
            }} />

            {/* Axes */}
            <div style={{
              position: 'absolute',
              left: '50%',
              top: 0,
              bottom: 0,
              width: 1,
              background: 'var(--border-2)',
              transform: 'translateX(-50%)',
              zIndex: 1,
            }} />
            <div style={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: '50%',
              height: 1,
              background: 'var(--border-2)',
              transform: 'translateY(-50%)',
              zIndex: 1,
            }} />

            {/* Axis Labels */}
            <div style={{ position: 'absolute', bottom: 4, left: '50%', transform: 'translateX(-50%)', fontSize: 'var(--t-2xs)', color: 'var(--text-3)', zIndex: 5 }}>Weak ← Growth → Strong</div>
            <div style={{ position: 'absolute', left: 4, top: '50%', transform: 'translateY(-50%)', fontSize: 'var(--t-2xs)', color: 'var(--text-3)', zIndex: 5, writingMode: 'vertical-rl', textOrientation: 'mixed' }}>Low ← Inflation → High</div>
          </div>

          {/* Key Inputs */}
          <div>
            <div className="stile">
              <div className="stile-label">Growth Axis</div>
              <div className="t-sm" style={{ marginTop: 4, color: 'var(--text-2)' }}>
                <div>GDP trend: <strong style={{ color: gdpTrend > 0 ? 'var(--success)' : gdpTrend < 0 ? 'var(--danger)' : 'var(--text)' }}>{gdpTrend > 0 ? '↗ Expanding' : gdpTrend < 0 ? '↘ Contracting' : '→ Flat'}</strong></div>
                <div style={{ marginTop: 4 }}>ISM Manufacturing: <strong className={ismVal > 50 ? 'up' : ismVal < 50 ? 'down' : ''}>{ismVal.toFixed(1)}</strong></div>
              </div>
            </div>
          </div>

          <div>
            <div className="stile">
              <div className="stile-label">Inflation Axis</div>
              <div className="t-sm" style={{ marginTop: 4, color: 'var(--text-2)' }}>
                <div>CPI (YoY): <strong style={{ color: cpiVal > 2.5 ? 'var(--danger)' : cpiVal > 2 ? 'var(--amber)' : 'var(--success)' }}>{cpiVal.toFixed(2)}%</strong></div>
                <div style={{ marginTop: 4 }}>Fed Target: <strong>2.0%</strong></div>
              </div>
            </div>
          </div>
        </div>

        <div style={{ marginTop: 'var(--space-4)', padding: 'var(--space-3) var(--space-4)', background: 'var(--surface-2)', borderRadius: 'var(--r-sm)' }}>
          <div className="t-sm muted">{regimeDesc}</div>
        </div>
      </div>
    </div>
  );
}

function GrowthLaborBarometer({ indicators }) {
  const claims = indicators?.find(i => {
    const nm = (i.name || '').toLowerCase();
    return nm.includes('jobless') || nm.includes('initial claims');
  });

  // Growth-Labor Barometer: ISM Manufacturing / Jobless Claims ratio
  // Combines industrial activity (ISM Mfg) with labor market stress to signal expansion vs contraction

  const ism = indicators?.find(i => (i.name || '').toLowerCase().includes('ism manufacturing'));
  const ismVal = ism?.rawValue ? +ism.rawValue : 50;
  const claimsVal = claims?.rawValue ? +claims.rawValue : 250000;
  const claimsHist = claims?.history || [];

  // Compute barometer: higher ISM + lower claims = expansion signal
  // Normalize: ISM 40-60 range, claims 150k-450k range
  const ismScore = Math.max(0, Math.min(1, (ismVal - 40) / 20));
  const claimsScore = Math.max(0, Math.min(1, (450000 - claimsVal) / 300000));
  const barometer = (ismScore * 0.6 + claimsScore * 0.4) * 100;

  // Trend: if we have history, compare current to 3-month average
  const claimsNumeric = claimsHist.map(h => +h.value).filter(v => !isNaN(v));
  const claimsMA3 = claimsNumeric.length >= 13
    ? claimsNumeric.slice(-13).reduce((a, b) => a + b) / 13
    : claimsVal;
  const claimsTrend = claimsVal < claimsMA3 ? 'down' : claimsVal > claimsMA3 ? 'up' : 'flat';

  const interpretation = barometer > 65
    ? { label: 'Expansion Strong', color: 'var(--success)', desc: 'Industrial activity robust, job market tight — rising barometer signals continued growth.' }
    : barometer > 50
    ? { label: 'Expansion Moderate', color: 'var(--cyan)', desc: 'Mixed but leaning positive — growth present but not accelerating.' }
    : barometer > 35
    ? { label: 'Contraction Risk', color: 'var(--amber)', desc: 'Weakening indicators — monitor for further deterioration.' }
    : { label: 'Contraction Evident', color: 'var(--danger)', desc: 'Industrial slowdown + labor weakness — recession-like conditions.' };

  // Build chart data from claims history
  const chartData = claimsHist
    .filter(h => h.date && h.value)
    .sort((a, b) => new Date(a.date) - new Date(b.date))
    .map(h => ({
      date: String(h.date).slice(0, 10),
      claims: +h.value,
      // Estimate barometer proxy based on claims alone (lower = better)
      barometer: Math.max(0, Math.min(100, (450000 - (+h.value)) / 4500)),
    }))
    .slice(-52);

  return (
    <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Growth-Labor Barometer</div>
          <div className="card-sub">ISM Manufacturing (growth proxy) vs Jobless Claims (labor stress) — expansion vs contraction signal</div>
        </div>
        <span className="badge" style={{ background: `${interpretation.color}20`, color: interpretation.color, border: `1px solid ${interpretation.color}50` }}>
          {barometer.toFixed(0)}
        </span>
      </div>
      <div className="card-body">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
          <div className="stile">
            <div className="stile-label">Current Reading</div>
            <div className="stile-value" style={{ color: interpretation.color }}>{barometer.toFixed(0)}</div>
            <div className="stile-sub muted t-xs">{interpretation.label}</div>
          </div>
          <div className="stile">
            <div className="stile-label">Components</div>
            <div className="t-sm" style={{ marginTop: 4, color: 'var(--text-2)' }}>
              <div>ISM Mfg: <strong className={ismVal > 50 ? 'up' : ismVal < 50 ? 'down' : ''}>{ismVal.toFixed(1)}</strong></div>
              <div style={{ marginTop: 4 }}>Jobless Claims: <strong className={claimsTrend === 'down' ? 'up' : claimsTrend === 'up' ? 'down' : ''}>{(+claimsVal).toLocaleString()}</strong></div>
            </div>
          </div>
        </div>

        {chartData.length > 1 && (
          <div style={{ height: 180, marginBottom: 'var(--space-4)' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="growthLaborGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={interpretation.color} stopOpacity={0.4} />
                    <stop offset="100%" stopColor={interpretation.color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM}
                  interval={Math.max(0, Math.floor(chartData.length / 6))} />
                <YAxis stroke="var(--text-3)" fontSize={10} domain={[0, 100]} />
                <Tooltip contentStyle={TT} labelFormatter={fmtD}
                  formatter={v => [v != null ? (+v).toFixed(0) : '—', 'Barometer']} />
                <ReferenceLine y={65} stroke="var(--border-2)" strokeDasharray="4 4" label={{ value: 'Strong', fontSize: 10, fill: 'var(--text-3)' }} />
                <ReferenceLine y={50} stroke="var(--border-2)" strokeDasharray="4 4" />
                <ReferenceLine y={35} stroke="var(--border-2)" strokeDasharray="4 4" label={{ value: 'Risk', fontSize: 10, fill: 'var(--text-3)' }} />
                <Area type="monotone" dataKey="barometer" stroke={interpretation.color}
                  strokeWidth={2} fill="url(#growthLaborGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        <div style={{ padding: 'var(--space-3) var(--space-4)', background: 'var(--surface-2)', borderRadius: 'var(--r-sm)' }}>
          <div className="t-sm muted">{interpretation.desc}</div>
        </div>
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
