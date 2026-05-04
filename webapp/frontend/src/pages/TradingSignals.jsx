/**
 * Trading Signals — STOCKS + ETFs unified page.
 *
 * Tabs at top: STOCKS | ETFs (both share buy_sell_daily / buy_sell_daily_etf
 * schemas — same columns, same filters, same row-expansion). Different
 * data source per tab.
 *
 * Per DESIGN_REDESIGN_PLAN.md §4 Page E: every column from buy_sell_daily is
 * available; default visible columns are the most algo-relevant ones, with
 * row-expansion revealing the full record.
 *
 * Tailwind + Primitives. No MUI imports.
 */

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Search, RefreshCw, Zap } from 'lucide-react';
import { api } from '../services/api';
import {
  Card, PageHeader, Stat, Chip, Button, Input, Select, Tabs,
  PnlCell, DataTable, cx,
} from '../components/ui/Primitives';

// =============================================================================
// HELPERS
// =============================================================================

const fmtMoney = (v) => v == null ? '—' : `$${Number(v).toFixed(2)}`;
const fmtPct = (v) => v == null ? '—' : `${Number(v).toFixed(2)}%`;
const fmtInt = (v) => v == null ? '—' : Number(v).toLocaleString('en-US');

const STAGE_VARIANT = {
  'Stage 1': 'muted',
  'Stage 2': 'bull',
  'Stage 2 - Markup': 'bull',
  'Stage 3': 'warn',
  'Stage 3 - Topping': 'warn',
  'Stage 4': 'bear',
};

const QUALITY_VARIANT = {
  STRONG: 'bull',
  MODERATE: 'warn',
  WEAK: 'bear',
};

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function TradingSignals() {
  const [tab, setTab] = useState('stocks');
  const [signal, setSignal] = useState('all');
  const [timeframe, setTimeframe] = useState('daily');
  const [search, setSearch] = useState('');
  const [stageFilter, setStageFilter] = useState('all');

  const endpoint = tab === 'etfs' ? '/signals/etf' : '/signals/stocks';

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['signals', tab, signal, timeframe],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set('timeframe', timeframe);
      params.set('limit', '500');
      if (signal !== 'all') params.set('signal', signal);
      return api.get(`/api${endpoint}?${params.toString()}`).then(r => r.data);
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
    if (stageFilter !== 'all') {
      r = r.filter(x => (x.market_stage || '').includes(stageFilter));
    }
    return r;
  }, [rows, search, stageFilter]);

  const buyCount = filtered.filter(r => (r.signal || '').toUpperCase() === 'BUY').length;
  const sellCount = filtered.filter(r => (r.signal || '').toUpperCase() === 'SELL').length;

  return (
    <div className="px-4 sm:px-6 py-6 max-w-page mx-auto">
      <PageHeader
        title="Trading Signals"
        subtitle={
          tab === 'stocks'
            ? 'Pine-script signals for stocks · click a row for full detail'
            : 'Pine-script signals for ETFs · click a row for full detail'
        }
        actions={
          <Button variant="ghost" size="sm" icon={RefreshCw} onClick={() => refetch()}>
            Refresh
          </Button>
        }
      />

      <Tabs
        tabs={[
          { value: 'stocks', label: 'Stocks', count: tab === 'stocks' ? rows.length : null },
          { value: 'etfs',   label: 'ETFs',   count: tab === 'etfs'   ? rows.length : null },
        ]}
        value={tab}
        onChange={setTab}
        className="mb-4"
      />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <Card padded className="mb-0">
          <Stat label="Total Signals" value={filtered.length} mono size="lg" />
        </Card>
        <Card padded className="mb-0">
          <Stat label="BUY" value={buyCount} color="#1F9956" mono size="lg" />
        </Card>
        <Card padded className="mb-0">
          <Stat label="SELL" value={sellCount} color="#E0392B" mono size="lg" />
        </Card>
        <Card padded className="mb-0">
          <Stat
            label="BUY/SELL Ratio"
            value={sellCount === 0 ? '∞' : (buyCount / sellCount).toFixed(2)}
            sub={buyCount > sellCount ? 'risk on' : buyCount < sellCount ? 'risk off' : 'even'}
            mono size="lg"
          />
        </Card>
      </div>

      <Card padded className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-[200px] relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint pointer-events-none" />
            <Input
              placeholder="Symbol (starts with)"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>
          <Select value={signal} onChange={e => setSignal(e.target.value)} className="w-32">
            <option value="all">All signals</option>
            <option value="BUY">BUY only</option>
            <option value="SELL">SELL only</option>
          </Select>
          <Select value={timeframe} onChange={e => setTimeframe(e.target.value)} className="w-32">
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </Select>
          <Select value={stageFilter} onChange={e => setStageFilter(e.target.value)} className="w-40">
            <option value="all">All stages</option>
            <option value="Stage 1">Stage 1 (Basing)</option>
            <option value="Stage 2">Stage 2 (Markup)</option>
            <option value="Stage 3">Stage 3 (Topping)</option>
            <option value="Stage 4">Stage 4 (Decline)</option>
          </Select>
        </div>
      </Card>

      <SignalsTable rows={filtered} loading={isLoading} error={error} retry={refetch} kind={tab} />
    </div>
  );
}

// =============================================================================
// TABLE
// =============================================================================

function SignalsTable({ rows, loading, error, retry, kind }) {
  const navigate = useNavigate();

  const columns = useMemo(() => [
    {
      key: 'symbol',
      header: 'Symbol',
      width: '110px',
      render: (r) => (
        <div className="flex items-center gap-2">
          <span className="font-bold text-ink-strong">{r.symbol}</span>
          {r.signal && (
            <Chip variant={r.signal.toUpperCase() === 'BUY' ? 'bull' : 'bear'}>
              {r.signal.toUpperCase()}
            </Chip>
          )}
        </div>
      ),
    },
    {
      key: 'sector',
      header: 'Sector',
      render: (r) => <span className="text-xs text-ink-muted truncate">{r.sector || '—'}</span>,
    },
    {
      key: 'close',
      header: 'Close',
      align: 'right',
      mono: true,
      sortable: true,
      render: (r) => fmtMoney(r.close),
    },
    {
      key: 'buylevel',
      header: 'Buy Level',
      align: 'right',
      mono: true,
      sortable: true,
      render: (r) => (
        <span className={cx(r.close >= r.buylevel ? 'text-bull' : 'text-ink-muted')}>
          {fmtMoney(r.buylevel)}
        </span>
      ),
    },
    {
      key: 'stoplevel',
      header: 'Stop',
      align: 'right',
      mono: true,
      sortable: true,
      render: (r) => fmtMoney(r.stoplevel),
    },
    {
      key: 'risk_reward_ratio',
      header: 'R/R',
      align: 'right',
      mono: true,
      sortable: true,
      render: (r) => r.risk_reward_ratio == null ? '—' : Number(r.risk_reward_ratio).toFixed(2),
    },
    {
      key: 'rsi',
      header: 'RSI',
      align: 'right',
      mono: true,
      sortable: true,
      render: (r) => {
        if (r.rsi == null) return <span className="text-ink-faint">—</span>;
        const rsi = Number(r.rsi);
        const color = rsi > 70 ? 'text-bear' : rsi < 30 ? 'text-bull' : 'text-ink';
        return <span className={color}>{rsi.toFixed(1)}</span>;
      },
    },
    {
      key: 'volume_surge_pct',
      header: 'Vol Surge',
      align: 'right',
      mono: true,
      sortable: true,
      render: (r) => {
        if (r.volume_surge_pct == null) return '—';
        return <PnlCell value={Number(r.volume_surge_pct)} format="percent" inline />;
      },
    },
    {
      key: 'base_type',
      header: 'Base',
      render: (r) => (
        <span className="text-xs text-ink-muted">
          {r.base_type ? `${r.base_type} (${r.base_length_days || '?'}d)` : '—'}
        </span>
      ),
    },
    {
      key: 'breakout_quality',
      header: 'Quality',
      render: (r) => r.breakout_quality
        ? <Chip variant={QUALITY_VARIANT[r.breakout_quality] || 'muted'}>{r.breakout_quality}</Chip>
        : <span className="text-ink-faint">—</span>,
    },
    {
      key: 'market_stage',
      header: 'Stage',
      render: (r) => r.market_stage
        ? <Chip variant={STAGE_VARIANT[r.market_stage] || 'muted'}>{r.market_stage.replace('Stage ', 'S')}</Chip>
        : <span className="text-ink-faint">—</span>,
    },
    {
      key: 'date',
      header: 'Date',
      mono: true,
      sortable: true,
      render: (r) => {
        const d = r.signal_triggered_date || r.date;
        return <span className="text-xs text-ink-muted">{d ? String(d).slice(0, 10) : '—'}</span>;
      },
    },
  ], []);

  return (
    <DataTable
      columns={columns}
      rows={rows}
      keyField="symbol"
      loading={loading}
      error={error}
      maxHeight="70vh"
      empty={{
        icon: Zap,
        title: 'No active signals',
        description: kind === 'etfs'
          ? 'No ETF signals match the current filters.'
          : 'No stock signals match the current filters. Try widening filters or check buy_sell_daily freshness.',
      }}
      onRowClick={(row) => {
        if (kind === 'stocks' && row.symbol) {
          navigate(`/app/stock/${row.symbol}`);
        }
      }}
      expandRender={(row) => <SignalDetail row={row} />}
    />
  );
}

// =============================================================================
// ROW EXPANSION
// =============================================================================

function SignalDetail({ row }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <DetailGroup
        title="Entry Plan"
        items={[
          ['Buy zone', `${fmtMoney(row.buy_zone_start)} – ${fmtMoney(row.buy_zone_end)}`],
          ['Pivot', fmtMoney(row.pivot_price)],
          ['Initial stop', fmtMoney(row.initial_stop)],
          ['Trailing stop', fmtMoney(row.trailing_stop)],
          ['Position size rec', row.position_size_recommendation || '—'],
          ['Entry quality', row.entry_quality_score ? `${row.entry_quality_score}/100` : '—'],
        ]}
      />
      <DetailGroup
        title="Targets & Exits"
        items={[
          ['Target +8%', fmtMoney(row.profit_target_8pct)],
          ['Target +20%', fmtMoney(row.profit_target_20pct)],
          ['Target +25%', fmtMoney(row.profit_target_25pct)],
          ['Exit T1', `${fmtMoney(row.exit_trigger_1_price)}${row.exit_trigger_1_condition ? ' (' + row.exit_trigger_1_condition + ')' : ''}`],
          ['Exit T2', `${fmtMoney(row.exit_trigger_2_price)}${row.exit_trigger_2_condition ? ' (' + row.exit_trigger_2_condition + ')' : ''}`],
          ['Exit T3', `${fmtMoney(row.exit_trigger_3_price)}${row.exit_trigger_3_condition ? ' (' + row.exit_trigger_3_condition + ')' : ''}`],
          ['Exit T4', `${fmtMoney(row.exit_trigger_4_price)}${row.exit_trigger_4_condition ? ' (' + row.exit_trigger_4_condition + ')' : ''}`],
          ['Sell level', fmtMoney(row.sell_level)],
        ]}
      />
      <DetailGroup
        title="Technicals & Strength"
        items={[
          ['RSI (14)', row.rsi != null ? Number(row.rsi).toFixed(1) : '—'],
          ['ADX', row.adx != null ? Number(row.adx).toFixed(1) : '—'],
          ['ATR', row.atr != null ? Number(row.atr).toFixed(2) : '—'],
          ['SMA 50', fmtMoney(row.sma_50)],
          ['SMA 200', fmtMoney(row.sma_200)],
          ['EMA 21', fmtMoney(row.ema_21)],
          ['Pct from EMA21', row.pct_from_ema21 != null ? fmtPct(row.pct_from_ema21) : '—'],
          ['Pct from SMA50', row.pct_from_sma50 != null ? fmtPct(row.pct_from_sma50) : '—'],
          ['RS Rating', row.rs_rating != null ? Number(row.rs_rating).toFixed(0) : '—'],
          ['Mansfield RS', row.mansfield_rs != null ? Number(row.mansfield_rs).toFixed(2) : '—'],
          ['Volume', fmtInt(row.volume)],
          ['Avg vol 50d', fmtInt(row.avg_volume_50d)],
          ['Volume surge', row.volume_surge_pct != null ? fmtPct(row.volume_surge_pct) : '—'],
        ]}
      />
    </div>
  );
}

function DetailGroup({ title, items }) {
  return (
    <div>
      <div className="text-2xs uppercase font-semibold text-ink-muted tracking-wider mb-2">
        {title}
      </div>
      <div className="space-y-1">
        {items.map(([label, value], i) => (
          <div key={i} className="flex items-baseline justify-between gap-2 text-xs">
            <span className="text-ink-muted shrink-0">{label}</span>
            <span className="text-ink font-mono tnum text-right truncate">{value || '—'}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
