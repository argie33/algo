import React, { useMemo, useState, useEffect } from 'react';
import {
  RefreshCw, TrendingUp, Activity,
  AlertCircle, Inbox, CalendarDays, BarChart2, Zap, DollarSign, Home, Globe,
} from 'lucide-react';
import {
  LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip,
  ReferenceLine, Legend,
} from 'recharts';
import { useApiQuery } from '../hooks/useApiQuery';
import { useThresholds } from '../hooks/useThresholds';
import { api } from '../services/api';
import { formatNumber, formatPercentageChange } from '../utils/formatters';
import ErrorBoundary from '../components/ErrorBoundary';

const TT = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)', fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

const _num   = (v, dp = 2) => formatNumber(v, dp);
const pct   = (v, dp = 2) => formatPercentageChange(v, dp);
const bps   = (v)         => (v == null || isNaN(+v)) ? '—' : `${Math.round(+v * 100)} bps`;
const fmtD  = (s)         => s ? new Date(s).toLocaleDateString() : '—';
const fmtM  = (s)         => s ? new Date(s).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) : '';
const up    = (v)         => v > 0 ? 'up' : v < 0 ? 'down' : 'flat';

const TABS = [
  { id: 'overview',  label: 'Overview',        icon: <BarChart2 size={13} /> },
  { id: 'cycle',     label: 'Business Cycle',  icon: <Activity size={13} /> },
  { id: 'rates',     label: 'Rates & Fed',     icon: <DollarSign size={13} /> },
  { id: 'labor',     label: 'Labor Market',    icon: <Activity size={13} /> },
  { id: 'inflation', label: 'Inflation',       icon: <TrendingUp size={13} /> },
  { id: 'growth',    label: 'Growth',          icon: <Zap size={13} /> },
  { id: 'housing',   label: 'Housing & Consumer', icon: <Home size={13} /> },
  { id: 'global',    label: 'Global & Stress', icon: <Globe size={13} /> },
  { id: 'calendar',  label: 'Calendar',        icon: <CalendarDays size={13} /> },
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

function EconomicDashboardPage() {
  const [tab, setTab] = useState('overview');
  const { thresholds, isDefault: usingDefaultThresholds } = useThresholds();

  // Trigger resize after mount to force charts to remeasure
  useEffect(() => {
    const timer = setTimeout(() => {
      window.dispatchEvent(new Event('resize'));
    }, 500);
    return () => clearTimeout(timer);
  }, []);

  const leadQ  = useApiQuery(['economic-leading'],   () => api.get('/api/economic/leading-indicators'), { refetchInterval: 120000 });
  const yldQ   = useApiQuery(['economic-yield'],     () => api.get('/api/economic/yield-curve-full'),   { refetchInterval: 120000 });
  const calQ   = useApiQuery(['economic-calendar'],  () => api.get('/api/economic/calendar'),           { refetchInterval: 120000 });
  const naaimQ = useApiQuery(['market-naaim'],       () => api.get('/api/market/naaim'),                { refetchInterval: 120000 });

  const isLoading = leadQ.loading || yldQ.loading || calQ.loading || naaimQ.loading;
  const refetch   = () => { leadQ.refetch(); yldQ.refetch(); calQ.refetch(); naaimQ.refetch(); };

  const leading    = leadQ.data   || {};
  const yieldData  = yldQ.data    || null;
  const indicators = leading.indicators || [];
  const calRaw     = calQ.data?.events ?? calQ.data?.items ?? (Array.isArray(calQ.data) ? calQ.data : []);
  const naaimData  = naaimQ.data  || null;

  // helper to find indicator by partial name
  const ind = (name) => indicators.find(i => (i.name || '').toLowerCase().includes(name.toLowerCase()));

  // ── Recession nowcasting ──────────────────────────────────────────────────
  const recession = useMemo(() => {
    const tiles = [];
    const unrate = ind('Unemployment Rate');
    const unrateHist = Array.isArray(unrate?.history) ? unrate.history : [];
    if (unrateHist.length >= 12) {
      const hist = unrateHist.slice(-12).map(p => +p.value).filter(v => !isNaN(v));
      if (hist.length >= 3) {
        const sahm = hist.slice(-3).reduce((s, v) => s + v, 0) / 3 - Math.min(...hist);
        tiles.push({
          label: 'Sahm Rule', value: `${sahm >= 0 ? '+' : ''}${sahm.toFixed(2)} pp`,
          threshold: `≥ ${thresholds.sahm_critical} triggers`, desc: '3-mo unemployment MA vs trailing 12-mo low',
          status: sahm >= thresholds.sahm_critical ? 'red' : sahm >= thresholds.sahm_warning ? 'amber' : 'green',
          weight: sahm >= thresholds.sahm_critical ? 100 : sahm >= thresholds.sahm_warning ? 60 : Math.max(0, sahm * 100),
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
        threshold: `< ${thresholds.spread_warning} inverts`, desc: 'Inversion preceded last 8 US recessions',
        status: spread < thresholds.spread_critical ? 'red' : spread < thresholds.spread_warning ? 'amber' : 'green',
        weight: spread < thresholds.spread_critical ? 100 : spread < thresholds.spread_warning ? 70 : Math.max(0, 50 - spread * 25),
      });
    }
    const hyHist = yieldData?.credit?.history?.['BAMLH0A0HYM2'] || [];
    const hyVal  = hyHist.at?.(-1)?.value;
    if (hyVal != null) {
      tiles.push({
        label: 'HY Credit Spread', value: `${(+hyVal).toFixed(2)}%`,
        threshold: `> ${thresholds.hy_spread_warning}% elevated`, desc: 'ICE BofA US High Yield OAS — default risk barometer',
        status: +hyVal > thresholds.hy_spread_critical ? 'red' : +hyVal > thresholds.hy_spread_warning ? 'amber' : 'green',
        weight: +hyVal > thresholds.hy_spread_critical ? 100 : +hyVal > thresholds.hy_spread_warning ? 60 : Math.max(0, +hyVal * 10),
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
          threshold: `> +${thresholds.claims_warning}% warning`, desc: '6-month change in initial unemployment claims',
          status: chg > thresholds.claims_critical ? 'red' : chg > thresholds.claims_warning ? 'amber' : 'green',
          weight: chg > thresholds.claims_critical ? 100 : chg > thresholds.claims_warning ? 60 : Math.max(0, chg * 2),
        });
      }
    }
    const vixHist = yieldData?.credit?.history?.['VIXCLS'] || [];
    const vixVal  = vixHist.at?.(-1)?.value;
    if (vixVal != null) {
      tiles.push({
        label: 'VIX Volatility', value: (+vixVal).toFixed(1),
        threshold: `> ${thresholds.vix_warning} elevated`, desc: 'CBOE Volatility Index — equity fear gauge',
        status: +vixVal > thresholds.vix_critical ? 'red' : +vixVal > thresholds.vix_warning ? 'amber' : 'green',
        weight: +vixVal > thresholds.vix_critical ? 100 : +vixVal > thresholds.vix_warning ? 60 : Math.max(0, +vixVal * 2),
      });
    }
    const igHist = yieldData?.credit?.history?.['BAMLH0A0IG'] || [];
    const igVal  = igHist.at?.(-1)?.value;
    if (igVal != null) {
      tiles.push({
        label: 'IG Credit Spread', value: `${(+igVal).toFixed(2)}%`,
        threshold: `> ${thresholds.ig_spread_warning}% caution`, desc: 'Investment grade OAS — financial stress indicator',
        status: +igVal > thresholds.ig_spread_critical ? 'red' : +igVal > thresholds.ig_spread_warning ? 'amber' : 'green',
        weight: +igVal > thresholds.ig_spread_critical ? 100 : +igVal > thresholds.ig_spread_warning ? 50 : Math.max(0, +igVal * 20),
      });
    }

    // Financial Stress Index (St. Louis Fed) — 18-variable composite
    const stlfsiHist = yieldData?.stress?.history?.['STLFSI4'] || [];
    const stlfsiVal  = stlfsiHist.at?.(-1)?.value ?? indicators.find(i => (i.name || '').includes('Financial Stress'))?.rawValue;
    if (stlfsiVal != null) {
      const sv = +stlfsiVal;
      tiles.push({
        label: 'Financial Stress (STL)', value: sv >= 0 ? `+${sv.toFixed(2)}σ` : `${sv.toFixed(2)}σ`,
        threshold: `> ${thresholds.stress_warning} = stressed`, desc: 'St. Louis Fed Financial Stress Index — 18 financial market variables',
        status: sv > thresholds.stress_critical ? 'red' : sv > thresholds.stress_warning ? 'amber' : 'green',
        weight: sv > thresholds.stress_critical ? 100 : sv > thresholds.stress_warning ? 50 : Math.max(0, sv * 20),
      });
    }

    // Chicago Fed National Activity Index — 85-indicator composite (< -0.70 = recession)
    const cfnaiInd2 = indicators.find(i => (i.name || '').includes('Chicago Fed'));
    if (cfnaiInd2?.rawValue != null) {
      const cv = +cfnaiInd2.rawValue;
      tiles.push({
        label: 'CFNAI Composite', value: cv >= 0 ? `+${cv.toFixed(2)}` : cv.toFixed(2),
        threshold: '< -0.70 = recession', desc: 'Chicago Fed National Activity Index — 85-indicator composite of US economic activity',
        status: cv < -0.7 ? 'red' : cv < -0.3 ? 'amber' : 'green',
        weight: cv < -0.7 ? 100 : cv < -0.3 ? 50 : Math.max(0, -cv * 50),
      });
    }

    if (!tiles.length) return null;
    const composite = Math.round(tiles.reduce((s, t) => s + t.weight, 0) / tiles.length);
    return { tiles, composite };
  }, [indicators, yieldData]);

  // ── Financial conditions ──────────────────────────────────────────────────
  const fci = useMemo(() => {
    if (!yieldData?.credit?.history) return [];
    const vixSeries  = Array.isArray(yieldData.credit.history['VIXCLS']) ? yieldData.credit.history['VIXCLS'] : [];
    const hySeries   = Array.isArray(yieldData.credit.history['BAMLH0A0HYM2']) ? yieldData.credit.history['BAMLH0A0HYM2'] : [];
    const igSeries   = Array.isArray(yieldData.credit.history['BAMLH0A0IG']) ? yieldData.credit.history['BAMLH0A0IG'] : [];
    const curveSeries = Array.isArray(yieldData.history?.T10Y2Y) ? yieldData.history.T10Y2Y : [];
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
      forecast: e.forecast ?? e.forecast_value ?? e.Forecast,
      previous: e.previous ?? e.previous_value ?? e.Previous,
      category: e.category || e.Category,
    })).sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [calRaw]);

  const fedRate     = ind('Fed Funds');
  const cpiInd      = ind('CPI') || ind('Inflation');
  const corePceInd  = ind('Core PCE');
  const gdpInd      = ind('GDP');
  const unrateInd   = ind('Unemployment');
  const claimsInd   = ind('Jobless') || ind('Initial Claims');
  const payrollInd  = ind('Payroll') || ind('Employment');
  const indproInd   = ind('Industrial Production');
  const housingInd  = ind('Housing Starts') || ind('Housing');
  const michInd     = ind('Consumer Sentiment') || ind('Michigan');
  const mortgageInd = ind('Mortgage Rate') || ind('MORTGAGE30US');
  // New indicators
  const t5yieInd    = ind('5Y Breakeven');
  const t10yieInd   = ind('10Y Breakeven');
  const dollarInd   = ind('USD Dollar');
  const oilInd      = ind('WTI Crude');
  const stlfsiInd   = ind('Financial Stress');
  const anfciInd    = ind('Financial Conditions');
  const joltsInd    = ind('JOLTS Job');
  const quitRateInd = ind('JOLTS Quit');
  const aheInd      = ind('Hourly Earnings');
  const tcuInd      = ind('Capacity Util');
  const phillyfedInd = ind('Philly Fed');
  const cfnaiInd    = ind('Chicago Fed');
  const permitInd   = ind('Building Permits');
  const savingsInd  = ind('Personal Savings') || ind('Savings Rate');
  const rdpiInd     = ind('Real Disposable');

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
          <div>{(leadQ.error?.message || leadQ.error?.responseData?.message || yldQ.error?.message || yldQ.error?.responseData?.message || 'Failed to load economic data')}</div>
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
              <ErrorBoundary>
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
              </ErrorBoundary>
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
                <ErrorBoundary>
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
                          fill={fci.at(-1)?.fci > 0 ? 'url(#fciUp)' : 'url(#fciDn)'} connectNulls={true} />
                      </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </ErrorBoundary>
              )}

              {spreadHist.length > 0 && (
                <ErrorBoundary>
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
                        <Area type="monotone" dataKey="value" stroke="var(--brand)" strokeWidth={2} fill="url(#spreadGrad)" connectNulls={true} />
                      </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </ErrorBoundary>
              )}
            </div>

            {/* NAAIM professional positioning */}
            {naaimData && <ErrorBoundary><NaaimPanel naaim={naaimData} /></ErrorBoundary>}

            {/* Credit spreads history */}
            <ErrorBoundary><CreditSpreadsPanel yieldData={yieldData} /></ErrorBoundary>
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
                  <ErrorBoundary>
                    <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={yieldCurve} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                      <XAxis dataKey="maturity" stroke="var(--text-3)" fontSize={11} />
                      <YAxis stroke="var(--text-3)" fontSize={11} domain={[0, 'auto']} tickFormatter={v => `${v}%`} />
                      <Tooltip contentStyle={TT} formatter={v => [`${(+v).toFixed(3)}%`, 'Yield']} />
                      <Line type="monotone" dataKey="yield" stroke="var(--brand)" strokeWidth={2.5} connectNulls={true}
                        dot={{ fill: 'var(--brand)', r: 4 }} activeDot={{ r: 6 }} />
                    </LineChart>
                    </ResponsiveContainer>
                  </ErrorBoundary>
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
              {claimsInd && <IndHistory ind={claimsInd} title="Initial Jobless Claims" sub="Weekly new unemployment insurance filings — earliest labor market signal" color="var(--cyan)" />}
            </div>
            {payrollInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={payrollInd} title="Non-Farm Payrolls" sub="Monthly job additions (thousands)" color="var(--success)" /></div>}

            {/* JOLTS Data — leading labor market indicators */}
            {(joltsInd || quitRateInd) && (
              <div className="card" style={{ marginTop: 'var(--space-4)' }}>
                <div className="card-head">
                  <div>
                    <div className="card-title">JOLTS Labor Market Survey</div>
                    <div className="card-sub">Job openings and quit rate — forward-looking demand and worker confidence signals</div>
                  </div>
                </div>
                <div className="card-body">
                  <div className="grid grid-2" style={{ marginBottom: 'var(--space-4)' }}>
                    {joltsInd && (
                      <div className="stile">
                        <div className="stile-label">Job Openings</div>
                        <div className="stile-value">{joltsInd.rawValue != null ? `${((+joltsInd.rawValue)/1000).toFixed(1)}M` : '—'}</div>
                        <div className="stile-sub muted t-xs">High openings = labor demand strong — Beveridge Curve tightness</div>
                      </div>
                    )}
                    {quitRateInd && (
                      <div className="stile">
                        <div className="stile-label">Quit Rate</div>
                        <div className="stile-value">{quitRateInd.value ? `${quitRateInd.value}%` : '—'}</div>
                        <div className="stile-sub muted t-xs">Workers quitting = confidence in finding new jobs — "Great Resignation" proxy</div>
                      </div>
                    )}
                  </div>
                  {joltsInd?.history?.length > 0 && (
                    <div style={{ height: 220 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={[...joltsInd.history].sort((a,b) => new Date(a.date)-new Date(b.date))}
                          margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                          <defs>
                            <linearGradient id="joltsGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.35} />
                              <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" vertical={false} />
                          <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM}
                            interval={Math.max(0, Math.floor((joltsInd.history.length) / 6))} />
                          <YAxis stroke="var(--text-3)" fontSize={10} />
                          <Tooltip contentStyle={TT} labelFormatter={fmtD}
                            formatter={v => [v != null ? `${((+v)/1000).toFixed(1)}M` : '—', 'Job Openings']} />
                          <Area type="monotone" dataKey="value" stroke="var(--brand)" strokeWidth={2} fill="url(#joltsGrad)" connectNulls={true} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              </div>
            )}
            {aheInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={aheInd} title="Average Hourly Earnings (YoY)" sub="Wage growth — sustained >4% historically inflationary; below 3.5% = labor cost normalization" color="var(--purple)" /></div>}
          </>
        )}

        {/* ── INFLATION ─────────────────────────────────────────────────── */}
        {tab === 'inflation' && (
          <>
            {/* Key KPIs — CPI, Core PCE, Fed Funds, Real Rate */}
            {(() => {
              const rate10Y = yieldData?.currentCurve?.['10Y'];
              const corePce = corePceInd?.rawValue;
              const realRate = corePce != null && rate10Y != null ? rate10Y - corePce : null;
              return (
                <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>
                  <MacroKpi label="CPI (YoY)" ind={cpiInd} unit="%" invertGood />
                  <MacroKpi label="Core PCE (YoY)" ind={corePceInd} unit="%" invertGood />
                  <MacroKpi label="Fed Funds Rate" ind={fedRate} unit="%" />
                  <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
                    <div className="eyebrow">Real Rate (10Y − Core PCE)</div>
                    <div className="mono" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
                      {realRate != null ? pct(realRate) : '—'}
                    </div>
                    <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>Positive = restrictive policy · Fed target 2.0%</div>
                  </div>
                </div>
              );
            })()}

            {/* TIPS Breakeven Inflation — market-implied expectations */}
            {(t5yieInd?.history?.length > 0 || t10yieInd?.history?.length > 0 ||
              yieldData?.breakevens?.history?.T5YIE?.length > 0) && (
              <ErrorBoundary><TipsBreakevenPanel t5y={t5yieInd} t10y={t10yieInd} yieldData={yieldData} /></ErrorBoundary>
            )}

            {/* CPI vs Core PCE vs Fed Funds overlay */}
            {cpiInd?.history?.length > 0 && fedRate?.history?.length > 0 && (
              <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
                <div className="card-head">
                  <div>
                    <div className="card-title">Inflation vs Federal Funds Rate</div>
                    <div className="card-sub">Fed policy stance relative to inflation — gap = real rate environment · Core PCE is Fed's actual 2% target</div>
                  </div>
                </div>
                <div className="card-body" style={{ height: 300 }}>
                  <ErrorBoundary><InflationVsFedChart cpiHist={cpiInd.history} corePceHist={corePceInd?.history} fedHist={fedRate.history} /></ErrorBoundary>
                </div>
              </div>
            )}

            {cpiInd && <IndHistory ind={cpiInd} title="CPI Inflation (YoY)" sub="Consumer Price Index — all items, all urban consumers" color="var(--danger)" />}
            {corePceInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={corePceInd} title="Core PCE Inflation (YoY)" sub="Personal Consumption Expenditures ex-Food & Energy — Federal Reserve's primary inflation target" color="var(--amber)" /></div>}
            {aheInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={aheInd} title="Average Hourly Earnings (YoY)" sub="Total private sector wages — wage inflation drives services inflation persistence" color="var(--purple)" /></div>}
          </>
        )}

        {/* ── BUSINESS CYCLE ────────────────────────────────────────────── */}
        {tab === 'cycle' && (
          <>
            <div className="grid grid-3" style={{ marginBottom: 'var(--space-4)' }}>
              <MacroKpi label="Philly Fed Mfg Index" ind={phillyfedInd} unit="" />
              <MacroKpi label="Chicago Fed Activity (CFNAI)" ind={cfnaiInd} unit="" />
              <MacroKpi label="Capacity Utilization" ind={tcuInd} unit="%" />
            </div>

            {/* Economic Regime Clock */}
            <ErrorBoundary><EconomicRegimeClock indicators={indicators} yieldData={yieldData} phillyfed={phillyfedInd} /></ErrorBoundary>

            {/* Growth-Labor Barometer */}
            <ErrorBoundary><GrowthLaborBarometer indicators={indicators} phillyfed={phillyfedInd} /></ErrorBoundary>

            {phillyfedInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={phillyfedInd} title="Philadelphia Fed Manufacturing Index" sub="Federal Reserve Bank of Philadelphia monthly survey — diffusion index, >0 = expansion, <0 = contraction" color="var(--brand)" /></div>}
            {cfnaiInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={cfnaiInd} title="Chicago Fed National Activity Index (CFNAI)" sub="85-indicator composite measuring US economic activity — above 0 = above historical trend" color="var(--cyan)" /></div>}
            {tcuInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={tcuInd} title="Capacity Utilization" sub="Manufacturing, mining, and utilities capacity in use — above 80% signals inflationary pressure" color="var(--purple)" /></div>}
          </>
        )}

        {/* ── GROWTH ─────────────────────────────────────────────────────── */}
        {tab === 'growth' && (
          <>
            <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>
              <MacroKpi label="GDP Growth" ind={gdpInd} unit="%" />
              <MacroKpi label="Industrial Prod." ind={indproInd} unit="" />
              <MacroKpi label="Capacity Utilization" ind={tcuInd} unit="%" />
              <MacroKpi label="Business Loans" ind={ind('Business Loans')} unit="B" />
            </div>

            {/* Leading Economic Index - 6-month forward signal */}
            <ErrorBoundary><LEIPanel indicators={indicators} /></ErrorBoundary>

            {gdpInd && <IndHistory ind={gdpInd} title="Real GDP Growth" sub="Quarterly annualized real GDP — Bureau of Economic Analysis" color="var(--success)" />}
            {indproInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={indproInd} title="Industrial Production (YoY)" sub="Federal Reserve industrial output index — manufacturing, mining, utilities" color="var(--brand)" /></div>}
            {tcuInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={tcuInd} title="Capacity Utilization" sub="Share of productive capacity in use — above 80% = inflationary pressure, below 75% = slack" color="var(--cyan)" /></div>}
            {cfnaiInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={cfnaiInd} title="Chicago Fed National Activity Index" sub="85-indicator composite — above 0 = above-trend growth, below -0.70 = recession risk" color="var(--purple)" /></div>}
            {rdpiInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={rdpiInd} title="Real Disposable Personal Income (YoY)" sub="Income after taxes adjusted for inflation — consumer spending fuel" color="var(--amber)" /></div>}
          </>
        )}

        {/* ── HOUSING & CONSUMER ───────────────────────────────────────── */}
        {tab === 'housing' && (
          <>
            <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>
              <MacroKpi label="Housing Starts" ind={housingInd} unit="K" />
              <MacroKpi label="Building Permits" ind={permitInd} unit="K" />
              <MacroKpi label="Consumer Sentiment" ind={michInd} unit="" />
              <MacroKpi label="30Y Mortgage Rate" ind={mortgageInd} unit="%" invertGood />
            </div>

            {permitInd && <IndHistory ind={permitInd} title="Building Permits (YoY)" sub="Leading indicator for housing construction — issued 1-2 months before starts" color="var(--brand)" />}
            {housingInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={housingInd} title="Housing Starts (YoY)" sub="New residential construction — Census Bureau (thousands, SAAR)" color="var(--cyan)" /></div>}
            {mortgageInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={mortgageInd} title="30-Year Fixed Mortgage Rate" sub="Freddie Mac PMMS — key affordability constraint for housing demand" color="var(--danger)" /></div>}
            {michInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={michInd} title="U. Michigan Consumer Sentiment" sub="Monthly consumer survey — leading indicator for spending, ranges 50-110" color="var(--amber)" /></div>}
            {savingsInd && <div style={{ marginTop: 'var(--space-4)' }}><IndHistory ind={savingsInd} title="Personal Savings Rate" sub="% of disposable income saved — high savings = future spending fuel, low = stretched consumer" color="var(--success)" /></div>}
          </>
        )}

        {/* ── GLOBAL & STRESS ──────────────────────────────────────────── */}
        {tab === 'global' && (
          <>
            <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>
              <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
                <div className="eyebrow">Financial Stress (STL)</div>
                <div className="mono" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)',
                  color: stlfsiInd?.rawValue > 1.5 ? 'var(--danger)' : stlfsiInd?.rawValue > 0.5 ? 'var(--amber)' : 'var(--success)' }}>
                  {stlfsiInd?.rawValue != null ? (stlfsiInd.rawValue >= 0 ? `+${(+stlfsiInd.rawValue).toFixed(2)}σ` : `${(+stlfsiInd.rawValue).toFixed(2)}σ`) : '—'}
                </div>
                <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>0 = normal · positive = stress</div>
              </div>
              <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
                <div className="eyebrow">Adj. Financial Conditions</div>
                <div className="mono" style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)',
                  color: anfciInd?.rawValue > 0.5 ? 'var(--danger)' : anfciInd?.rawValue < -0.5 ? 'var(--success)' : 'var(--text)' }}>
                  {anfciInd?.rawValue != null ? (anfciInd.rawValue >= 0 ? `+${(+anfciInd.rawValue).toFixed(3)}` : `${(+anfciInd.rawValue).toFixed(3)}`) : '—'}
                </div>
                <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>Chicago Fed ANFCI · positive = tight</div>
              </div>
              <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
                <div className="eyebrow">USD Broad Dollar Index</div>
                <div className={`mono ${dollarInd?.trend || 'flat'}`} style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
                  {dollarInd?.rawValue != null ? (+dollarInd.rawValue).toFixed(1) : '—'}
                </div>
                <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>Trade-weighted broad index</div>
              </div>
              <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
                <div className="eyebrow">WTI Crude Oil</div>
                <div className={`mono ${oilInd?.trend || 'flat'}`} style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
                  {oilInd?.rawValue != null ? `$${(+oilInd.rawValue).toFixed(1)}` : '—'}
                </div>
                <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>Cushing, Oklahoma $/barrel</div>
              </div>
            </div>

            {/* Financial Stress Panel */}
            <ErrorBoundary><FinancialStressPanel stlfsiInd={stlfsiInd} anfciInd={anfciInd} yieldData={yieldData} /></ErrorBoundary>

            {/* Dollar & Oil charts */}
            <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
              {dollarInd?.history?.length > 0 && (
                <div className="card">
                  <div className="card-head">
                    <div>
                      <div className="card-title">USD Broad Dollar Index</div>
                      <div className="card-sub">Trade-weighted nominal index vs major currencies — strong dollar = tighter global financial conditions</div>
                    </div>
                  </div>
                  <div className="card-body" style={{ height: 240 }}>
                    <ErrorBoundary>
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={[...dollarInd.history].filter((_, i) => i % 5 === 0).sort((a,b) => new Date(a.date)-new Date(b.date))}
                        margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="dollarGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.35} />
                            <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" vertical={false} />
                        <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM} interval="preserveStartEnd" />
                        <YAxis stroke="var(--text-3)" fontSize={10} domain={['auto', 'auto']} />
                        <Tooltip contentStyle={TT} labelFormatter={fmtD} formatter={v => [`${(+v).toFixed(1)}`, 'USD Index']} />
                        <Area type="monotone" dataKey="value" stroke="var(--brand)" strokeWidth={2} fill="url(#dollarGrad)" connectNulls={true} />
                      </AreaChart>
                      </ResponsiveContainer>
                    </ErrorBoundary>
                  </div>
                </div>
              )}
              {oilInd?.history?.length > 0 && (
                <div className="card">
                  <div className="card-head">
                    <div>
                      <div className="card-title">WTI Crude Oil Price</div>
                      <div className="card-sub">Cushing, Oklahoma spot price — leading indicator for energy inflation, global demand, and margin pressure</div>
                    </div>
                  </div>
                  <div className="card-body" style={{ height: 240 }}>
                    <ErrorBoundary>
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={[...oilInd.history].filter((_, i) => i % 5 === 0).sort((a,b) => new Date(a.date)-new Date(b.date))}
                          margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                          <defs>
                            <linearGradient id="oilGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="var(--amber)" stopOpacity={0.35} />
                              <stop offset="100%" stopColor="var(--amber)" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" vertical={false} />
                          <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM} interval="preserveStartEnd" />
                          <YAxis stroke="var(--text-3)" fontSize={10} tickFormatter={v => `$${(+v).toFixed(0)}`} domain={['auto', 'auto']} />
                          <Tooltip contentStyle={TT} labelFormatter={fmtD} formatter={v => [`$${(+v).toFixed(2)}`, 'WTI Crude']} />
                          <Area type="monotone" dataKey="value" stroke="var(--amber)" strokeWidth={2} fill="url(#oilGrad)" connectNulls={true} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </ErrorBoundary>
                  </div>
                </div>
              )}
            </div>
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
              {isLoading ? <Empty title="Loading…" /> :
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

function MacroKpi({ label, ind, _unit, invertGood }) {
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
  const history = Array.isArray(ind?.history) ? ind.history : [];
  if (history.length === 0) return null;
  const data = [...history].sort((a, b) => new Date(a.date) - new Date(b.date));
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
  const igHist = credit?.history?.['BAMLH0A0IG'] || [];
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

function NaaimPanel({ naaim }) {
  const current = naaim?.current?.value ?? naaim?.current ?? naaim?.naaim_number_mean;
  if (current == null) return null;

  const val = +current;
  // Zone classification: <30 very defensive, 30-50 defensive, 50-75 healthy, >75 extended
  const zone = val > 80 ? 'extended' : val >= 50 ? 'healthy' : val >= 30 ? 'defensive' : 'very_defensive';
  const zoneColor = zone === 'healthy' ? 'var(--success)' : zone === 'extended' ? 'var(--amber)' : 'var(--danger)';
  const zoneLabel = zone === 'healthy' ? 'Healthy Risk Appetite' : zone === 'extended' ? 'Extended — Watch for Reversion' : zone === 'defensive' ? 'Defensive Positioning' : 'Very Defensive — Capitulation Risk';

  const history = Array.isArray(naaim?.history) ? naaim.history : [];
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
                <Area type="monotone" dataKey="value" stroke={zoneColor}
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

function EconomicRegimeClock({ indicators, _yieldData, phillyfed }) {
  const gdp = indicators?.find(i => (i.name || '').toLowerCase().includes('gdp'));
  const cpi = indicators?.find(i => (i.name || '').toLowerCase().includes('cpi'));
  const cfnai = indicators?.find(i => (i.name || '').toLowerCase().includes('chicago fed'));

  // Growth axis: use CFNAI (best composite), fallback to Philly Fed, then GDP trend
  // CFNAI: >0 = above-trend growth, <0 = below trend
  const cfnaiVal = cfnai?.rawValue != null ? +cfnai.rawValue : null;
  const gdpTrend = gdp?.trend === 'up' ? 1 : gdp?.trend === 'down' ? -1 : 0;
  // Philly Fed: >0 = expansion, <0 = contraction (diffusion index, not 0-100 scale)
  const phillyRaw = phillyfed?.rawValue != null ? +phillyfed.rawValue : null;
  const phillyTrend = phillyRaw != null ? (phillyRaw > 0 ? 1 : phillyRaw < 0 ? -1 : 0) : 0;
  // Composite growth score: CFNAI is most reliable, else GDP + Philly
  const growthScore = cfnaiVal != null
    ? Math.max(-1, Math.min(1, cfnaiVal))
    : (gdpTrend + phillyTrend) / 2;

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
            <div style={{ position: 'absolute', bottom: 4, left: '50%', transform: 'translateX(-50%)', fontSize: 'var(--t-2xs)', color: 'var(--text-3)', zIndex: 5 }}>Weak â† Growth → Strong</div>
            <div style={{ position: 'absolute', left: 4, top: '50%', transform: 'translateY(-50%)', fontSize: 'var(--t-2xs)', color: 'var(--text-3)', zIndex: 5, writingMode: 'vertical-rl', textOrientation: 'mixed' }}>Low â† Inflation → High</div>
          </div>

          {/* Key Inputs */}
          <div>
            <div className="stile">
              <div className="stile-label">Growth Axis</div>
              <div className="t-sm" style={{ marginTop: 4, color: 'var(--text-2)' }}>
                {cfnaiVal != null
                  ? <div>CFNAI: <strong style={{ color: cfnaiVal > 0 ? 'var(--success)' : cfnaiVal < -0.35 ? 'var(--danger)' : 'var(--amber)' }}>{cfnaiVal >= 0 ? `+${cfnaiVal.toFixed(2)}` : cfnaiVal.toFixed(2)}</strong></div>
                  : <div>GDP trend: <strong style={{ color: gdpTrend > 0 ? 'var(--success)' : gdpTrend < 0 ? 'var(--danger)' : 'var(--text)' }}>{gdpTrend > 0 ? '↗ Expanding' : gdpTrend < 0 ? '↘ Contracting' : '→ Flat'}</strong></div>
                }
                <div style={{ marginTop: 4 }}>Philly Fed Mfg: <strong className={phillyRaw != null ? (phillyRaw > 0 ? 'up' : 'down') : ''}>{phillyRaw != null ? `${phillyRaw >= 0 ? '+' : ''}${phillyRaw.toFixed(1)}` : '—'}</strong></div>
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

function GrowthLaborBarometer({ indicators, phillyfed }) {
  const claims = indicators?.find(i => {
    const nm = (i.name || '').toLowerCase();
    return nm.includes('jobless') || nm.includes('initial claims');
  });

  // Growth-Labor Barometer: Philly Fed Manufacturing / Jobless Claims composite
  // Combines industrial activity with labor market stress to signal expansion vs contraction
  const phillyRaw = phillyfed?.rawValue != null ? +phillyfed.rawValue : null;
  // Convert Philly Fed diffusion index (centered at 0) to ISM-like scale (centered at 50)
  const ismVal = phillyRaw != null ? 50 + phillyRaw / 2 : 50;
  const claimsVal = claims?.rawValue ? +claims.rawValue : 250000;
  const claimsHist = Array.isArray(claims?.history) ? claims.history : [];

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
          <div className="card-sub">Philly Fed Manufacturing (growth proxy) vs Jobless Claims (labor stress) — expansion vs contraction composite signal</div>
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
              <div>Philly Fed ({phillyRaw != null ? `${phillyRaw >= 0 ? '+' : ''}${phillyRaw.toFixed(1)}` : '—'}): <strong className={ismVal > 50 ? 'up' : ismVal < 50 ? 'down' : ''}>{ismVal.toFixed(1)} (ISM equiv)</strong></div>
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

function LEIPanel({ indicators }) {
  // Leading Economic Index components
  // Components: UNRATE (inverted), HOUST, ICSA (inverted), CIVPART, PERMIT, MMNRNJ (inverted), DCOILWTICO, PMI, Consumer Expectations, Stock prices

  const unrate = indicators?.find(i => (i.name || '').toLowerCase().includes('unemployment'));
  const houst = indicators?.find(i => (i.name || '').toLowerCase().includes('housing'));
  const icsa = indicators?.find(i => (i.name || '').toLowerCase().includes('jobless') || (i.name || '').toLowerCase().includes('initial claims'));
  const _civpart = indicators?.find(i => (i.name || '').toLowerCase().includes('participation'));
  const sp500 = indicators?.find(i => (i.name || '').toLowerCase().includes('sp500') || (i.name || '').toLowerCase().includes('s&p'));

  // Extract values with fallbacks
  const unrateVal = unrate?.rawValue ? +unrate.rawValue : null;
  const houstVal = houst?.rawValue ? +houst.rawValue : null;
  const icsaVal = icsa?.rawValue ? +icsa.rawValue : null;
  const sp500Val = sp500?.rawValue ? +sp500.rawValue : null;

  // Calculate LEI momentum (simplified): normalize components to 0-100 scale and average
  // Components:
  // - Lower unemployment = expansion (invert: 100 - UNRATE*10)
  // - Higher housing = expansion
  // - Lower jobless claims = expansion (invert)
  // - Higher stock prices = expansion
  const leiScore = (() => {
    let components = [];
    if (unrateVal != null) components.push(Math.max(0, Math.min(100, 100 - unrateVal * 10)));
    if (houstVal != null) components.push(Math.max(0, Math.min(100, Math.min(houstVal / 2, 100))));
    if (icsaVal != null) components.push(Math.max(0, Math.min(100, Math.max(0, 100 - icsaVal / 5000))));
    if (sp500Val != null) components.push(Math.max(0, Math.min(100, Math.min(sp500Val / 50, 100))));
    return components.length > 0 ? components.reduce((a, b) => a + b) / components.length : 50;
  })();

  // 6-month historical data from indicator histories (if available)
  const chartData = (() => {
    const history = Array.isArray(icsa?.history) ? icsa.history : [];
    if (history.length === 0) return [];
    const hist = history.slice(-26).map(h => {
      const u = unrate?.history?.find(uh => String(uh.date).slice(0, 10) === String(h.date).slice(0, 10));
      const h2 = houst?.history?.find(hh => String(hh.date).slice(0, 10) === String(h.date).slice(0, 10));
      const s = sp500?.history?.find(sh => String(sh.date).slice(0, 10) === String(h.date).slice(0, 10));

      const unr = u?.value ? +u.value : null;
      const hou = h2?.value ? +h2.value : null;
      const ics = +h.value;
      const sp = s?.value ? +s.value : null;

      const comps = [];
      if (unr != null) comps.push(Math.max(0, Math.min(100, 100 - unr * 10)));
      if (hou != null) comps.push(Math.max(0, Math.min(100, Math.min(hou / 2, 100))));
      if (ics != null) comps.push(Math.max(0, Math.min(100, Math.max(0, 100 - ics / 5000))));
      if (sp != null) comps.push(Math.max(0, Math.min(100, Math.min(sp / 50, 100))));

      return {
        date: String(h.date).slice(0, 10),
        lei: comps.length > 0 ? comps.reduce((a, b) => a + b) / comps.length : 50,
      };
    }).sort((a, b) => new Date(a.date) - new Date(b.date));
    return hist;
  })();

  const sixMonthAvg = chartData.length > 0
    ? chartData.slice(-26).reduce((s, d) => s + d.lei, 0) / Math.min(26, chartData.length)
    : 50;
  const sixMonthTrend = chartData.length >= 2
    ? chartData[chartData.length - 1].lei > sixMonthAvg ? 'up' : chartData[chartData.length - 1].lei < sixMonthAvg ? 'down' : 'flat'
    : 'flat';

  const leiInterpretation = leiScore > 60
    ? { label: 'Expansion Strong', color: 'var(--success)', desc: 'LEI pointing to continued growth — positive momentum across labor, housing, and equities' }
    : leiScore > 50
    ? { label: 'Expansion Moderate', color: 'var(--cyan)', desc: 'Mixed signals but growth-leaning — monitor for deterioration' }
    : leiScore > 40
    ? { label: 'Growth Risk', color: 'var(--amber)', desc: 'Leading indicators softening — recession risk rising, watch labor market' }
    : { label: 'Contraction Risk', color: 'var(--danger)', desc: 'LEI signaling recession — defensive positioning warranted' };

  return (
    <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Leading Economic Index (LEI)</div>
          <div className="card-sub">Composite 6-month forward signal — unemployment, housing, claims, equities</div>
        </div>
        <span className="badge" style={{ background: `${leiInterpretation.color}20`, color: leiInterpretation.color, border: `1px solid ${leiInterpretation.color}50` }}>
          {leiScore.toFixed(0)}
        </span>
      </div>
      <div className="card-body">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
          <div className="stile">
            <div className="stile-label">Current LEI</div>
            <div className="stile-value" style={{ color: leiInterpretation.color }}>{leiScore.toFixed(0)}</div>
            <div className="stile-sub muted t-xs">{leiInterpretation.label}</div>
          </div>
          <div className="stile">
            <div className="stile-label">6-Month Trend</div>
            <div className="t-sm" style={{ marginTop: 4, color: 'var(--text-2)' }}>
              <div>vs 26-week avg: <strong className={sixMonthTrend === 'up' ? 'up' : sixMonthTrend === 'down' ? 'down' : ''}>{sixMonthTrend === 'up' ? '↗ Improving' : sixMonthTrend === 'down' ? '↘ Deteriorating' : '→ Flat'}</strong></div>
              <div style={{ marginTop: 4 }}>Latest: <strong>{chartData.length > 0 ? chartData[chartData.length - 1].lei.toFixed(0) : '—'}</strong></div>
            </div>
          </div>
        </div>

        {chartData.length > 1 && (
          <div style={{ height: 200, marginBottom: 'var(--space-4)' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="leiGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={leiInterpretation.color} stopOpacity={0.4} />
                    <stop offset="100%" stopColor={leiInterpretation.color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM}
                  interval={Math.max(0, Math.floor(chartData.length / 6))} />
                <YAxis stroke="var(--text-3)" fontSize={10} domain={[0, 100]} />
                <Tooltip contentStyle={TT} labelFormatter={fmtD}
                  formatter={v => [v != null ? (+v).toFixed(0) : '—', 'LEI Score']} />
                <ReferenceLine y={sixMonthAvg} stroke="var(--border-2)" strokeDasharray="4 4" label={{ value: '6mo Avg', fontSize: 10, fill: 'var(--text-3)' }} />
                <ReferenceLine y={60} stroke="var(--success)" strokeDasharray="2 6" opacity={0.3} />
                <ReferenceLine y={40} stroke="var(--danger)" strokeDasharray="2 6" opacity={0.3} />
                <Area type="monotone" dataKey="lei" stroke={leiInterpretation.color}
                  strokeWidth={2} fill="url(#leiGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        <div style={{ padding: 'var(--space-3) var(--space-4)', background: 'var(--surface-2)', borderRadius: 'var(--r-sm)' }}>
          <div className="t-sm muted">{leiInterpretation.desc}</div>
        </div>
      </div>
    </div>
  );
}

function TipsBreakevenPanel({ t5y, t10y, yieldData }) {
  const t5hist = Array.isArray(t5y?.history) ? t5y.history : Array.isArray(yieldData?.breakevens?.history?.T5YIE) ? yieldData.breakevens.history.T5YIE : [];
  const t10hist = Array.isArray(t10y?.history) ? t10y.history : Array.isArray(yieldData?.breakevens?.history?.T10YIE) ? yieldData.breakevens.history.T10YIE : [];
  const t5cur = t5y?.rawValue ?? yieldData?.breakevens?.current?.T5YIE;
  const t10cur = t10y?.rawValue ?? yieldData?.breakevens?.current?.T10YIE;

  const combined = (() => {
    const map = new Map();
    [...t5hist].filter((_, i) => i % 5 === 0).forEach(p => {
      const k = String(p.date).slice(0, 10);
      const cur = map.get(k) || { date: k };
      cur.t5y = +p.value;
      map.set(k, cur);
    });
    [...t10hist].filter((_, i) => i % 5 === 0).forEach(p => {
      const k = String(p.date).slice(0, 10);
      const cur = map.get(k) || { date: k };
      cur.t10y = +p.value;
      map.set(k, cur);
    });
    return [...map.values()].sort((a, b) => new Date(a.date) - new Date(b.date));
  })();

  if (combined.length < 5) return null;

  return (
    <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">TIPS Breakeven Inflation Expectations</div>
          <div className="card-sub">Market-implied inflation expectations from TIPS vs nominal Treasuries — the Fed monitors these closely</div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
          {t5cur != null && (
            <div className="stile" style={{ textAlign: 'right' }}>
              <div className="stile-label">5Y Breakeven</div>
              <div className="stile-value" style={{ color: +t5cur > 3 ? 'var(--danger)' : +t5cur > 2.5 ? 'var(--amber)' : 'var(--success)' }}>{(+t5cur).toFixed(2)}%</div>
            </div>
          )}
          {t10cur != null && (
            <div className="stile" style={{ textAlign: 'right' }}>
              <div className="stile-label">10Y Breakeven</div>
              <div className="stile-value" style={{ color: +t10cur > 3 ? 'var(--danger)' : +t10cur > 2.5 ? 'var(--amber)' : 'var(--success)' }}>{(+t10cur).toFixed(2)}%</div>
            </div>
          )}
        </div>
      </div>
      <div className="card-body" style={{ height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={combined} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
            <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM} interval="preserveStartEnd" />
            <YAxis stroke="var(--text-3)" fontSize={10} domain={[1, 4]} tickFormatter={v => `${(+v).toFixed(1)}%`} />
            <Tooltip contentStyle={TT} labelFormatter={fmtD}
              formatter={(v, n) => [`${(+v).toFixed(2)}%`, n === 't5y' ? '5Y Breakeven' : '10Y Breakeven']} />
            <Legend wrapperStyle={{ fontSize: 11 }} formatter={n => n === 't5y' ? '5Y Breakeven' : '10Y Breakeven'} />
            <ReferenceLine y={2} stroke="var(--success)" strokeDasharray="4 4" label={{ value: 'Fed Target 2%', fontSize: 9, fill: 'var(--success)' }} />
            <ReferenceLine y={2.5} stroke="var(--amber)" strokeDasharray="4 4" label={{ value: '2.5% Caution', fontSize: 9, fill: 'var(--amber)' }} />
            <Line type="monotone" dataKey="t5y" name="t5y" stroke="var(--brand)" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="t10y" name="t10y" stroke="var(--danger)" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="card-body" style={{ paddingTop: 0 }}>
        <div className="t-xs muted">
          Breakeven = nominal Treasury yield − TIPS real yield · above 2.5% = markets expect above-target inflation · above 3% = inflation expectations unanchoring
        </div>
      </div>
    </div>
  );
}

function InflationVsFedChart({ cpiHist, corePceHist, fedHist }) {
  const map = new Map();
  [...(cpiHist || [])].sort((a, b) => new Date(a.date) - new Date(b.date)).forEach(p => {
    const k = String(p.date).slice(0, 7);
    map.set(k, { date: k, cpi: +p.value });
  });
  [...(corePceHist || [])].sort((a, b) => new Date(a.date) - new Date(b.date)).forEach(p => {
    const k = String(p.date).slice(0, 7);
    const cur = map.get(k) || { date: k };
    cur.corePce = +p.value;
    map.set(k, cur);
  });
  [...(fedHist || [])].sort((a, b) => new Date(a.date) - new Date(b.date)).forEach(p => {
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
        <Tooltip contentStyle={TT} formatter={(v, n) => [`${(+v).toFixed(2)}%`, n === 'cpi' ? 'CPI YoY' : n === 'corePce' ? 'Core PCE YoY' : 'Fed Funds']} />
        <Legend wrapperStyle={{ fontSize: 11 }} formatter={n => n === 'cpi' ? 'CPI (YoY)' : n === 'corePce' ? 'Core PCE (YoY)' : 'Fed Funds Rate'} />
        <ReferenceLine y={2} stroke="var(--success)" strokeDasharray="4 4" />
        <Line type="monotone" dataKey="cpi" name="cpi" stroke="var(--danger)" strokeWidth={2} dot={false} />
        {corePceHist?.length > 0 && <Line type="monotone" dataKey="corePce" name="corePce" stroke="var(--amber)" strokeWidth={2} dot={false} strokeDasharray="6 3" />}
        <Line type="monotone" dataKey="fed" name="fed" stroke="var(--cyan)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function FinancialStressPanel({ stlfsiInd, anfciInd, yieldData }) {
  const stlfsiHist = Array.isArray(stlfsiInd?.history) ? stlfsiInd.history : Array.isArray(yieldData?.stress?.history?.STLFSI4) ? yieldData.stress.history.STLFSI4 : [];
  const anfciHist = Array.isArray(anfciInd?.history) ? anfciInd.history : Array.isArray(yieldData?.stress?.history?.ANFCI) ? yieldData.stress.history.ANFCI : [];

  const combined = (() => {
    const map = new Map();
    [...stlfsiHist].filter((_, i) => i % 2 === 0).forEach(p => {
      const k = String(p.date).slice(0, 10);
      const cur = map.get(k) || { date: k };
      cur.stlfsi = +p.value;
      map.set(k, cur);
    });
    [...anfciHist].filter((_, i) => i % 2 === 0).forEach(p => {
      const k = String(p.date).slice(0, 10);
      const cur = map.get(k) || { date: k };
      cur.anfci = +p.value;
      map.set(k, cur);
    });
    return [...map.values()].sort((a, b) => new Date(a.date) - new Date(b.date));
  })();

  const latest = combined.at(-1);
  const stlfsiLatest = latest?.stlfsi ?? stlfsiInd?.rawValue;
  const stressLevel = stlfsiLatest != null
    ? (+stlfsiLatest > 1.5 ? { label: 'Severe Stress', color: 'var(--danger)' }
      : +stlfsiLatest > 0.5 ? { label: 'Elevated Stress', color: 'var(--amber)' }
      : { label: 'Normal Conditions', color: 'var(--success)' })
    : { label: '—', color: 'var(--text-muted)' };

  if (combined.length < 5) return null;

  return (
    <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Financial Stress Index</div>
          <div className="card-sub">St. Louis Fed STLFSI4 (18 variables) + Chicago Fed ANFCI — broader than credit spreads alone</div>
        </div>
        <span className="badge" style={{ background: `${stressLevel.color}20`, color: stressLevel.color, border: `1px solid ${stressLevel.color}50` }}>
          {stressLevel.label}
        </span>
      </div>
      <div className="card-body" style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={combined} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
            <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10} tickFormatter={fmtM} interval="preserveStartEnd" />
            <YAxis stroke="var(--text-3)" fontSize={10} />
            <Tooltip contentStyle={TT} labelFormatter={fmtD}
              formatter={(v, n) => [`${(+v).toFixed(3)}σ`, n === 'stlfsi' ? 'STLFSI4 (STL)' : 'ANFCI (Chicago Fed)']} />
            <Legend wrapperStyle={{ fontSize: 11 }} formatter={n => n === 'stlfsi' ? 'STLFSI4 (STL Fed)' : 'ANFCI (Chicago Fed)'} />
            <ReferenceLine y={0} stroke="var(--border-2)" strokeDasharray="4 4" />
            <ReferenceLine y={1} stroke="var(--amber)" strokeDasharray="3 5" label={{ value: 'Stress Zone', fontSize: 9, fill: 'var(--amber)' }} />
            <ReferenceLine y={-1} stroke="var(--success)" strokeDasharray="3 5" label={{ value: 'Easy', fontSize: 9, fill: 'var(--success)' }} />
            {stlfsiHist.length > 0 && <Line type="monotone" dataKey="stlfsi" name="stlfsi" stroke="var(--danger)" strokeWidth={2} dot={false} />}
            {anfciHist.length > 0 && <Line type="monotone" dataKey="anfci" name="anfci" stroke="var(--brand)" strokeWidth={2} dot={false} strokeDasharray="6 3" />}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="card-body" style={{ paddingTop: 0 }}>
        <div className="t-xs muted">
          STLFSI4: 18 financial market variables (interest rates, spreads, other indicators) · 0 = average conditions · positive = stress ·
          ANFCI adjusts for current macro conditions — negative = loose, positive = tight
        </div>
      </div>
    </div>
  );
}

export default function EconomicDashboard() {
  return (
    <ErrorBoundary>
      <EconomicDashboardPage />
    </ErrorBoundary>
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

