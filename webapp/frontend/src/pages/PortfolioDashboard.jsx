/**
 * Portfolio Dashboard — algo-only.
 *
 * Surfaces every metric the algo tracks: open positions w/ R/stop/targets,
 * performance ratios (Sharpe / Sortino / Calmar / max DD), trade-level
 * win rate / expectancy / profit factor, equity-curve from algo_portfolio_snapshots,
 * exposure context from market regime. Plus deep risk + composition analytics:
 * R-ladder, risk-pie, sector-bars, stage-donut, return-histogram, drawdown,
 * setup outcomes, holding histogram, position health, circuit breakers.
 *
 * Pure JSX + theme.css classes. Recharts only.
 */

import React, { useMemo } from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import {
  RefreshCw, TrendingUp, Activity, Shield,
  Inbox, DollarSign, BarChart3, Zap, AlertTriangle,
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, Cell, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, PieChart, Pie, Legend, ReferenceLine,
} from 'recharts';
import { useApiQuery } from '../hooks/useApiQuery';
import { api } from '../services/api';
import ErrorBoundary from '../components/ErrorBoundary';
import { SkeletonKpi, SkeletonChart, SkeletonTable, SkeletonCircuitBreaker, SkeletonChartContent, AddGlobalStyles } from '../components/Skeleton';
import { fmtMoney, fmtMoneyShort, num, pct } from '../components/dashboard/shared/utils/dashboardFormatters';

const Pnl = ({ value, suffix = '' }) => {
  if (value == null || isNaN(Number(value))) return <span className="muted">—</span>;
  const v = Number(value);
  const cls = v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
  const sign = v > 0 ? '+' : '';
  return (
    <span className={`mono tnum ${cls}`} style={{ fontWeight: 'var(--w-semibold)' }}>
      {sign}{v.toFixed(2)}{suffix}
    </span>
  );
};

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
  boxShadow: 'var(--shadow-md)',
};

const PIE_PALETTE = [
  'var(--brand)', 'var(--cyan)', 'var(--purple)', 'var(--success)',
  'var(--amber)', 'var(--danger)', '#8BC34A', '#E91E63',
  '#FFC107', '#795548', '#607D8B', '#FF6B6B',
];

// Reusable style objects to prevent recreation on every render
const MARKER_STYLE_BASE = {
  position: 'absolute', top: -4, bottom: -4,
  display: 'flex', flexDirection: 'column', alignItems: 'center',
  pointerEvents: 'none',
};

const MARKER_LINE_STYLE = (big, color) => ({
  width: big ? 4 : 2, flex: 1, background: color,
  borderRadius: 'var(--r-pill)',
  boxShadow: big ? `0 0 4px ${color}` : 'none',
});

const MARKER_LABEL_STYLE = (color) => ({
  fontSize: 'var(--t-2xs)', color, fontWeight: 'var(--w-bold)',
  marginTop: 2, lineHeight: 1, whiteSpace: 'nowrap',
});

const LADDER_TRACK_STYLE = {
  position: 'relative', height: 28, background: 'var(--surface-2)',
  borderRadius: 'var(--r-pill)', overflow: 'visible',
  border: '1px solid var(--border-soft)',
};

const LADDER_FILL_STYLE = (pStop, pCur, pEntry) => ({
  position: 'absolute', top: 0, bottom: 0,
  left: `${Math.min(pStop, pCur)}%`,
  width: `${Math.max(0, Math.abs(pCur - pStop))}%`,
  background: pCur >= pEntry
    ? 'linear-gradient(90deg, var(--danger) 0%, var(--amber) 50%, var(--success) 100%)'
    : 'linear-gradient(90deg, var(--danger) 0%, var(--amber) 100%)',
  opacity: 0.35,
  borderRadius: 'var(--r-pill)',
});

// Data extraction helpers — consistent patterns for normalizing API responses
const extractArray = (data, defaultKey = 'items') => {
  if (Array.isArray(data)) return data;
  if (data && typeof data === 'object' && Array.isArray(data[defaultKey])) return data[defaultKey];
  return [];
};

const extractNestedValue = (obj, path, defaultValue = null) => {
  if (!obj || typeof obj !== 'object') return defaultValue;
  const keys = path.split('.');
  let val = obj;
  for (const key of keys) {
    val = val?.[key];
    if (val === undefined) return defaultValue;
  }
  return val ?? defaultValue;
};

const hasError = (data) => data?._error != null;
const isCached = (data) => data?.fromCache === true;
const isPlaceholder = (data) => data?._is_placeholder === true;

const CachedDataBadge = () => (
  <span className="badge badge-amber" style={{ fontSize: 'var(--t-xs)', marginLeft: 'var(--space-1)' }}>
    🔄 Cached
  </span>
);

const formatErrorDetail = (err, context) => {
  if (!err) return null;
  if (typeof err === 'string') return err;

  // Log to console for devtools debugging
  if (context) {
    console.error(`[Portfolio] ${context}:`, {
      message: err.message,
      status: err.status,
      code: err.code,
      url: err.url,
      responseData: err.responseData,
    });
  }

  const parts = [];
  if (err.message) parts.push(err.message);
  if (err.status) parts.push(`HTTP ${err.status}`);
  if (err.code) parts.push(`(${err.code})`);
  if (err.url) parts.push(`URL: ${err.url}`);
  if (err.responseData?.error) parts.push(`Server: ${err.responseData.error}`);
  if (err.responseData?.message) parts.push(`Server: ${err.responseData.message}`);
  return parts.length > 0 ? parts.join(' • ') : 'Unknown error';
};

function PortfolioDashboardPage() {
  const navigate = useNavigate();

  // Determine if any query is loading to show skeleton UI
  const { data: status, loading: statusLoading, error: statusError, refetch: refetchStatus } = useApiQuery(
    ['algo-status'],
    () => api.get('/api/algo/status'),
  );
  const { data: positions, loading: posLoading, error: posError, refetch: refetchPositions } = useApiQuery(
    ['algo-positions'],
    () => api.get('/api/algo/positions'),
  );
  const { data: perf, loading: perfLoading, error: perfError, refetch: refetchPerf } = useApiQuery(
    ['algo-performance'],
    () => api.get('/api/algo/performance'),
  );
  const { data: trades, loading: tradesLoading, error: tradesError, refetch: refetchTrades } = useApiQuery(
    ['algo-trades-recent'],
    () => api.get('/api/algo/trades?limit=200'),
  );
  const { data: markets, loading: marketsLoading, error: marketsError, refetch: refetchMarkets } = useApiQuery(
    ['algo-markets'],
    () => api.get('/api/algo/markets'),
  );
  const { data: equityItems, loading: equityLoading, error: equityError, refetch: refetchEquity } = useApiQuery(
    ['algo-equity-curve'],
    () => api.get('/api/algo/equity-curve?limit=180'),
  );
  const { data: breakers, loading: breakersLoading, error: _breakersError, refetch: refetchBreakers } = useApiQuery(
    ['algo-circuit-breakers'],
    () => api.get('/api/algo/circuit-breakers'),
  );
  const { data: returnHistogram, loading: histogramLoading, error: histogramError, refetch: refetchHistogram } = useApiQuery(
    ['algo-daily-return-histogram'],
    () => api.get('/api/algo/daily-return-histogram'),
  );
  const { data: tradeDistribution, loading: distLoading, error: distError, refetch: refetchDistribution } = useApiQuery(
    ['algo-trade-distribution'],
    () => api.get('/api/algo/trade-distribution'),
  );
  const { data: holdingDistribution, loading: holdingLoading, error: holdingError, refetch: refetchHolding } = useApiQuery(
    ['algo-holding-period-distribution'],
    () => api.get('/api/algo/holding-period-distribution'),
  );
  const { data: stageDistribution, loading: stageLoading, error: stageError, refetch: refetchStage } = useApiQuery(
    ['algo-stage-distribution'],
    () => api.get('/api/algo/stage-distribution'),
  );

  // Check if primary data is still loading (avoid flickering by holding skeletons until main data arrives)
  // Includes all query states to prevent skeleton loaders from showing/hiding at different times
  const isPrimaryLoading = statusLoading || posLoading || perfLoading || marketsLoading || equityLoading || tradesLoading || breakersLoading || histogramLoading || distLoading || holdingLoading || stageLoading;

  // Normalize paginated responses using consistent extraction pattern
  const positionsList = extractArray(positions);
  const tradesList = extractArray(trades);
  const equityCurve = extractArray(equityItems);
  const sectorAllocation = extractArray(positions, 'sector_allocation');

  // Apply null safety and domain-specific filtering
  const safePositionsList = positionsList.length > 0 ? positionsList : [];
  const safeTradesList = tradesList.length > 0
    ? tradesList.filter(t => t.status === 'closed')
    : [];
  const safeEquityCurve = equityCurve.length > 0
    ? equityCurve.filter(item => item && typeof item === 'object' && item.date && (item.value != null || item.equity != null))
    : [];

  // Extract portfolio data with consistent nested access
  const portfolio = extractNestedValue(status, 'portfolio', {});
  const currentExp = extractNestedValue(markets, 'current', {});
  const currentHealth = extractNestedValue(markets, 'market_health', {});
  const market = {
    trend: currentHealth.market_trend || 'unknown',
    stage: currentHealth.market_stage ?? 0,
    vix: currentHealth.vix_level ?? 0,
    distribution_days: currentExp.distribution_days_4w ?? currentExp.distribution_days ?? 0,
  };

  // Compute portfolio metrics
  const unrealizedPnl = portfolio.unrealized_pnl_dollars ?? 0;
  const totalPositionValue = safePositionsList.reduce((s, p) => {
    const val = Number(p?.position_value ?? 0);
    return s + (isNaN(val) ? 0 : val);
  }, 0);
  const totalValue = (portfolio.total_value != null && !isNaN(Number(portfolio.total_value)))
    ? parseFloat(portfolio.total_value)
    : (totalPositionValue || 0);

  // Unified error and cache detection using helper functions
  const hasCachedPerf = isCached(perf);
  const hasCachedTrades = isCached(trades);
  const hasCachedEquity = isCached(equityItems);

  const perfDataError = hasError(perf) ? perf._error : null;
  const tradesDataError = hasError(trades) ? trades._error : null;
  const posDataError = hasError(positions) ? positions._error : null;
  const marketsDataError = hasError(markets) ? markets._error : null;
  const equityDataError = hasError(equityItems) ? equityItems._error : null;
  const statusDataError = hasError(status) ? status._error : null;

  const isPerfPlaceholder = isPlaceholder(perf);
  const isEquityPlaceholder = isPlaceholder(equityItems);
  const isTradesPlaceholder = isPlaceholder(trades);
  const isReturnHistogramPlaceholder = isPlaceholder(returnHistogram);
  const isDistributionPlaceholder = isPlaceholder(tradeDistribution);
  const isHoldingPlaceholder = isPlaceholder(holdingDistribution);

  // Show error banner for individual errors, but don't block entire dashboard (graceful degradation)
  // Only show errors that don't have cached fallback data
  const criticalErrors = [
    statusError || statusDataError,
    posError || posDataError,
    (perfError && !hasCachedPerf ? perfError : null) || (perfDataError && !hasCachedPerf ? perfDataError : null),
    (tradesError && !hasCachedTrades ? tradesError : null) || (tradesDataError && !hasCachedTrades ? tradesDataError : null),
    marketsError || marketsDataError,
    (equityError && !hasCachedEquity ? equityError : null) || (equityDataError && !hasCachedEquity ? equityDataError : null)
  ];
  const hasAnyError = criticalErrors.some(err => err);
  const errorList = [];
  if (statusError || statusDataError) errorList.push({ section: 'Status', error: statusError || statusDataError });
  if (posError || posDataError) errorList.push({ section: 'Positions', error: posError || posDataError });
  if ((perfError && !hasCachedPerf) || (perfDataError && !hasCachedPerf)) errorList.push({ section: 'Performance', error: perfError || perfDataError });
  if ((tradesError && !hasCachedTrades) || (tradesDataError && !hasCachedTrades)) errorList.push({ section: 'Recent Trades', error: tradesError || tradesDataError });
  if (marketsError || marketsDataError) errorList.push({ section: 'Markets', error: marketsError || marketsDataError });
  if ((equityError && !hasCachedEquity) || (equityDataError && !hasCachedEquity)) errorList.push({ section: 'Equity Curve', error: equityError || equityDataError });

  // Show stale data banner (but not as error — just informational)
  const staleSections = [];
  if (hasCachedPerf && perfError) staleSections.push('Performance metrics');
  if (hasCachedTrades && tradesError) staleSections.push('Recent trades');
  if (hasCachedEquity && equityError) staleSections.push('Equity curve');

  return (
    <div className="main-content">
      <AddGlobalStyles />
      <div className="page-head">
        <div>
          <div className="page-head-title">Portfolio</div>
          <div className="page-head-sub">
            Algo positions · Performance · Risk profile · Market context
          </div>
        </div>
        <div className="page-head-actions" style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button className="btn btn-outline btn-sm" onClick={() => navigate('/app/algo-dashboard')}>
            Terminal Dashboard
          </button>
          <button className="btn btn-outline btn-sm" onClick={() => {
            refetchStatus();
            refetchPositions();
            refetchPerf();
            refetchTrades();
            refetchMarkets();
            refetchEquity();
            refetchBreakers();
            refetchHistogram();
            refetchDistribution();
            refetchHolding();
            refetchStage();
          }}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Stale data banner (from cache fallback) */}
      {staleSections.length > 0 && (
        <div className="card" style={{ background: 'rgba(255, 193, 7, 0.1)', borderLeft: '3px solid var(--amber)', marginBottom: 'var(--space-4)' }}>
          <div style={{ padding: 'var(--space-3)' }}>
            <div style={{ fontWeight: 'var(--w-semibold)', marginBottom: 'var(--space-2)' }}>
              🔄 Using recent cached data
            </div>
            <div className="muted t-sm" style={{ marginBottom: 'var(--space-3)' }}>
              {staleSections.join(', ')} couldn't reach the server. Showing last known state while we reconnect.
            </div>
            <button
              className="btn btn-sm"
              onClick={() => {
                if (hasCachedPerf && perfError) refetchPerf?.();
                if (hasCachedTrades && tradesError) refetchTrades?.();
                if (hasCachedEquity && equityError) refetchEquity?.();
              }}
            >
              <RefreshCw size={14} /> Refresh Now
            </button>
          </div>
        </div>
      )}

      {/* Error banner for individual API failures (graceful degradation) */}
      {hasAnyError && (
        <div className="card" style={{ background: 'var(--surface-warning)', borderLeft: '3px solid var(--warning)', marginBottom: 'var(--space-4)' }}>
          <div style={{ padding: 'var(--space-3)' }}>
            <div style={{ fontWeight: 'var(--w-semibold)', marginBottom: 'var(--space-2)' }}>
              ⚠️ Some data is unavailable
            </div>
            <div className="muted t-sm" style={{ marginBottom: 'var(--space-3)' }}>
              {errorList.map((item, idx) => (
                <div key={idx} style={{ marginBottom: 'var(--space-1)' }}>
                  {item.section}: {formatErrorDetail(item.error)}
                </div>
              ))}
            </div>
            <button
              className="btn btn-sm"
              onClick={() => {
                statusError && refetchStatus?.();
                posError && refetchPositions?.();
                if (perfError && !hasCachedPerf) refetchPerf?.();
                if (tradesError && !hasCachedTrades) refetchTrades?.();
                marketsError && refetchMarkets?.();
                if (equityError && !hasCachedEquity) refetchEquity?.();
              }}
            >
              <RefreshCw size={14} /> Retry Failed Requests
            </button>
          </div>
        </div>
      )}

      {/* Top KPI strip */}
      {isPrimaryLoading ? (
        <div className="grid grid-4">
          <SkeletonKpi />
          <SkeletonKpi />
          <SkeletonKpi />
          <SkeletonKpi />
        </div>
      ) : (perfDataError && !hasCachedPerf) || posDataError ? (
        <div className="card card-danger">
          <div className="card-body">
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              <AlertTriangle size={20} style={{ color: 'var(--danger)' }} />
              <div>
                <div style={{ fontWeight: 'var(--w-semibold)' }}>Critical Data Unavailable</div>
                <div style={{ fontSize: 'var(--t-sm)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>
                  {perfDataError && !hasCachedPerf ? perfDataError : posDataError}
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-4">
          <Kpi
            label="Portfolio Value"
            value={fmtMoneyShort(totalValue)}
            sub={`${safePositionsList.length} open positions`}
            icon={DollarSign}
          />
          <Kpi
            label="Unrealized P&L"
            value={<Pnl value={totalValue > 0 ? (unrealizedPnl / totalValue * 100) : null} suffix="%" />}
            sub={`$${unrealizedPnl >= 0 ? '+' : ''}${unrealizedPnl.toFixed(0)} unrealized`}
            icon={Activity}
            tone={unrealizedPnl >= 0 ? 'up' : 'down'}
          />
          <Kpi
            label="Total Return"
            value={<Pnl value={perf?.total_return_pct} suffix="%" />}
            sub={`${perf?.total_trades ?? 0} closed trades`}
            icon={TrendingUp}
            tone={perf?.total_return_pct >= 0 ? 'up' : 'down'}
          />
          <Kpi
            label="Market Regime"
            value={<span className="mono">{(market.trend || '—').toString().toUpperCase()}</span>}
            sub={`Stage ${market.stage ?? '—'} · DD ${market.distribution_days ?? 0}`}
            icon={Shield}
          />
        </div>
      )}

      {/* Ratios row */}
      {hasCachedPerf && <div style={{ marginTop: 'var(--space-4)', marginBottom: 'var(--space-2)' }}><CachedDataBadge /> Performance Metrics (from cache)</div>}
      {isPerfPlaceholder && <div style={{ marginTop: 'var(--space-4)', marginBottom: 'var(--space-2)' }}><span className="badge badge-warning">⚠️ Placeholder</span> Performance Metrics (building trading history)</div>}
      {isPrimaryLoading ? (
        <div className="grid grid-4" style={{ marginTop: 'var(--space-4)' }}>
          <SkeletonKpi />
          <SkeletonKpi />
          <SkeletonKpi />
          <SkeletonKpi />
        </div>
      ) : perfDataError && !hasCachedPerf ? (
        <div className="card card-danger" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-body">
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              <AlertTriangle size={20} style={{ color: 'var(--danger)' }} />
              <div>
                <div style={{ fontWeight: 'var(--w-semibold)' }}>Performance Metrics Unavailable</div>
                <div style={{ fontSize: 'var(--t-sm)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>{perfDataError}</div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-4" style={{ marginTop: hasCachedPerf ? 'var(--space-2)' : 'var(--space-4)' }}>
          <Kpi
            label="Sharpe (annualized)"
            value={<span className="mono tnum">{num(perf?.sharpe_annualized)}</span>}
            sub="risk-adjusted"
            icon={BarChart3}
            tone={perf?.sharpe_annualized > 1 ? 'up' : perf?.sharpe_annualized < 0 ? 'down' : ''}
          />
          <Kpi
            label="Sortino"
            value={<span className="mono tnum">{num(perf?.sortino_annualized)}</span>}
            sub="downside-only"
            icon={Shield}
          />
          <Kpi
            label="Calmar"
            value={<span className="mono tnum">{num(perf?.calmar_ratio)}</span>}
            sub={`Max DD ${pct(perf?.max_drawdown_pct, 1)}`}
            icon={AlertTriangle}
            tone={perf?.calmar_ratio > 1 ? 'up' : perf?.max_drawdown_pct > 20 ? 'down' : ''}
          />
          <Kpi
            label="Profit Factor"
            value={<span className="mono tnum">{perf?.profit_factor == null ? '—' : num(perf.profit_factor)}</span>}
            sub={`${perf?.win_rate_pct ?? 0}% win rate`}
            icon={Zap}
            tone={perf?.profit_factor > 1.5 ? 'up' : perf?.profit_factor < 1 ? 'down' : ''}
          />
        </div>
      )}

      {/* Circuit breakers */}
      <CircuitBreakerPanel data={breakers} loading={isPrimaryLoading} />

      {/* Equity curve + Drawdown chart */}
      {equityDataError && !hasCachedEquity ? (
        <div className="card card-danger" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-body">
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              <AlertTriangle size={20} style={{ color: 'var(--danger)' }} />
              <div>
                <div style={{ fontWeight: 'var(--w-semibold)' }}>Equity Curve & Analytics Unavailable</div>
                <div style={{ fontSize: 'var(--t-sm)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>{equityDataError}</div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
          <ErrorBoundary>
            <EquityCurve series={safeEquityCurve} loading={isPrimaryLoading} />
          </ErrorBoundary>
          <ErrorBoundary>
            <DrawdownChart series={safeEquityCurve} loading={isPrimaryLoading} />
          </ErrorBoundary>
        </div>
      )}

      {/* Daily-return histogram + Trade outcome distribution */}
      {tradesDataError && !hasCachedTrades ? (
        <div className="card card-danger" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-body">
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              <AlertTriangle size={20} style={{ color: 'var(--danger)' }} />
              <div>
                <div style={{ fontWeight: 'var(--w-semibold)' }}>Trade Analytics Unavailable</div>
                <div style={{ fontSize: 'var(--t-sm)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>{tradesDataError}</div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
          <ErrorBoundary>
            <DailyReturnHistogram histogram_data={returnHistogram} loading={isPrimaryLoading} />
          </ErrorBoundary>
          <ErrorBoundary>
            <TradeDistribution distribution_data={tradeDistribution} loading={isPrimaryLoading} />
          </ErrorBoundary>
        </div>
      )}

      {/* R-multiple ladder */}
      <ErrorBoundary>
        <RLadderPanel positions={safePositionsList} loading={isPrimaryLoading}
                      onSelect={(s) => navigate(`/app/stock/${encodeURIComponent(s)}`)} />
      </ErrorBoundary>

      {/* Risk-pie + Sector concentration + Stage donut */}
      <div className="grid grid-3" style={{ marginTop: 'var(--space-4)' }}>
        <ErrorBoundary>
          <RiskAllocationPie positions={safePositionsList} totalValue={totalValue} loading={isPrimaryLoading}
                              onSelect={(s) => navigate(`/app/stock/${encodeURIComponent(s)}`)} />
        </ErrorBoundary>
        <ErrorBoundary>
          <SectorConcentration sector_allocation={sectorAllocation} loading={isPrimaryLoading} />
        </ErrorBoundary>
        <ErrorBoundary>
          <StagePhaseDonut distribution={stageDistribution} loading={isPrimaryLoading} />
        </ErrorBoundary>
      </div>

      {/* Position-health table */}
      <ErrorBoundary>
        <PositionHealthTable positions={safePositionsList} loading={isPrimaryLoading}
                              onSelect={(s) => navigate(`/app/stock/${encodeURIComponent(s)}`)} />
      </ErrorBoundary>

      {/* Trade-level metrics + holding-period histogram */}
      {perfDataError && !hasCachedPerf ? (
        <div className="card card-danger" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-body">
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              <AlertTriangle size={20} style={{ color: 'var(--danger)' }} />
              <div>
                <div style={{ fontWeight: 'var(--w-semibold)' }}>Trade Metrics Unavailable</div>
                <div style={{ fontSize: 'var(--t-sm)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>{perfDataError}</div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">Trade Metrics</div>
                <div className="card-sub">Closed trades · win/loss profile · expectancy</div>
              </div>
            </div>
            <div className="card-body">
              <div className="grid grid-3">
                <Stile label="Avg Win" value={<Pnl value={perf?.avg_win_pct} suffix="%" />} />
                <Stile label="Avg Loss" value={<Pnl value={perf?.avg_loss_pct} suffix="%" />} />
                <Stile label="Expectancy" value={<span className="mono tnum">{num(perf?.expectancy_r, 3)}R</span>} />
                <Stile label="Avg Win R" value={<span className="mono tnum">{num(perf?.avg_win_r)}R</span>} />
                <Stile label="Avg Loss R" value={<span className="mono tnum">{num(perf?.avg_loss_r)}R</span>} />
                <Stile label="Avg Hold" value={<span className="mono tnum">{num(perf?.avg_hold_days, 1)}d</span>} />
                <Stile label="Best Streak" value={<span className="mono tnum up">{perf?.best_win_streak ?? 0}W</span>} />
                <Stile label="Worst Streak" value={<span className="mono tnum down">{perf?.worst_loss_streak ?? 0}L</span>} />
                <Stile label="Current" value={<StreakValue v={perf?.current_streak} />} />
              </div>
              <div style={{ marginTop: 'var(--space-4)', paddingTop: 'var(--space-4)', borderTop: '1px solid var(--border-soft)' }}>
                <div className="grid grid-3">
                  <Stile label="Total P&L" value={<Pnl value={perf?.total_pnl_dollars} />} />
                  <Stile label="Gross Wins" value={<span className="mono tnum up">{fmtMoneyShort(perf?.gross_win_dollars)}</span>} />
                  <Stile label="Gross Losses" value={<span className="mono tnum down">{fmtMoneyShort(perf?.gross_loss_dollars)}</span>} />
                </div>
              </div>
            </div>
          </div>

          <ErrorBoundary>
            <HoldingPeriodHistogram holding_data={holdingDistribution} />
          </ErrorBoundary>
        </div>
      )}

      {/* Recent trades */}
      {tradesDataError && !hasCachedTrades ? (
        <div className="card card-danger" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-body">
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              <AlertTriangle size={20} style={{ color: 'var(--danger)' }} />
              <div>
                <div style={{ fontWeight: 'var(--w-semibold)' }}>Recent Trades Unavailable</div>
                <div style={{ fontSize: 'var(--t-sm)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>{tradesDataError}</div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="card" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-head">
            <div>
              <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                Recent Trades
                {hasCachedTrades && <CachedDataBadge />}
              </div>
              <div className="card-sub">Last closed positions</div>
            </div>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {isPrimaryLoading ? (
              <SkeletonTable />
            ) : (safeTradesList.length === 0) ? (
              <Empty title="No closed trades yet" />
            ) : (
            <div style={{ maxHeight: '360px', overflow: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th className="num">Entry</th>
                    <th className="num">Exit</th>
                    <th className="num">P&L %</th>
                    <th className="num">R</th>
                    <th className="num">Days</th>
                  </tr>
                </thead>
                <tbody>
                  {safeTradesList.map((t, i) => (
                    <tr key={i}
                        onClick={() => navigate(`/app/stock/${encodeURIComponent(t.symbol)}`)}
                        style={{ cursor: 'pointer' }}>
                      <td>
                        <span className="strong" style={{ fontWeight: 'var(--w-semibold)' }}>{t.symbol}</span>
                      </td>
                      <td className="num mono tnum">{fmtMoney(t.entry_price)}</td>
                      <td className="num mono tnum">{t.exit_price ? fmtMoney(t.exit_price) : '—'}</td>
                      <td className="num"><Pnl value={t.profit_loss_pct} suffix="%" /></td>
                      <td className="num"><Pnl value={t.exit_r_multiple} suffix="R" /></td>
                      <td className="num mono tnum muted">{t.trade_duration_days ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )}
          </div>
        </div>
      )}

      {/* Market context */}
      {marketsDataError ? (
        <div className="card card-danger" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-head">
            <div>
              <div className="card-title">Market Context</div>
              <div className="card-sub">Regime, exposure target, and risk inputs feeding position sizing</div>
            </div>
          </div>
          <div className="card-body">
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              <AlertTriangle size={20} style={{ color: 'var(--danger)' }} />
              <div>
                <div style={{ fontWeight: 'var(--w-semibold)' }}>Market Data Unavailable</div>
                <div style={{ fontSize: 'var(--t-sm)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>{marketsDataError}</div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="card" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-head">
            <div>
              <div className="card-title">Market Context</div>
              <div className="card-sub">Regime, exposure target, and risk inputs feeding position sizing</div>
            </div>
          </div>
          <div className="card-body">
            <div className="grid grid-4">
              <Stile
                label="Exposure Target"
                value={<span className="mono tnum">{markets?.current?.exposure_pct ?? '—'}%</span>}
                sub={(markets?.current?.regime || '').toString().toUpperCase()}
              />
              <Stile
                label="Market Score"
                value={<span className="mono tnum">{markets?.current?.raw_score ?? '—'}/100</span>}
                sub="12-factor composite"
              />
              <Stile
                label="VIX"
                value={<span className="mono tnum">{num(market.vix, 1)}</span>}
                sub={market.vix > 25 ? 'elevated' : market.vix > 15 ? 'normal' : 'low'}
              />
              <Stile
                label="Distribution Days"
                value={<span className={`mono tnum ${market.distribution_days >= 5 ? 'down' : ''}`}>
                  {market.distribution_days ?? 0}
                </span>}
                sub="trailing 4 weeks"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PortfolioDashboard() {
  return (
    <ErrorBoundary>
      <PortfolioDashboardPage />
    </ErrorBoundary>
  );
}

// ─── Circuit breaker panel ──────────────────────────────────────────────────
function CircuitBreakerPanel({ data, loading }) {
  const breakers = Array.isArray(data) ? data : data?.breakers || [];
  const error = data?._error;

  if (loading) {
    return <SkeletonCircuitBreaker />;
  }

  if (error) {
    return (
      <div className="card card-danger" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Circuit Breakers</div>
            <div className="card-sub">Pre-trade kill-switch state</div>
          </div>
        </div>
        <div className="card-body">
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            <AlertTriangle size={20} style={{ color: 'var(--danger)' }} />
            <div>
              <div style={{ fontWeight: 'var(--w-semibold)' }}>Circuit Breaker Data Unavailable</div>
              <div style={{ fontSize: 'var(--t-sm)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>{error}</div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (breakers.length === 0) {
    return (
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Circuit Breakers</div>
            <div className="card-sub">Pre-trade kill-switch state</div>
          </div>
        </div>
        <div className="card-body">
          <Empty title="No circuit breaker data" />
        </div>
      </div>
    );
  }

  const tripped = breakers.filter(b => b.triggered).length;
  const gridCols = breakers.length <= 2 ? 2 : breakers.length === 3 ? 3 : 4;
  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Circuit Breakers</div>
          <div className="card-sub">
            {tripped === 0
              ? 'All clear — no kill-switches triggered'
              : `${tripped} of ${breakers.length} breakers triggered — new entries halted`}
          </div>
        </div>
        <span className={`badge ${tripped === 0 ? 'badge-success' : 'badge-danger'}`}>
          {tripped === 0 ? 'CLEAR' : 'HALTED'}
        </span>
      </div>
      <div className="card-body">
        <div className={`grid grid-${gridCols}`} style={{ gap: 'var(--space-3)' }}>
          {breakers.map(b => {
            const utilPct = b.threshold > 0
              ? Math.min(100, Math.round((Number(b.current) / Number(b.threshold)) * 100))
              : 0;
            const tone = b.triggered ? 'down' : utilPct > 75 ? '' : 'up';
            const color = b.triggered ? 'var(--danger)'
                        : utilPct > 75 ? 'var(--amber)' : 'var(--success)';
            return (
              <div key={b.id} className="card" style={{ padding: 'var(--space-3)' }}>
                <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                  <div className="t-xs muted strong">{b.label}</div>
                  <span className={`badge ${b.triggered ? 'badge-danger' : 'badge-success'}`}
                        style={{ fontSize: 'var(--t-2xs)' }}>
                    {b.triggered ? 'TRIPPED' : 'OK'}
                  </span>
                </div>
                <div className={`mono tnum ${tone}`} style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)' }}>
                  {b.current}{b.unit}
                  <span className="muted t-xs" style={{ marginLeft: 6, fontWeight: 'var(--w-medium)' }}>
                    / {b.threshold}{b.unit}
                  </span>
                </div>
                <div style={{
                  marginTop: 'var(--space-2)',
                  height: 4, background: 'var(--border-soft)',
                  borderRadius: 'var(--r-pill)', overflow: 'hidden',
                }}>
                  <div style={{ height: '100%', width: `${utilPct}%`, background: color, transition: 'width 200ms' }} />
                </div>
                <div className="t-2xs muted" style={{ marginTop: 'var(--space-2)', lineHeight: 1.3 }}>
                  {b.description}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── Equity curve ──────────────────────────────────────────────────────────
function EquityCurve({ series, loading }) {
  const data = useMemo(() => {
    if (!series || series.length === 0) return [];
    return series.map(s => ({
      date: String(s.snapshot_date || '').slice(5, 10),
      value: Number(s.total_portfolio_value || 0),
    })).filter(d => d.value > 0);
  }, [series]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Equity Curve</div>
          <div className="card-sub">Portfolio value · daily snapshots</div>
        </div>
      </div>
      <div className="card-body">
        {loading ? (
          <SkeletonChartContent />
        ) : data.length < 2 ? (
          <Empty title="Equity curve building" desc={`${data.length} snapshot${data.length === 1 ? '' : 's'} — need 2+ for a curve.`} />
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11} tickLine={false} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false}
                       tickFormatter={fmtMoneyShort} width={64} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [fmtMoney(v), 'Value']} />
                <Area type="monotone" dataKey="value" stroke="var(--brand)" strokeWidth={2}
                      fill="url(#equityGrad)" connectNulls={true} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Drawdown chart ────────────────────────────────────────────────────────
function DrawdownChart({ series, loading }) {
  const data = useMemo(() => {
    if (!series || series.length === 0) return [];
    return series
      .map(s => ({
        date: String(s.snapshot_date || '').slice(5, 10),
        dd: Number(s.drawdown_pct || 0),
      }))
      .filter(s => s.dd !== 0 || s.date);
  }, [series]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Drawdown</div>
          <div className="card-sub">% drawdown from peak (lower = deeper)</div>
        </div>
      </div>
      <div className="card-body">
        {loading ? (
          <SkeletonChartContent />
        ) : data.length < 2 ? (
          <Empty title="Drawdown building" desc="Need 2+ snapshots to compute drawdown." />
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--danger)" stopOpacity={0} />
                    <stop offset="100%" stopColor="var(--danger)" stopOpacity={0.5} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11} tickLine={false} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false}
                       tickFormatter={(v) => `${v}%`} width={50} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${v}%`, 'Drawdown']} />
                <ReferenceLine y={0} stroke="var(--border)" />
                <Area type="monotone" dataKey="dd" stroke="var(--danger)" strokeWidth={1.5}
                      fill="url(#ddGrad)" connectNulls={true} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Daily-return histogram (bell-curve overlay style) ─────────────────────
function DailyReturnHistogram({ histogram_data, loading }) {
  const { buckets, stats, isPlaceholder } = useMemo(() => {
    if (!histogram_data) return { buckets: [], stats: null, isPlaceholder: false };
    const data = histogram_data.buckets || [];
    const stat = histogram_data.stats || null;
    const placeholder = histogram_data._is_placeholder === true;
    return { buckets: data, stats: stat, isPlaceholder: placeholder };
  }, [histogram_data]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            Daily Return Distribution
            {isPlaceholder && <span className="badge badge-warning" style={{ fontSize: 'var(--t-2xs)' }}>Placeholder</span>}
          </div>
          <div className="card-sub">
            {isPlaceholder
              ? 'Data building - no trading history yet'
              : stats
              ? `${stats.count} sessions · mean ${stats.mean.toFixed(2)}% · σ ${stats.std.toFixed(2)}%`
              : 'Last 90 days'}
          </div>
        </div>
      </div>
      <div className="card-body">
        {loading ? (
          <div style={{ height: 220 }}>
            <SkeletonChart />
          </div>
        ) : buckets.length === 0 || isPlaceholder ? (
          <Empty title="No daily-return data yet" desc={isPlaceholder ? "Algo is building trading history. Returns will show here after first trades." : undefined} />
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={buckets} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="mid" stroke="var(--text-3)" fontSize={11} tickLine={false}
                       tickFormatter={(v) => `${v}%`} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false} allowDecimals={false} width={32} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v) => [v, 'Sessions']}
                  labelFormatter={(l) => `${l}%`} />
                <ReferenceLine x={0} stroke="var(--border)" strokeDasharray="2 4" />
                <Bar dataKey="count">
                  {buckets.map((b, i) => (
                    <Cell key={i} fill={b.mid >= 0 ? 'var(--success)' : 'var(--danger)'} fillOpacity={0.85} />
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

// ─── Trade outcome distribution ────────────────────────────────────────────
function TradeDistribution({ distribution_data, loading }) {
  const { buckets, isPlaceholder } = useMemo(() => {
    if (!distribution_data) return { buckets: [], isPlaceholder: false };
    const data = distribution_data.buckets || [];
    const placeholder = distribution_data._is_placeholder === true;
    return { buckets: data, isPlaceholder: placeholder };
  }, [distribution_data]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            Trade Outcome Distribution
            {isPlaceholder && <span className="badge badge-warning" style={{ fontSize: 'var(--t-2xs)' }}>Placeholder</span>}
          </div>
          <div className="card-sub">{isPlaceholder ? 'No trades yet' : 'R-multiples across closed trades'}</div>
        </div>
      </div>
      <div className="card-body">
        {loading ? (
          <div style={{ height: 220 }}>
            <SkeletonChart />
          </div>
        ) : buckets.length === 0 || isPlaceholder ? (
          <Empty title="No closed trades yet" desc={isPlaceholder ? "Trade distribution will appear after the first trade closes." : undefined} />
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={buckets} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="range" stroke="var(--text-3)" fontSize={11} tickLine={false} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false} allowDecimals={false} width={32} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="count">
                  {buckets.map((b, i) => (
                    <Cell key={i}
                      fill={b.min >= 0 ? 'var(--success)' : 'var(--danger)'} fillOpacity={0.85} />
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

// ─── Holding period histogram ──────────────────────────────────────────────
function HoldingPeriodHistogram({ holding_data }) {
  const { buckets, isPlaceholder } = useMemo(() => {
    if (!holding_data) return { buckets: [], isPlaceholder: false };
    const data = holding_data.buckets || [];
    const placeholder = holding_data._is_placeholder === true;
    return { buckets: data, isPlaceholder: placeholder };
  }, [holding_data]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            Holding Period Distribution
            {isPlaceholder && <span className="badge badge-warning" style={{ fontSize: 'var(--t-2xs)' }}>Placeholder</span>}
          </div>
          <div className="card-sub">{isPlaceholder ? 'No trades yet' : 'Days held per closed trade'}</div>
        </div>
      </div>
      <div className="card-body">
        {buckets.length === 0 || isPlaceholder ? (
          <Empty title="No closed trades yet" desc={isPlaceholder ? "Holding period distribution will appear after trades close." : undefined} />
        ) : (
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={buckets} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="range" stroke="var(--text-3)" fontSize={11} tickLine={false} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false} allowDecimals={false} width={32} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="count" fill="var(--cyan)" fillOpacity={0.85} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── R-multiple ladder per position ────────────────────────────────────────
function RLadderPanel({ positions, loading, onSelect }) {
  const posArray = Array.isArray(positions) ? positions : (positions?.items || []);
  const ladders = useMemo(() => {
    if (!posArray) return [];
    return posArray
      .filter(p => p.ladder_pct_stop != null && p.ladder_pct_entry != null && p.ladder_pct_current != null)
      .map(p => ({
        symbol: p.symbol,
        r_multiple: p.r_multiple,
        entry: p.avg_entry_price,
        cur: p.current_price,
        stop: p.stop_loss_price,
        t1: p.target_1_price,
        t2: p.target_2_price,
        t3: p.target_3_price,
        unrealized_pnl_pct: p.unrealized_pnl_pct,
        pStop: p.ladder_pct_stop,
        pEntry: p.ladder_pct_entry,
        pCur: p.ladder_pct_current,
        pT1: p.ladder_pct_t1,
        pT2: p.ladder_pct_t2,
        pT3: p.ladder_pct_t3,
      }));
  }, [posArray]);

  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">R-Multiple Ladder</div>
          <div className="card-sub">Stop · entry · current · T1/T2/T3 per open position</div>
        </div>
      </div>
      <div className="card-body">
        {loading ? (
          <SkeletonTable />
        ) : ladders.length === 0 ? (
          <Empty title="No open positions with stop/target levels"
                 desc="Stops & targets are populated by the orchestrator at entry time." />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {ladders.map((l, i) => (
              <div key={i} onClick={() => onSelect(l.symbol)}
                   style={{ cursor: 'pointer' }}>
                <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                  <div className="flex items-center" style={{ gap: 'var(--space-3)' }}>
                    <span className="strong" style={{ fontWeight: 'var(--w-bold)', fontSize: 'var(--t-md)' }}>
                      {l.symbol}
                    </span>
                    <RChip r={l.r_multiple} />
                    <Pnl value={l.unrealized_pnl_pct} suffix="%" />
                  </div>
                  <div className="t-xs muted mono tnum">
                    Stop {fmtMoney(l.stop)} · Entry {fmtMoney(l.entry)} · Now {fmtMoney(l.cur)}
                  </div>
                </div>
                <div style={LADDER_TRACK_STYLE}>
                  {/* Filled track from stop to current (or stop to entry if underwater) */}
                  <div style={LADDER_FILL_STYLE(l.pStop, l.pCur, l.pEntry)} />
                  <Marker pct={l.pStop} color="var(--danger)" label="S" />
                  <Marker pct={l.pEntry} color="var(--text-2)" label="E" />
                  {l.pT1 != null && <Marker pct={l.pT1} color="var(--cyan)" label="T1" />}
                  {l.pT2 != null && <Marker pct={l.pT2} color="var(--purple)" label="T2" />}
                  {l.pT3 != null && <Marker pct={l.pT3} color="var(--success)" label="T3" />}
                  <Marker pct={l.pCur} color="var(--brand)" label="◆" big />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Marker({ pct, color, label, big = false }) {
  return (
    <div style={{...MARKER_STYLE_BASE, left: `${pct}%`, transform: 'translateX(-50%)'}}>
      <div style={MARKER_LINE_STYLE(big, color)} />
      <div className="mono tnum" style={MARKER_LABEL_STYLE(color)}>{label}</div>
    </div>
  );
}

function RChip({ r }) {
  if (r == null) return <span className="badge" style={{ fontSize: 'var(--t-2xs)' }}>—</span>;
  const cls = r >= 1 ? 'badge-success' : r >= 0 ? 'badge-cyan' : r >= -0.5 ? 'badge-amber' : 'badge-danger';
  const sign = r > 0 ? '+' : '';
  return (
    <span className={`badge ${cls} mono tnum`} style={{ fontSize: 'var(--t-2xs)' }}>
      {sign}{r.toFixed(2)}R
    </span>
  );
}

// ─── Risk allocation pie ───────────────────────────────────────────────────
function RiskAllocationPie({ positions, totalValue, loading, onSelect }) {
  const posArray = Array.isArray(positions) ? positions : (positions?.items || []);
  const data = useMemo(() => {
    if (!posArray) return [];
    return posArray
      .filter(p => (p.open_risk_dollars || 0) > 0)
      .map(p => ({
        symbol: p.symbol,
        risk: Number(p.open_risk_dollars) || 0,
        risk_pct: Number(p.risk_pct) || 0,
      }))
      .sort((a, b) => b.risk - a.risk);
  }, [posArray]);
  // Risk percentage is pre-computed per-position; aggregate using backend-computed total
  const totalRisk = data.reduce((s, d) => s + d.risk, 0);
  const riskPct = data.length > 0 ? data.reduce((s, d) => s + d.risk_pct, 0) : 0;

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Open Risk Allocation</div>
          <div className="card-sub">
            {data.length === 0 ? 'No positions with stops'
              : `${fmtMoneyShort(totalRisk)} at risk · ${riskPct.toFixed(2)}% of portfolio`}
          </div>
        </div>
      </div>
      <div className="card-body">
        {loading ? (
          <SkeletonChartContent />
        ) : data.length === 0 ? (
          <Empty title="No risk data" desc="Positions need stop levels." />
        ) : (
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data} dataKey="risk" nameKey="symbol"
                     cx="50%" cy="50%" innerRadius={50} outerRadius={90}
                     onClick={(d) => d?.symbol && onSelect(d.symbol)}
                     paddingAngle={2}>
                  {data.map((_, i) => (
                    <Cell key={i} fill={PIE_PALETTE[i % PIE_PALETTE.length]}
                          style={{ cursor: 'pointer' }} />
                  ))}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v, n) => [fmtMoney(v), n]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Sector concentration bar chart ────────────────────────────────────────
function SectorConcentration({ sector_allocation, loading }) {
  const data = sector_allocation || [];
  const overweight = data.find(d => d.allocation_pct > 30);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Sector Concentration</div>
          <div className="card-sub">
            {overweight ? `Heavy in ${overweight.sector} (${overweight.pct.toFixed(1)}%)`
                        : 'Diversified across sectors'}
          </div>
        </div>
      </div>
      <div className="card-body">
        {loading ? (
          <SkeletonChartContent />
        ) : data.length === 0 ? (
          <Empty title="No sector data" />
        ) : (
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical"
                        margin={{ top: 4, right: 16, left: 4, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis type="number" stroke="var(--text-3)" fontSize={11}
                       tickFormatter={(v) => `${Number(v).toFixed(0)}%`} />
                <YAxis type="category" dataKey="sector" stroke="var(--text-3)"
                       fontSize={11} width={110} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v) => [`${v.toFixed(1)}%`, 'Allocation']} />
                <Bar dataKey="allocation_pct" radius={[0, 4, 4, 0]}>
                  {data.map((d, i) => (
                    <Cell key={i} fill={d.allocation_pct > 30 ? 'var(--danger)' : 'var(--brand)'} />
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

// ─── Stage phase donut ─────────────────────────────────────────────────────
function StagePhaseDonut({ distribution, loading }) {
  const data = useMemo(() => {
    if (!distribution || !distribution.distribution) return [];
    return distribution.distribution || [];
  }, [distribution]);

  const colorFor = (p) => {
    if (p.startsWith('Early')) return 'var(--success)';
    if (p.startsWith('Mid')) return 'var(--cyan)';
    if (p.startsWith('Late')) return 'var(--amber)';
    if (p.startsWith('Stage 1')) return 'var(--brand)';
    if (p.startsWith('Stage 3')) return 'var(--purple)';
    if (p.startsWith('Stage 4')) return 'var(--danger)';
    return 'var(--text-3)';
  };

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Stage Phase Distribution</div>
          <div className="card-sub">Where holdings sit in the market stage cycle</div>
        </div>
      </div>
      <div className="card-body">
        {loading ? (
          <SkeletonChartContent />
        ) : data.length === 0 ? (
          <Empty title="No stage data" desc="Positions need trend_template_data coverage." />
        ) : (
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data} dataKey="count" nameKey="phase"
                     cx="50%" cy="50%" innerRadius={50} outerRadius={90} paddingAngle={2}>
                  {data.map((d, i) => (
                    <Cell key={i} fill={colorFor(d.phase)} />
                  ))}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Position health table ─────────────────────────────────────────────────
function PositionHealthTable({ positions, loading, onSelect }) {
  const posArray = Array.isArray(positions) ? positions : (positions?.items || []);
  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Position Health ({posArray.length || 0})</div>
          <div className="card-sub">Days held · R · stop/target distance · trend posture · sector</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {loading ? (
          <SkeletonTable />
        ) : !posArray || posArray.length === 0 ? (
          <Empty title="No open positions" />
        ) : (
          <div style={{ overflow: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Sector</th>
                  <th className="num">Days</th>
                  <th className="num">R</th>
                  <th className="num">P&L %</th>
                  <th className="num">→ Stop</th>
                  <th className="num">→ T1</th>
                  <th className="num">→ T2</th>
                  <th className="num">→ T3</th>
                  <th>Stage</th>
                  <th className="num">Trend</th>
                  <th className="num">% from low</th>
                  <th>Exit Plan</th>
                </tr>
              </thead>
              <tbody>
                {posArray.map((p, i) => (
                  <tr key={i}
                      onClick={() => onSelect(p.symbol)}
                      style={{ cursor: 'pointer' }}>
                    <td><span className="strong" style={{ fontWeight: 'var(--w-bold)' }}>{p.symbol}</span></td>
                    <td className="t-xs muted">{p.sector || '—'}</td>
                    <td className="num mono tnum muted">{p.days_since_entry ?? '—'}</td>
                    <td className="num"><RChip r={p.r_multiple} /></td>
                    <td className="num"><Pnl value={p.unrealized_pnl_pct} suffix="%" /></td>
                    <td className="num mono tnum down">
                      {p.distance_to_stop_pct != null ? `-${num(p.distance_to_stop_pct, 1)}%` : '—'}
                    </td>
                    <td className="num mono tnum">
                      {p.distance_to_t1_pct != null ? `+${num(p.distance_to_t1_pct, 1)}%` : '—'}
                    </td>
                    <td className="num mono tnum">
                      {p.distance_to_t2_pct != null ? `+${num(p.distance_to_t2_pct, 1)}%` : '—'}
                    </td>
                    <td className="num mono tnum">
                      {p.distance_to_t3_pct != null ? `+${num(p.distance_to_t3_pct, 1)}%` : '—'}
                    </td>
                    <td>
                      {p.weinstein_stage != null
                        ? <span className="badge mono">S{p.weinstein_stage}</span>
                        : <span className="muted">—</span>}
                    </td>
                    <td className="num mono tnum">
                      {p.minervini_trend_score != null ? `${p.minervini_trend_score}/8` : '—'}
                    </td>
                    <td className="num mono tnum">
                      {p.pct_from_52w_low != null ? `+${num(p.pct_from_52w_low, 0)}%` : '—'}
                    </td>
                    <td>
                      <span className="badge" style={{ textTransform: 'uppercase', fontSize: 'var(--t-2xs)' }}>
                        {(p.stage_in_exit_plan || 'init').toString()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── shared little components ──────────────────────────────────────────────
function Kpi({ label, value, sub, icon: Icon, tone }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="flex items-center justify-between">
        <div className="eyebrow">{label}</div>
        {Icon && <Icon size={16} className="muted" />}
      </div>
      <div className={`mono ${tone || ''}`}
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

function StreakValue({ v }) {
  if (v == null || v === 0) return <span className="mono muted">0</span>;
  const cls = v > 0 ? 'up' : 'down';
  return <span className={`mono tnum ${cls}`}>{v > 0 ? `${v}W` : `${Math.abs(v)}L`}</span>;
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

// PropTypes for chart components
CircuitBreakerPanel.propTypes = {
  data: PropTypes.oneOfType([PropTypes.array, PropTypes.object]),
  loading: PropTypes.bool,
};

EquityCurve.propTypes = {
  series: PropTypes.array,
  loading: PropTypes.bool,
};

DrawdownChart.propTypes = {
  series: PropTypes.array,
  loading: PropTypes.bool,
};

DailyReturnHistogram.propTypes = {
  series: PropTypes.array,
  loading: PropTypes.bool,
};

TradeDistribution.propTypes = {
  trades: PropTypes.array,
  loading: PropTypes.bool,
};

HoldingPeriodHistogram.propTypes = {
  trades: PropTypes.array,
};

RLadderPanel.propTypes = {
  positions: PropTypes.array,
  loading: PropTypes.bool,
  onSelect: PropTypes.func,
};

RiskAllocationPie.propTypes = {
  positions: PropTypes.array,
  totalValue: PropTypes.number,
  loading: PropTypes.bool,
  onSelect: PropTypes.func,
};

SectorConcentration.propTypes = {
  positions: PropTypes.array,
  totalValue: PropTypes.number,
  loading: PropTypes.bool,
};

StagePhaseDonut.propTypes = {
  distribution: PropTypes.object,
  loading: PropTypes.bool,
};

PositionHealthTable.propTypes = {
  positions: PropTypes.array,
  loading: PropTypes.bool,
  onSelect: PropTypes.func,
};

