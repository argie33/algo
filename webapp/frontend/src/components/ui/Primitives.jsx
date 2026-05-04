/**
 * Primitives — Tailwind component library for the rebuild.
 *
 * Per DESIGN_REDESIGN_PLAN.md and the giggly-meandering-shannon plan file.
 * Plain React + Tailwind classes. No MUI imports. Authored to be easily ported
 * to Tamagui later for the iOS/Android app (cross-platform mobile stack).
 *
 * All visual tokens come from tailwind.config.js → Bullseye design system.
 *
 * Components exported from this file:
 *   - <Card>          surface for any data section
 *   - <PageHeader>    page-level header strip (title / subtitle / actions)
 *   - <Stat>          single metric: label + big value + optional delta + sub
 *   - <PnlCell>       money or percent with semantic color, tabular figures
 *   - <Chip>          status / metadata badge
 *   - <GradeChip>     A+/A/B/C/D/E/F letter grade
 *   - <Button>        primary / secondary / ghost / danger
 *   - <Input>         single-line text input with consistent height
 *   - <Select>        select with consistent height
 *   - <Tabs>          tab strip with brand-colored active indicator
 *   - <DataTable>     sortable, sticky-header, expandable rows
 *   - <Skeleton>      layout-preserving loader
 *   - <EmptyState>    "no data" panel with icon + message + CTA
 *   - <ErrorState>    error panel with retry
 *   - <StatusDot>     live / stale / error indicator
 *   - <FactorBar>     score breakdown bar with label + value + max
 *   - <Sparkline>     mini inline trend
 *   - <SectionDivider>  thin titled separator
 */

import React, { useState } from 'react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';
import {
  ChevronDown,
  ChevronUp,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Minus,
  AlertCircle,
  RefreshCw,
  Inbox,
} from 'lucide-react';

// =============================================================================
// HELPERS
// =============================================================================

export const cx = (...args) => twMerge(clsx(...args));

export const fmtAgo = (ts) => {
  if (!ts) return '—';
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

export const fmtMoney = (v, dp = 2) =>
  v == null ? '—' :
  `$${Number(v).toLocaleString('en-US', { maximumFractionDigits: dp, minimumFractionDigits: dp })}`;

export const fmtPct = (v, dp = 2) =>
  v == null ? '—' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(dp)}%`;

export const fmtNum = (v, dp = 2) =>
  v == null ? '—' : Number(v).toFixed(dp);

// =============================================================================
// CARD
// =============================================================================

export function Card({
  title, subtitle, action, freshness, source,
  loading, error, empty,
  children, className, padded = true,
}) {
  return (
    <section className={cx('card', padded && 'p-4', 'mb-4', className)}>
      {(title || action) && (
        <header className="flex items-center justify-between mb-3 gap-3">
          <div className="min-w-0 flex-1">
            {title && (
              <h3 className="section-title truncate">{title}</h3>
            )}
            {subtitle && (
              <p className="section-subtitle">{subtitle}</p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {freshness && (
              <span className="text-xs font-mono tnum text-ink-faint">
                {freshness}
              </span>
            )}
            {source && (
              <span className="chip-muted">{source}</span>
            )}
            {action}
          </div>
        </header>
      )}
      {loading ? <Skeleton height={120} /> :
       error ? <ErrorState error={error} /> :
       empty ? <EmptyState {...empty} /> :
       children}
    </section>
  );
}

// =============================================================================
// PAGE HEADER
// =============================================================================

export function PageHeader({ title, subtitle, actions, breadcrumb }) {
  return (
    <div className="page-header">
      <div className="min-w-0">
        {breadcrumb && (
          <div className="text-xs text-ink-muted mb-1">{breadcrumb}</div>
        )}
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

// =============================================================================
// STAT
// =============================================================================

export function Stat({ label, value, delta, sub, color, mono = true, size = 'md' }) {
  const sizeClasses = {
    sm: 'text-base',
    md: 'text-lg',
    lg: 'text-xl',
    xl: 'text-2xl',
  }[size] || 'text-lg';
  return (
    <div className="min-w-0">
      <div className="label">{label}</div>
      <div
        className={cx(
          'font-semibold mt-0.5',
          sizeClasses,
          mono && 'font-mono tnum',
          !color && 'text-ink-strong'
        )}
        style={color ? { color } : undefined}
      >
        {value}
      </div>
      {delta != null && (
        <PnlCell value={delta} format="percent" inline className="mt-0.5 text-sm" />
      )}
      {sub && (
        <div className="text-xs text-ink-muted mt-0.5">{sub}</div>
      )}
    </div>
  );
}

// =============================================================================
// PNL CELL — money or percent with semantic color
// =============================================================================

export function PnlCell({ value, format = 'percent', dp = 2, inline = false, className }) {
  if (value == null || isNaN(Number(value))) {
    return <span className={cx('text-ink-faint', className)}>—</span>;
  }
  const v = Number(value);
  const color = v > 0 ? 'text-bull' : v < 0 ? 'text-bear' : 'text-ink-muted';
  const sign = v > 0 ? '+' : '';
  const formatted = format === 'money' ? `${sign}${fmtMoney(v, dp).replace('$', v < 0 ? '-$' : '$')}`
                   : `${sign}${v.toFixed(dp)}%`;
  return (
    <span className={cx('font-mono tnum font-semibold', color, !inline && 'inline-block', className)}>
      {formatted}
    </span>
  );
}

// =============================================================================
// CHIP & GRADE CHIP
// =============================================================================

export function Chip({ children, variant = 'muted', className, size = 'sm' }) {
  const cls = {
    muted: 'chip-muted',
    bull: 'chip-bull',
    bear: 'chip-bear',
    warn: 'chip-warn',
    info: 'chip-info',
    brand: 'chip-brand',
  }[variant] || 'chip-muted';
  const sizeCls = size === 'lg' ? 'px-2.5 py-1 text-xs' : '';
  return <span className={cx(cls, sizeCls, className)}>{children}</span>;
}

const GRADE_VARIANT = {
  'A+': 'bull', 'A': 'bull',
  'B': 'brand',
  'C': 'warn',
  'D': 'warn',
  'E': 'bear',
  'F': 'bear',
};

export function GradeChip({ grade, className }) {
  if (!grade) return <span className="text-ink-faint">—</span>;
  return (
    <Chip variant={GRADE_VARIANT[grade] || 'muted'} className={cx('w-7 justify-center', className)}>
      {grade}
    </Chip>
  );
}

// =============================================================================
// BUTTON
// =============================================================================

export function Button({
  variant = 'primary', size = 'md', loading, children,
  className, icon: Icon, iconRight, type = 'button', ...rest
}) {
  const variantCls = {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    ghost: 'btn-ghost',
    danger: 'btn-danger',
  }[variant] || 'btn-primary';
  const sizeCls = {
    sm: 'px-3 py-1 text-xs',
    md: '',
    lg: 'px-5 py-2.5 text-base',
  }[size] || '';
  return (
    <button
      type={type}
      className={cx(variantCls, sizeCls, className)}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? <RefreshCw size={14} className="animate-spin" /> :
        Icon ? <Icon size={14} /> : null}
      {children}
      {iconRight && <span className="ml-1">{iconRight}</span>}
    </button>
  );
}

// =============================================================================
// INPUTS
// =============================================================================

export const Input = React.forwardRef(({ className, ...rest }, ref) => (
  <input ref={ref} className={cx('input', className)} {...rest} />
));
Input.displayName = 'Input';

export const Select = React.forwardRef(({ className, children, ...rest }, ref) => (
  <select ref={ref} className={cx('input pr-8 cursor-pointer', className)} {...rest}>
    {children}
  </select>
));
Select.displayName = 'Select';

// =============================================================================
// TABS
// =============================================================================

export function Tabs({ tabs, value, onChange, className }) {
  return (
    <div className={cx('flex border-b border-border', className)}>
      {tabs.map((tab, i) => {
        const active = value === (tab.value ?? i);
        return (
          <button
            key={tab.value ?? i}
            type="button"
            onClick={() => onChange(tab.value ?? i)}
            className={cx(
              'px-4 py-2 text-sm font-medium transition-colors duration-fast',
              'border-b-2 -mb-[1px]',
              active
                ? 'text-brand border-brand'
                : 'text-ink-muted border-transparent hover:text-ink hover:border-border-strong'
            )}
          >
            {tab.label}
            {tab.count != null && (
              <span className={cx(
                'ml-1.5 inline-flex items-center justify-center px-1.5 rounded-full text-2xs font-mono tnum',
                active ? 'bg-brand-soft text-brand' : 'bg-bg-alt text-ink-muted'
              )}>
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// =============================================================================
// SKELETON / EMPTY / ERROR / STATUS DOT
// =============================================================================

export function Skeleton({ width = '100%', height = 16, className, count = 1 }) {
  return (
    <div className={cx('flex flex-col gap-2', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="animate-pulse bg-bg-alt rounded-sm"
          style={{ width, height }}
        />
      ))}
    </div>
  );
}

export function EmptyState({ icon: Icon = Inbox, title = 'No data', description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <Icon size={36} className="text-ink-faint mb-3" strokeWidth={1.5} />
      <p className="text-sm font-medium text-ink-strong mb-1">{title}</p>
      {description && <p className="text-xs text-ink-muted max-w-sm mb-3">{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, retry }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center bg-bear-soft border border-bear/30 rounded-md">
      <AlertCircle size={32} className="text-bear mb-2" strokeWidth={1.5} />
      <p className="text-sm font-semibold text-ink-strong">Something went wrong</p>
      <p className="text-xs text-ink-muted mt-1 max-w-md">
        {typeof error === 'string' ? error : error?.message || 'Please try again'}
      </p>
      {retry && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  );
}

const STATUS_COLOR = {
  live: 'bg-bull',
  fresh: 'bg-bull',
  stale: 'bg-warn',
  error: 'bg-bear',
  unknown: 'bg-ink-faint',
};
export function StatusDot({ status = 'unknown', className }) {
  return (
    <span className={cx(
      'inline-block w-2 h-2 rounded-full',
      STATUS_COLOR[status] || STATUS_COLOR.unknown,
      status === 'live' && 'animate-pulse',
      className,
    )} />
  );
}

// =============================================================================
// FACTOR BAR
// =============================================================================

export function FactorBar({ label, value, max, sub, className }) {
  const pct = max ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const color = pct >= 70 ? 'bg-bull' : pct >= 40 ? 'bg-brand' : pct >= 20 ? 'bg-warn' : 'bg-bear';
  return (
    <div className={cx('mb-3', className)}>
      <div className="flex items-baseline justify-between mb-1">
        <span className="label">{label}</span>
        <span className="font-mono tnum text-xs text-ink-strong">
          {Number(value).toFixed(1)} / {max}
        </span>
      </div>
      <div className="h-1.5 bg-bg-alt rounded-sm overflow-hidden">
        <div
          className={cx('h-full transition-all duration-slow', color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      {sub && <div className="text-2xs text-ink-faint mt-1">{sub}</div>}
    </div>
  );
}

// =============================================================================
// TREND ARROW
// =============================================================================

export function TrendArrow({ value, size = 16 }) {
  if (value == null || value === 0) return <Minus size={size} className="text-ink-muted" />;
  return value > 0
    ? <TrendingUpIcon size={size} className="text-bull" />
    : <TrendingDownIcon size={size} className="text-bear" />;
}

// =============================================================================
// DATA TABLE
// =============================================================================

/**
 * Columns: [{ key, header, render?, sortable?, align?, width? }]
 * Rows: array of objects keyed by `key` field
 */
export function DataTable({
  columns, rows, keyField = 'id',
  onRowClick, expandRender, sortable = true,
  empty, loading, error, className,
  maxHeight = '60vh',
}) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('asc');
  const [expandedKey, setExpandedKey] = useState(null);

  const sortedRows = React.useMemo(() => {
    if (!sortKey) return rows;
    const r = [...rows];
    r.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av === bv) return 0;
      const cmp = av > bv ? 1 : -1;
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return r;
  }, [rows, sortKey, sortDir]);

  if (loading) return <Skeleton height={300} />;
  if (error) return <ErrorState error={error} />;
  if (!rows?.length) return <EmptyState {...(empty || {})} />;

  const handleSort = (col) => {
    if (!sortable || col.sortable === false) return;
    if (sortKey === col.key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(col.key); setSortDir('asc'); }
  };

  return (
    <div className={cx('overflow-auto rounded-md border border-border', className)} style={{ maxHeight }}>
      <table className="table">
        <thead>
          <tr>
            {columns.map(col => (
              <th
                key={col.key}
                onClick={() => handleSort(col)}
                className={cx(
                  col.align === 'right' && 'text-right',
                  col.sortable !== false && sortable && 'cursor-pointer select-none hover:text-ink',
                  col.width && `w-[${col.width}]`,
                )}
                style={col.width ? { width: col.width } : undefined}
              >
                <span className="inline-flex items-center gap-1">
                  {col.header}
                  {sortable && col.sortable !== false && sortKey === col.key && (
                    sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, i) => {
            const k = row[keyField] ?? i;
            const expanded = expandedKey === k;
            return (
              <React.Fragment key={k}>
                <tr
                  onClick={() => {
                    if (expandRender) setExpandedKey(prev => prev === k ? null : k);
                    if (onRowClick) onRowClick(row);
                  }}
                >
                  {columns.map(col => (
                    <td
                      key={col.key}
                      className={cx(
                        col.align === 'right' && 'text-right',
                        col.mono && 'font-mono tnum',
                      )}
                    >
                      {col.render ? col.render(row) : row[col.key] ?? '—'}
                    </td>
                  ))}
                </tr>
                {expanded && expandRender && (
                  <tr>
                    <td colSpan={columns.length} className="bg-bg-alt p-4">
                      {expandRender(row)}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// =============================================================================
// SECTION DIVIDER
// =============================================================================

export function SectionDivider({ children, className }) {
  return (
    <div className={cx('relative flex items-center my-6', className)}>
      <span className="label pr-3">{children}</span>
      <div className="flex-1 h-px bg-border" />
    </div>
  );
}

// =============================================================================
// SPARKLINE — minimal SVG, no axis, brand-colored
// =============================================================================

export function Sparkline({ data, width = 80, height = 24, color }) {
  if (!data || data.length < 2) return null;
  const values = data.map(d => typeof d === 'number' ? d : d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const dx = width / (values.length - 1);
  const points = values.map((v, i) => `${i * dx},${height - ((v - min) / range) * height}`).join(' ');
  const last = values[values.length - 1];
  const first = values[0];
  const trend = last >= first ? 'stroke-bull' : 'stroke-bear';
  return (
    <svg width={width} height={height} className={cx('inline-block align-middle', !color && trend)}>
      <polyline
        points={points}
        fill="none"
        strokeWidth={1.5}
        stroke={color || 'currentColor'}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
