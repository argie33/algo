import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  RefreshCw, TrendingUp, TrendingDown, Minus, Activity,
  AlertCircle, Inbox, CalendarDays,
} from 'lucide-react';
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  ResponsiveContainer, Tooltip, ReferenceLine, Legend,
} from 'recharts';
import { api, extractData } from '../services/api';

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

const num = (v, dp = 2) => (v == null || isNaN(Number(v))) ? '—' : Number(v).toFixed(dp);
const fmtBps = (v) => (v == null || isNaN(Number(v))) ? '—' : Math.round(Number(v));
const fmtDate = (s) => s ? new Date(s).toLocaleDateString() : '—';
const fmtMonth = (s) => s ? new Date(s).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) : '';

function signalToBadge(sig) {
  if (sig === 'Positive') return 'badge-success';
  if (sig === 'Negative') return 'badge-danger';
  return 'badge-cyan';
}

function trendTone(t) {
  if (t === 'up') return 'up';
  if (t === 'down') return 'down';
  return 'flat';
}

function trendIcon(t, size = 14) {
  if (t === 'up') return <TrendingUp size={size} />;
  if (t === 'down') return <TrendingDown size={size} />;
  return <Minus size={size} />;
}

function importanceBadge(level) {
  const v = (level || '').toLowerCase();
  if (v === 'high') return 'badge-danger';
  if (v === 'medium') return 'badge-amber';
  return 'badge';
}

function stressTone(value, hi, mid) {
  if (value == null) return 'flat';
  if (value >= hi) return 'down';
  if (value >= mid) return 'flat';
  return 'up';
}

export default function EconomicDashboard() {
  const leadingQ = useQuery({
    queryKey: ['economic-leading-indicators'],
    queryFn: async () => {
      const r = await api.get('/api/economic/leading-indicators');
      const ext = extractData(r);
      return ext.data || ext || {};
    },
    refetchInterval: 60000,
  });

  const yieldQ = useQuery({
    queryKey: ['economic-yield-curve-full'],
    queryFn: async () => {
      const r = await api.get('/api/economic/yield-curve-full');
      const ext = extractData(r);
      return ext.data || ext || null;
    },
    refetchInterval: 60000,
  });

  const calendarQ = useQuery({
    queryKey: ['economic-calendar'],
    queryFn: async () => {
      const r = await api.get('/api/economic/calendar');
      const ext = extractData(r);
      const raw = ext.data || ext || {};
      return raw?.events || (Array.isArray(raw) ? raw : []);
    },
    refetchInterval: 60000,
  });

  const isLoading = leadingQ.isLoading || yieldQ.isLoading || calendarQ.isLoading;
  const refetch = () => {
    leadingQ.refetch();
    yieldQ.refetch();
    calendarQ.refetch();
  };

  const leading = leadingQ.data || {};
  const yieldData = yieldQ.data || null;
  const calendarRaw = calendarQ.data || [];

  const indicators = leading.indicators || [];

  const yieldCurveData = useMemo(() => {
    if (!yieldData?.currentCurve) return [];
    const map = { '3M': '3 Month', '2Y': '2 Year', '5Y': '5 Year', '10Y': '10 Year', '30Y': '30 Year' };
    return Object.entries(yieldData.currentCurve).map(([k, v]) => ({
      maturity: map[k] || k,
      yield: v ?? null,
    }));
  }, [yieldData]);

  const transformedHistory = useMemo(() => {
    if (!yieldData?.history) return {};
    const seriesMap = {
      DGS3MO: '3M', DGS2: '2Y', DGS5: '5Y', DGS10: '10Y', DGS30: '30Y',
      T10Y2Y: 'spread_10y2y', T10Y3M: 'spread_10y3m',
    };
    const out = {};
    Object.entries(yieldData.history).forEach(([sid, data]) => {
      out[seriesMap[sid] || sid] = data || [];
    });
    return out;
  }, [yieldData]);

  const spreadHistory = transformedHistory.spread_10y2y || [];
  const tenYHistory = transformedHistory['10Y'] || [];
  const twoYHistory = transformedHistory['2Y'] || [];

  const rateComparison = useMemo(() => {
    if (!tenYHistory.length || !twoYHistory.length) return [];
    const map = new Map();
    tenYHistory.forEach((p) => {
      if (p?.date != null) map.set(p.date, { date: p.date, ten: p.value });
    });
    twoYHistory.forEach((p) => {
      if (p?.date == null) return;
      const cur = map.get(p.date) || { date: p.date };
      cur.two = p.value;
      map.set(p.date, cur);
    });
    return Array.from(map.values()).sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [tenYHistory, twoYHistory]);

  const calendar = useMemo(() => {
    if (!Array.isArray(calendarRaw)) return [];
    return calendarRaw.map((e) => ({
      date: e.event_date || e.date,
      event: e.event_name || e.Event || e.event,
      importance: e.importance || e.Importance,
      forecast: e.forecast_value ?? e.Forecast,
      previous: e.previous_value ?? e.Previous,
      category: e.category || e.Category,
    }));
  }, [calendarRaw]);

  // Compute economic stress
  const stress = useMemo(() => {
    let sum = 0;
    let count = 0;
    const unrate = indicators.find((i) => i.name === 'Unemployment Rate');
    const claims = indicators.find((i) => i.name === 'Initial Jobless Claims');
    if (unrate?.rawValue != null) {
      sum += Math.min(100, Math.max(0, (unrate.rawValue - 3.5) * 20));
      count++;
    }
    if (claims?.rawValue != null) {
      sum += Math.min(100, Math.max(0, (claims.rawValue / 1000 - 200) * 2));
      count++;
    }
    const t10y2y = yieldData?.spreads?.T10Y2Y;
    if (t10y2y != null && t10y2y < 0) {
      sum += 25;
      count++;
    }
    if (count === 0) return null;
    return Math.round(Math.min(100, Math.max(0, sum / count)));
  }, [indicators, yieldData]);

  const recessionProbability = stress != null ? Math.round(stress * 0.5) : null;

  // ─── Recession Nowcasting Indicators ────────────────────────────────
  // Compose Sahm rule, yield curve, credit spread, jobless-claims trend.
  const recessionPanel = useMemo(() => {
    const tiles = [];

    // Sahm Rule: 3-month MA of UNRATE − min(UNRATE) over trailing 12 months
    const unrate = indicators.find((i) => i.name === 'Unemployment Rate');
    if (unrate?.history && unrate.history.length >= 12) {
      const hist = unrate.history.slice(-12).map((p) => Number(p.value)).filter((v) => !isNaN(v));
      if (hist.length >= 3) {
        const last3 = hist.slice(-3);
        const ma3 = last3.reduce((s, v) => s + v, 0) / last3.length;
        const min12 = Math.min(...hist);
        const sahm = ma3 - min12;
        tiles.push({
          label: 'Sahm Rule',
          desc: '3-mo unemployment MA vs trailing 12-mo low',
          value: `${sahm >= 0 ? '+' : ''}${sahm.toFixed(2)} pp`,
          threshold: '≥ 0.50 triggers',
          status: sahm >= 0.5 ? 'recession' : sahm >= 0.3 ? 'warn' : 'ok',
          weight: sahm >= 0.5 ? 100 : sahm >= 0.3 ? 60 : Math.max(0, sahm * 100),
        });
      }
    }

    // Yield curve: 10y-3m (or fall back to 10y-2y)
    const t10y3m = yieldData?.spreads?.T10Y3M;
    const t10y2y = yieldData?.spreads?.T10Y2Y;
    const spread = t10y3m != null ? t10y3m : t10y2y;
    if (spread != null) {
      tiles.push({
        label: t10y3m != null ? '10Y − 3M Curve' : '10Y − 2Y Curve',
        desc: 'Inversion preceded last 8 recessions',
        value: `${spread >= 0 ? '+' : ''}${(spread * 100).toFixed(0)} bps`,
        threshold: '< 0 inverts',
        status: spread < -0.5 ? 'recession' : spread < 0 ? 'warn' : 'ok',
        weight: spread < -0.5 ? 100 : spread < 0 ? 70 : Math.max(0, 50 - spread * 25),
      });
    }

    // High-yield credit spread (BAMLH0A0HYM2): elevated > 5%
    const hyHist = yieldData?.credit?.history?.['BAMLH0A0HYM2'] || [];
    const hyLatest = hyHist.length ? hyHist[hyHist.length - 1].value : null;
    if (hyLatest != null) {
      tiles.push({
        label: 'High-Yield Spread',
        desc: 'Bond stress above govt yields',
        value: `${hyLatest.toFixed(2)}%`,
        threshold: '> 5% elevated',
        status: hyLatest > 8 ? 'recession' : hyLatest > 5 ? 'warn' : 'ok',
        weight: hyLatest > 8 ? 100 : hyLatest > 5 ? 60 : Math.max(0, hyLatest * 10),
      });
    }

    // Initial Jobless Claims 6-month change
    const claims = indicators.find((i) => i.name === 'Initial Jobless Claims');
    if (claims?.history && claims.history.length >= 26) {
      const cur = Number(claims.rawValue);
      const past = Number(claims.history[claims.history.length - 27]?.value);
      if (!isNaN(cur) && !isNaN(past) && past > 0) {
        const pctChange = ((cur - past) / past) * 100;
        tiles.push({
          label: 'Jobless Claims 6m Δ',
          desc: '6-month change in initial claims',
          value: `${pctChange >= 0 ? '+' : ''}${pctChange.toFixed(1)}%`,
          threshold: '> +20% warning',
          status: pctChange > 30 ? 'recession' : pctChange > 20 ? 'warn' : 'ok',
          weight: pctChange > 30 ? 100 : pctChange > 20 ? 60 : Math.max(0, pctChange * 2),
        });
      }
    }

    // VIX as stress indicator
    const vixHist = yieldData?.credit?.history?.['VIXCLS'] || [];
    const vixLatest = vixHist.length ? vixHist[vixHist.length - 1].value : null;
    if (vixLatest != null) {
      tiles.push({
        label: 'VIX (Vol Index)',
        desc: 'Equity volatility / fear gauge',
        value: vixLatest.toFixed(1),
        threshold: '> 25 elevated',
        status: vixLatest > 35 ? 'recession' : vixLatest > 25 ? 'warn' : 'ok',
        weight: vixLatest > 35 ? 100 : vixLatest > 25 ? 60 : Math.max(0, vixLatest * 2),
      });
    }

    if (tiles.length === 0) return null;
    const compositeProb = Math.round(
      tiles.reduce((s, t) => s + t.weight, 0) / tiles.length
    );
    return { tiles, compositeProb };
  }, [indicators, yieldData]);

  // ─── Financial Conditions composite (VIX + HY spread + curve, normalized) ─
  const financialConditions = useMemo(() => {
    if (!yieldData?.credit?.history) return [];
    const vix = yieldData.credit.history['VIXCLS'] || [];
    const hy = yieldData.credit.history['BAMLH0A0HYM2'] || [];
    const curve = transformedHistory.spread_10y2y || [];
    if (vix.length < 10 || hy.length < 10) return [];

    const map = new Map();
    vix.forEach((p) => {
      if (p?.date == null) return;
      const k = String(p.date).slice(0, 10);
      const cur = map.get(k) || { date: k };
      cur.vix = Number(p.value);
      map.set(k, cur);
    });
    hy.forEach((p) => {
      if (p?.date == null) return;
      const k = String(p.date).slice(0, 10);
      const cur = map.get(k) || { date: k };
      cur.hy = Number(p.value);
      map.set(k, cur);
    });
    curve.forEach((p) => {
      if (p?.date == null) return;
      const k = String(p.date).slice(0, 10);
      const cur = map.get(k) || { date: k };
      // value is in basis points (T10Y2Y stored as % so it's fractional, e.g. -0.34)
      cur.curve = Number(p.value);
      map.set(k, cur);
    });
    // Compose FCI = z-normalized (vix + hy − curve), scaled to ~−3..+3
    const arr = Array.from(map.values()).filter((d) => d.vix != null && d.hy != null);
    if (arr.length === 0) return [];
    const meanV = arr.reduce((s, d) => s + d.vix, 0) / arr.length;
    const meanH = arr.reduce((s, d) => s + d.hy, 0) / arr.length;
    const sdV = Math.sqrt(arr.reduce((s, d) => s + (d.vix - meanV) ** 2, 0) / arr.length) || 1;
    const sdH = Math.sqrt(arr.reduce((s, d) => s + (d.hy - meanH) ** 2, 0) / arr.length) || 1;
    return arr
      .map((d) => ({
        date: d.date,
        // Higher = tighter / more stressful conditions
        fci: ((d.vix - meanV) / sdV) + ((d.hy - meanH) / sdH)
             + (d.curve != null ? -d.curve : 0),
      }))
      .sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [yieldData, transformedHistory]);

  const cats = useMemo(() => ({
    LEI: indicators.filter((i) => i.category === 'LEI'),
    LAGGING: indicators.filter((i) => i.category === 'LAGGING'),
    COINCIDENT: indicators.filter((i) => i.category === 'COINCIDENT'),
    SECONDARY: indicators.filter((i) => i.category === 'SECONDARY'),
  }), [indicators]);

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Economic Dashboard</div>
          <div className="page-head-sub">
            Recession probability, leading indicators, treasury curve and economic calendar
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={refetch} disabled={isLoading}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {(leadingQ.error || yieldQ.error) && (
        <div className="alert alert-danger" style={{ marginBottom: 'var(--space-4)' }}>
          <AlertCircle size={16} />
          <div>{leadingQ.error?.message || yieldQ.error?.message || 'Failed to load economic data'}</div>
        </div>
      )}

      {recessionProbability != null && recessionProbability > 40 && (
        <div className="alert alert-warn" style={{ marginBottom: 'var(--space-4)' }}>
          <AlertCircle size={16} />
          <div>
            <strong>Elevated Recession Risk:</strong> {recessionProbability}% probability —
            multiple economic warning signals detected. Monitor market conditions closely.
          </div>
        </div>
      )}

      {/* Health summary KPIs */}
      <div className="grid grid-3">
        <KpiTile
          label="Recession Risk"
          value={recessionProbability != null ? `${recessionProbability}%` : '—'}
          tone={stressTone(recessionProbability, 60, 35)}
          bar={recessionProbability}
        />
        <KpiTile
          label="Economic Stress"
          value={stress != null ? `${stress}` : '—'}
          tone={stressTone(stress, 60, 30)}
          bar={stress}
        />
        <KpiTile
          label="Yield Curve"
          value={yieldData?.spreads?.T10Y2Y != null ? `${fmtBps(yieldData.spreads.T10Y2Y)} bps` : '—'}
          tone={yieldData?.spreads?.T10Y2Y != null ? (yieldData.spreads.T10Y2Y < 0 ? 'down' : 'up') : 'flat'}
          sub={yieldData?.isInverted ? 'Inverted — recession signal' : 'Normal curve'}
        />
      </div>

      {/* Yield curve status banner + key maturities */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Treasury Yield Curve</div>
            <div className="card-sub">3M to 30Y — current snapshot &amp; spreads</div>
          </div>
          <div className="card-actions">
            <span className={`badge ${yieldData?.isInverted ? 'badge-danger' : 'badge-success'}`}>
              {yieldData?.isInverted ? 'INVERTED CURVE' : 'NORMAL CURVE'}
            </span>
          </div>
        </div>
        <div className="card-body">
          <div className="grid grid-4" style={{ marginBottom: 'var(--space-5)' }}>
            <Stile label="3-Month" value={yieldData?.currentCurve?.['3M'] != null ? `${num(yieldData.currentCurve['3M'])}%` : '—'} />
            <Stile label="2-Year"  value={yieldData?.currentCurve?.['2Y'] != null ? `${num(yieldData.currentCurve['2Y'])}%` : '—'} />
            <Stile label="10-Year" value={yieldData?.currentCurve?.['10Y'] != null ? `${num(yieldData.currentCurve['10Y'])}%` : '—'} />
            <Stile label="30-Year" value={yieldData?.currentCurve?.['30Y'] != null ? `${num(yieldData.currentCurve['30Y'])}%` : '—'} />
          </div>

          {yieldCurveData.length > 0 ? (
            <div style={{ height: 320 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={yieldCurveData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                  <XAxis dataKey="maturity" stroke="var(--text-3)" fontSize={11} />
                  <YAxis stroke="var(--text-3)" fontSize={11} domain={[0, 'auto']}
                         tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    formatter={(v) => v != null ? [`${Number(v).toFixed(3)}%`, 'Yield'] : ['—', 'Yield']}
                  />
                  <Line type="monotone" dataKey="yield" stroke="var(--brand)" strokeWidth={2.5}
                        dot={{ fill: 'var(--brand)', r: 4 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="No yield curve data" desc="Run the FRED economic loader to populate treasury yields." />
          )}
        </div>
      </div>

      {/* Spread + comparison charts */}
      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">10Y - 2Y Spread</div>
              <div className="card-sub">Primary recession indicator (T10Y2Y)</div>
            </div>
          </div>
          <div className="card-body">
            {spreadHistory.length > 0 ? (
              <div style={{ height: 280 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={spreadHistory} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="ecoSpread" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                    <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10}
                           tickFormatter={fmtMonth} interval="preserveStartEnd" />
                    <YAxis stroke="var(--text-3)" fontSize={10}
                           tickFormatter={(v) => `${Math.round(v)}`} />
                    <Tooltip
                      contentStyle={TOOLTIP_STYLE}
                      formatter={(v) => v != null ? [`${Math.round(v)} bps`, 'Spread'] : ['—', 'Spread']}
                      labelFormatter={(d) => fmtDate(d)}
                    />
                    <ReferenceLine y={0} stroke="var(--danger)" strokeDasharray="4 4" />
                    <Area type="monotone" dataKey="value" stroke="var(--brand)"
                          strokeWidth={2} fill="url(#ecoSpread)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Empty title="No spread history" />
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">10Y vs 2Y Yields</div>
              <div className="card-sub">Comparison over time</div>
            </div>
          </div>
          <div className="card-body">
            {rateComparison.length > 0 ? (
              <div style={{ height: 280 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={rateComparison} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                    <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10}
                           tickFormatter={fmtMonth} interval="preserveStartEnd" />
                    <YAxis stroke="var(--text-3)" fontSize={10}
                           tickFormatter={(v) => `${Number(v).toFixed(1)}%`} />
                    <Tooltip
                      contentStyle={TOOLTIP_STYLE}
                      formatter={(v, name) => [v != null ? `${Number(v).toFixed(2)}%` : '—', name]}
                      labelFormatter={(d) => fmtDate(d)}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-3)' }} />
                    <Line type="monotone" dataKey="ten" name="10Y" stroke="var(--brand)"
                          strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="two" name="2Y" stroke="var(--amber)"
                          strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Empty title="No comparison data" />
            )}
          </div>
        </div>
      </div>

      {/* Recession Nowcasting Panel */}
      {recessionPanel && (
        <div className="card" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-head">
            <div>
              <div className="card-title">Recession Nowcasting</div>
              <div className="card-sub">
                Composite probability across {recessionPanel.tiles.length} indicators · Sahm rule, yield curve,
                credit spreads, jobless claims, vol regime
              </div>
            </div>
            <div className="card-actions">
              <span className={`badge ${recessionPanel.compositeProb >= 60 ? 'badge-danger'
                                      : recessionPanel.compositeProb >= 35 ? 'badge-amber'
                                      : 'badge-success'}`}>
                {recessionPanel.compositeProb}% composite
              </span>
            </div>
          </div>
          <div className="card-body">
            <div className="bar" style={{ marginBottom: 'var(--space-4)' }}>
              <div className="bar-fill" style={{
                width: `${recessionPanel.compositeProb}%`,
                background: recessionPanel.compositeProb >= 60 ? 'var(--danger)'
                          : recessionPanel.compositeProb >= 35 ? 'var(--amber)'
                          : 'var(--success)',
              }} />
            </div>
            <div className="grid grid-3">
              {recessionPanel.tiles.map((t) => (
                <div className="stile" key={t.label}>
                  <div className="stile-label">{t.label}</div>
                  <div className={`stile-value ${t.status === 'recession' ? 'down' : t.status === 'ok' ? 'up' : ''}`}>
                    {t.value}
                  </div>
                  <div className="stile-sub">
                    <span className={`badge ${t.status === 'recession' ? 'badge-danger'
                                            : t.status === 'warn' ? 'badge-amber'
                                            : 'badge-success'}`}>
                      {t.status === 'recession' ? 'TRIGGERED' : t.status === 'warn' ? 'WARN' : 'OK'}
                    </span>{' '}
                    <span className="muted">{t.threshold}</span>
                  </div>
                  <div className="t-2xs muted" style={{ marginTop: 'var(--space-1)' }}>{t.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Financial Conditions composite */}
      {financialConditions.length > 0 && (
        <div className="card" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-head">
            <div>
              <div className="card-title">Financial Conditions Composite</div>
              <div className="card-sub">
                Z-normalized blend: VIX + high-yield spread − yield curve · higher = tighter / more stress
              </div>
            </div>
          </div>
          <div className="card-body">
            <div style={{ height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={financialConditions} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="fciGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--purple)" stopOpacity={0.45} />
                      <stop offset="100%" stopColor="var(--purple)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                  <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10}
                         tickFormatter={fmtMonth} interval="preserveStartEnd" />
                  <YAxis stroke="var(--text-3)" fontSize={10}
                         tickFormatter={(v) => Number(v).toFixed(1)} />
                  <Tooltip contentStyle={TOOLTIP_STYLE}
                           labelFormatter={(d) => fmtDate(d)}
                           formatter={(v) => [`${Number(v).toFixed(2)} σ`, 'FCI']} />
                  <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="4 4" />
                  <Area type="monotone" dataKey="fci" stroke="var(--purple)"
                        strokeWidth={2} fill="url(#fciGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="t-xs muted" style={{ marginTop: 'var(--space-2)' }}>
              Above 0σ = above-average stress · below 0σ = easier conditions. Components: VIX volatility,
              high-yield bond spread, treasury curve.
            </div>
          </div>
        </div>
      )}

      {/* Indicator categories */}
      <IndicatorSection title="Leading Economic Indicators" icon={<TrendingUp size={16} />} list={cats.LEI} />
      <IndicatorSection title="Coincident Indicators"      icon={<Activity size={16} />}    list={cats.COINCIDENT} />
      <IndicatorSection title="Lagging Indicators"         icon={<TrendingDown size={16} />} list={cats.LAGGING} />
      <IndicatorSection title="Secondary Indicators"       icon={<Minus size={16} />}       list={cats.SECONDARY} />

      {/* Economic Calendar */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Economic Calendar</div>
            <div className="card-sub">Upcoming releases &amp; events</div>
          </div>
          <div className="card-actions">
            <CalendarDays size={16} className="muted" />
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {calendar.length === 0 ? (
            <Empty title="No upcoming economic events" />
          ) : (
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
                  {calendar.map((e, idx) => (
                    <tr key={`${e.date}-${e.event}-${idx}`}>
                      <td className="t-xs muted">{fmtDate(e.date)}</td>
                      <td><span className="strong">{e.event}</span></td>
                      <td className="t-xs muted">{e.category || '—'}</td>
                      <td>
                        <span className={`badge ${importanceBadge(e.importance)}`}>
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
    </div>
  );
}

function IndicatorSection({ title, icon, list }) {
  if (!list || list.length === 0) return null;
  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title flex items-center gap-2">{icon} {title}</div>
          <div className="card-sub">{list.length} series</div>
        </div>
      </div>
      <div className="card-body">
        <div className="grid grid-2">
          {list.map((ind, idx) => (
            <IndicatorCard key={`${ind.name}-${idx}`} indicator={ind} idx={idx} />
          ))}
        </div>
      </div>
    </div>
  );
}

function IndicatorCard({ indicator, idx }) {
  const tone = trendTone(indicator.trend);
  const change = indicator.change;
  const changeTone = change > 0 ? 'up' : change < 0 ? 'down' : 'flat';
  const gradId = `econInd-${idx}-${(indicator.name || '').replace(/\s+/g, '')}`;

  return (
    <div className="panel" style={{ padding: 'var(--space-5)' }}>
      <div className="flex items-start justify-between gap-3" style={{ marginBottom: 'var(--space-3)' }}>
        <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
          <span className={tone}>{trendIcon(indicator.trend, 18)}</span>
          <div style={{ minWidth: 0 }}>
            <div className="strong" style={{ fontSize: 'var(--t-md)', fontWeight: 'var(--w-semibold)' }}>
              {indicator.name}
            </div>
            {indicator.description && (
              <div className="t-xs muted truncate">{indicator.description}</div>
            )}
          </div>
        </div>
        {indicator.signal && (
          <span className={`badge ${signalToBadge(indicator.signal)}`}>{indicator.signal}</span>
        )}
      </div>

      <div className="flex items-baseline gap-3" style={{ marginBottom: 'var(--space-3)' }}>
        <div className={`mono tnum ${tone}`}
             style={{ fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)', letterSpacing: '-0.5px' }}>
          {indicator.value}
        </div>
        {change != null && !isNaN(Number(change)) && (
          <div className={`mono tnum ${changeTone}`} style={{ fontSize: 'var(--t-sm)', fontWeight: 'var(--w-semibold)' }}>
            {change > 0 ? '+' : ''}{Number(change).toFixed(2)}%
          </div>
        )}
      </div>

      {Array.isArray(indicator.history) && indicator.history.length > 1 && (
        <div style={{ height: 180 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={indicator.history} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="date" stroke="var(--text-3)" fontSize={10}
                     tickFormatter={fmtMonth}
                     interval={Math.floor(indicator.history.length / 6) || 0} />
              <YAxis stroke="var(--text-3)" fontSize={10} width={48} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(v) => v != null ? [Number(v).toFixed(2), 'Value'] : ['—', 'Value']}
                labelFormatter={(d) => fmtDate(d)}
              />
              <Area type="monotone" dataKey="value" stroke="var(--brand)" strokeWidth={2}
                    fill={`url(#${gradId})`} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {indicator.date && (
        <div className="t-2xs muted" style={{ marginTop: 'var(--space-3)', paddingTop: 'var(--space-2)', borderTop: '1px solid var(--border-soft)' }}>
          Updated: {fmtDate(indicator.date)}
        </div>
      )}
    </div>
  );
}

function KpiTile({ label, value, tone, sub, bar }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="eyebrow">{label}</div>
      <div className={`mono ${tone || ''}`}
           style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
        {value}
      </div>
      {sub && <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>{sub}</div>}
      {bar != null && !isNaN(Number(bar)) && (
        <div className="bar" style={{ marginTop: 'var(--space-3)' }}>
          <div className="bar-fill"
               style={{
                 width: `${Math.min(100, Math.max(0, Number(bar)))}%`,
                 background: tone === 'down' ? 'var(--danger)' : tone === 'flat' ? 'var(--amber)' : 'var(--success)',
               }} />
        </div>
      )}
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
