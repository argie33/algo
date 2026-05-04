/**
 * Trading Signals — STOCKS + ETFs unified page.
 * Pure JSX + theme.css classes.
 */

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Search, RefreshCw, Inbox, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '../services/api';

const fmtMoney = (v) => v == null ? '—' : `$${Number(v).toFixed(2)}`;
const fmtPct = (v) => v == null ? '—' : `${Number(v).toFixed(2)}%`;
const fmtInt = (v) => v == null ? '—' : Number(v).toLocaleString('en-US');
const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);

const STAGE_VARIANT = {
  'Stage 1': 'badge', 'Stage 2': 'badge-success', 'Stage 2 - Markup': 'badge-success',
  'Stage 3': 'badge-amber', 'Stage 3 - Topping': 'badge-amber', 'Stage 4': 'badge-danger',
};
const QUALITY_VARIANT = { STRONG: 'badge-success', MODERATE: 'badge-amber', WEAK: 'badge-danger' };

export default function TradingSignals() {
  const [tab, setTab] = useState('stocks');
  const [signal, setSignal] = useState('all');
  const [timeframe, setTimeframe] = useState('daily');
  const [search, setSearch] = useState('');
  const [stageFilter, setStageFilter] = useState('all');
  const [expandedKey, setExpandedKey] = useState(null);

  const endpoint = tab === 'etfs' ? '/api/signals/etf' : '/api/signals/stocks';

  const { data, isLoading, refetch } = useQuery({
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

  const rows = data?.items || data?.data || [];
  const filtered = useMemo(() => {
    let r = rows;
    if (search) {
      const q = search.trim().toUpperCase();
      r = r.filter(x => x.symbol?.startsWith(q));
    }
    if (stageFilter !== 'all') r = r.filter(x => (x.market_stage || '').includes(stageFilter));
    return r;
  }, [rows, search, stageFilter]);

  const buyCount = filtered.filter(r => (r.signal || '').toUpperCase() === 'BUY').length;
  const sellCount = filtered.filter(r => (r.signal || '').toUpperCase() === 'SELL').length;

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
          <button className="btn btn-outline btn-sm" onClick={() => refetch()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

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

      <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="kpi"><div className="kpi-label">Total Signals</div><div className="kpi-value">{filtered.length}</div></div>
        <div className="kpi"><div className="kpi-label">BUY</div><div className="kpi-value up">{buyCount}</div></div>
        <div className="kpi"><div className="kpi-label">SELL</div><div className="kpi-value down">{sellCount}</div></div>
        <div className="kpi">
          <div className="kpi-label">BUY/SELL Ratio</div>
          <div className="kpi-value">{sellCount === 0 ? '∞' : (buyCount / sellCount).toFixed(2)}</div>
          <div className="kpi-sub">{buyCount > sellCount ? 'risk on' : buyCount < sellCount ? 'risk off' : 'even'}</div>
        </div>
      </div>

      <div className="card card-pad-sm" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="flex gap-3" style={{ flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-faint)' }} />
            <input className="input" placeholder="Symbol (starts with)" value={search}
              onChange={e => setSearch(e.target.value)} style={{ paddingLeft: 32 }} />
          </div>
          <select className="select" value={signal} onChange={e => setSignal(e.target.value)} style={{ width: 140 }}>
            <option value="all">All signals</option>
            <option value="BUY">BUY only</option>
            <option value="SELL">SELL only</option>
          </select>
          <select className="select" value={timeframe} onChange={e => setTimeframe(e.target.value)} style={{ width: 130 }}>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
          <select className="select" value={stageFilter} onChange={e => setStageFilter(e.target.value)} style={{ width: 180 }}>
            <option value="all">All stages</option>
            <option value="Stage 1">Stage 1 (Basing)</option>
            <option value="Stage 2">Stage 2 (Markup)</option>
            <option value="Stage 3">Stage 3 (Topping)</option>
            <option value="Stage 4">Stage 4 (Decline)</option>
          </select>
        </div>
      </div>

      <SignalsTable rows={filtered} loading={isLoading} kind={tab}
        expandedKey={expandedKey} setExpandedKey={setExpandedKey} />
    </div>
  );
}

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
              <th className="num">RSI</th>
              <th className="num">Vol Surge</th>
              <th>Base</th>
              <th>Quality</th>
              <th>Stage</th>
              <th className="num">Date</th>
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
                    <td className="muted t-xs">{r.base_type ? `${r.base_type} (${r.base_length_days || '?'}d)` : '—'}</td>
                    <td>
                      {r.breakout_quality
                        ? <span className={`badge ${QUALITY_VARIANT[r.breakout_quality] || 'badge'}`}>{r.breakout_quality}</span>
                        : <span className="muted">—</span>}
                    </td>
                    <td>
                      {r.market_stage
                        ? <span className={`badge ${STAGE_VARIANT[r.market_stage] || 'badge'}`}>{r.market_stage.replace('Stage ', 'S')}</span>
                        : <span className="muted">—</span>}
                    </td>
                    <td className="num muted t-xs">{r.signal_triggered_date || r.date ? String(r.signal_triggered_date || r.date).slice(0, 10) : '—'}</td>
                  </tr>
                  {expanded && (
                    <tr>
                      <td colSpan={12} style={{ background: 'var(--bg-2)', padding: 'var(--space-4)' }}>
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

function SignalDetail({ row, kind, onSymbolClick }) {
  return (
    <div>
      {kind === 'stocks' && (
        <button className="btn btn-outline btn-sm" onClick={onSymbolClick} style={{ marginBottom: 'var(--space-3)' }}>
          Open {row.symbol} detail →
        </button>
      )}
      <div className="grid grid-3 gap-4">
        <DetailGroup title="Entry plan" items={[
          ['Buy zone', `${fmtMoney(row.buy_zone_start)} – ${fmtMoney(row.buy_zone_end)}`],
          ['Pivot', fmtMoney(row.pivot_price)],
          ['Initial stop', fmtMoney(row.initial_stop)],
          ['Trailing stop', fmtMoney(row.trailing_stop)],
          ['Position size', row.position_size_recommendation || '—'],
          ['Entry quality', row.entry_quality_score ? `${row.entry_quality_score}/100` : '—'],
        ]} />
        <DetailGroup title="Targets & exits" items={[
          ['Target +8%', fmtMoney(row.profit_target_8pct)],
          ['Target +20%', fmtMoney(row.profit_target_20pct)],
          ['Target +25%', fmtMoney(row.profit_target_25pct)],
          ['Exit T1', fmtMoney(row.exit_trigger_1_price)],
          ['Exit T2', fmtMoney(row.exit_trigger_2_price)],
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
          ['Volume', fmtInt(row.volume)],
          ['Avg vol 50d', fmtInt(row.avg_volume_50d)],
          ['Vol surge', row.volume_surge_pct != null ? fmtPct(row.volume_surge_pct) : '—'],
        ]} />
      </div>
    </div>
  );
}

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

function Empty({ title, desc }) {
  return (
    <div className="card">
      <div className="empty">
        <Inbox />
        <div className="empty-title">{title}</div>
        {desc && <div className="empty-desc">{desc}</div>}
      </div>
    </div>
  );
}
