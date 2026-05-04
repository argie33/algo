/**
 * Swing Candidates — full-universe swing-trader scores.
 *
 * Surfaces the complete output of swing_trader_scores: 7 component scores
 * (setup / trend / momentum / volume / fundamentals / sector / multi-tf),
 * grade, gate-pass status, fail reason, sector + industry. Filters: grade,
 * sector, gate-pass, min score. Click row → /app/stock/:symbol.
 *
 * Pure JSX + theme.css classes.
 */

import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  RefreshCw, Search, Inbox, CheckCircle, XCircle,
  TrendingUp, Filter,
} from 'lucide-react';
import { api } from '../services/api';

const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);

const GRADE_CLASS = {
  'A+': 'badge-success',
  'A':  'badge-success',
  'B':  'badge-cyan',
  'C':  'badge-amber',
  'D':  'badge',
  'F':  'badge-danger',
};

export default function SwingCandidates() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [grade, setGrade] = useState('');
  const [sector, setSector] = useState('');
  const [gateFilter, setGateFilter] = useState(''); // '', 'pass', 'fail'
  const [minScore, setMinScore] = useState(0);

  const { data: items, isLoading, refetch } = useQuery({
    queryKey: ['swing-candidates', minScore],
    queryFn: () =>
      api.get(`/api/algo/swing-scores?limit=500&min_score=${minScore}`)
         .then(r => r.data?.items || []),
    refetchInterval: 60000,
  });

  const sectors = useMemo(() => {
    if (!items) return [];
    return Array.from(new Set(items.map(i => i.sector).filter(Boolean))).sort();
  }, [items]);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = search.trim().toUpperCase();
    return items.filter(i => {
      if (q && !(i.symbol || '').toUpperCase().includes(q)) return false;
      if (grade && i.grade !== grade) return false;
      if (sector && i.sector !== sector) return false;
      if (gateFilter === 'pass' && !i.pass_gates) return false;
      if (gateFilter === 'fail' && i.pass_gates) return false;
      return true;
    });
  }, [items, search, grade, sector, gateFilter]);

  // Grade distribution for the KPI strip
  const stats = useMemo(() => {
    if (!items) return { total: 0, passing: 0, gradeA: 0, top10Score: 0 };
    const passing = items.filter(i => i.pass_gates).length;
    const gradeA = items.filter(i => i.grade === 'A' || i.grade === 'A+').length;
    const top10 = items.slice(0, 10);
    const top10Score = top10.length === 0 ? 0
      : top10.reduce((s, i) => s + (i.swing_score || 0), 0) / top10.length;
    return { total: items.length, passing, gradeA, top10Score };
  }, [items]);

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Swing Candidates</div>
          <div className="page-head-sub">
            Full-universe research-weighted scoring · setup · trend · momentum · volume · fundamentals · sector · multi-TF
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={() => refetch()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-4">
        <Kpi label="Total Universe" value={stats.total.toLocaleString()} sub="ranked candidates" />
        <Kpi label="Pass All Gates" value={stats.passing.toLocaleString()}
             sub={`${stats.total ? Math.round(stats.passing / stats.total * 100) : 0}% qualify`}
             tone={stats.passing > 0 ? 'up' : ''} />
        <Kpi label="Grade A / A+" value={stats.gradeA.toLocaleString()}
             sub="institutional-quality" tone={stats.gradeA > 0 ? 'up' : ''} />
        <Kpi label="Top-10 Avg" value={`${num(stats.top10Score, 1)}/100`} sub="composite score" />
      </div>

      {/* Filters bar */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body">
          <div className="flex items-center gap-3" style={{ flexWrap: 'wrap' }}>
            <div className="flex items-center gap-2" style={{ flex: '1 1 220px', minWidth: 200 }}>
              <Search size={14} className="muted" />
              <input
                className="input"
                placeholder="Search symbol…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ flex: 1 }}
              />
            </div>
            <select className="select" value={grade} onChange={e => setGrade(e.target.value)}>
              <option value="">All grades</option>
              <option value="A+">A+</option>
              <option value="A">A</option>
              <option value="B">B</option>
              <option value="C">C</option>
              <option value="D">D</option>
              <option value="F">F</option>
            </select>
            <select className="select" value={sector} onChange={e => setSector(e.target.value)}>
              <option value="">All sectors</option>
              {sectors.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select className="select" value={gateFilter} onChange={e => setGateFilter(e.target.value)}>
              <option value="">All gates</option>
              <option value="pass">Pass only</option>
              <option value="fail">Fail only</option>
            </select>
            <select className="select" value={minScore} onChange={e => setMinScore(Number(e.target.value))}>
              <option value="0">Score ≥ 0</option>
              <option value="40">Score ≥ 40</option>
              <option value="60">Score ≥ 60</option>
              <option value="75">Score ≥ 75</option>
              <option value="85">Score ≥ 85</option>
            </select>
            <span className="t-xs muted" style={{ marginLeft: 'auto' }}>
              <Filter size={12} style={{ verticalAlign: '-2px' }} /> {filtered.length} of {items?.length || 0}
            </span>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body" style={{ padding: 0 }}>
          {isLoading ? (
            <Empty title="Loading universe…" />
          ) : filtered.length === 0 ? (
            <Empty title="No candidates match filters"
                   desc="Loosen filters or wait for the next eval cycle." />
          ) : (
            <div style={{ overflow: 'auto', maxHeight: '70vh' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: 32 }} className="num">#</th>
                    <th>Symbol</th>
                    <th>Sector</th>
                    <th>Grade</th>
                    <th className="num">Score</th>
                    <th className="num">Setup</th>
                    <th className="num">Trend</th>
                    <th className="num">Mom</th>
                    <th className="num">Vol</th>
                    <th className="num">Fund</th>
                    <th className="num">Sector</th>
                    <th className="num">MTF</th>
                    <th>Gates</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((c, i) => (
                    <Row key={c.symbol} c={c} rank={i + 1}
                         onClick={() => navigate(`/app/stock/${c.symbol}`)} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Component legend */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Score Components</div>
            <div className="card-sub">Research-weighted composite — each component contributes to the 0-100 score</div>
          </div>
        </div>
        <div className="card-body">
          <div className="grid grid-4">
            <Legend name="Setup" desc="VCP / cup-with-handle / flat-base / pivot proximity" />
            <Legend name="Trend" desc="Minervini 8-pt template + Weinstein stage" />
            <Legend name="Momentum" desc="ADX / RSI sweet spot / multi-TF alignment" />
            <Legend name="Volume" desc="Pocket-pivot count / dry-up + breakout volume" />
            <Legend name="Fundamentals" desc="EPS / sales / margin growth + ROE filter" />
            <Legend name="Sector" desc="Mansfield RS + sector rotation tier" />
            <Legend name="Multi-TF" desc="Daily + weekly + monthly alignment" />
            <Legend name="Gates" desc="Trend + SQS + advanced filters all pass" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── row ───────────────────────────────────────────────────────────────────
function Row({ c, rank, onClick }) {
  const cmp = c.components || {};
  return (
    <tr onClick={onClick} style={{ cursor: 'pointer' }}>
      <td className="num mono tnum muted">{rank}</td>
      <td>
        <span className="strong" style={{ fontWeight: 'var(--w-semibold)' }}>{c.symbol}</span>
      </td>
      <td className="t-xs muted" style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {c.sector || '—'}
      </td>
      <td>
        <span className={`badge ${GRADE_CLASS[c.grade] || 'badge'}`}>{c.grade || '—'}</span>
      </td>
      <td className="num mono tnum" style={{ fontWeight: 'var(--w-semibold)' }}>
        {num(c.swing_score, 1)}
      </td>
      <td className="num mono tnum t-xs">{num(cmp.setup, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.trend, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.momentum, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.volume, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.fundamentals, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.sector, 1)}</td>
      <td className="num mono tnum t-xs">{num(cmp.multi_tf, 1)}</td>
      <td>
        {c.pass_gates ? (
          <span className="badge badge-success">
            <CheckCircle size={11} style={{ verticalAlign: '-2px' }} /> PASS
          </span>
        ) : (
          <span className="badge badge-danger" title={c.fail_reason || ''}>
            <XCircle size={11} style={{ verticalAlign: '-2px' }} /> {c.fail_reason ? c.fail_reason.slice(0, 18) : 'FAIL'}
          </span>
        )}
      </td>
    </tr>
  );
}

// ─── small ─────────────────────────────────────────────────────────────────
function Kpi({ label, value, sub, tone }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="flex items-center justify-between">
        <div className="eyebrow">{label}</div>
        <TrendingUp size={16} className="muted" />
      </div>
      <div className={`mono ${tone || ''}`}
           style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
        {value}
      </div>
      {sub && <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>{sub}</div>}
    </div>
  );
}

function Legend({ name, desc }) {
  return (
    <div className="stile">
      <div className="stile-label">{name}</div>
      <div className="t-xs muted" style={{ marginTop: 4 }}>{desc}</div>
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
