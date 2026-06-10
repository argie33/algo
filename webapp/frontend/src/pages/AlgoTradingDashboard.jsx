/**
 * Algo Trading Dashboard Setup
 *
 * Download and run the Python algo dashboard locally for real-time trading insights.
 */

import React from 'react';
import { Download, Terminal } from 'lucide-react';

export default function AlgoTradingDashboard() {
  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Algo Trading Dashboard</div>
          <div className="page-head-sub">Run locally for real-time market insights and position tracking</div>
        </div>
      </div>

      <div className="card" style={{ maxWidth: '600px', margin: 'var(--space-6) auto' }}>
        <div className="card-body">
          <div style={{ textAlign: 'center' }}>
            <Terminal size={48} style={{ color: 'var(--brand)', marginBottom: 'var(--space-4)' }} />

            <h2 style={{ fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)', marginBottom: 'var(--space-4)' }}>
              Algo Ops Terminal Dashboard
            </h2>

            <p style={{ color: 'var(--text-muted)', marginBottom: 'var(--space-6)', fontSize: 'var(--t-base)' }}>
              Download the Python dashboard script and run it locally to monitor your algo trading system in real-time.
            </p>

            <div style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--r-md)',
              padding: 'var(--space-4)',
              marginBottom: 'var(--space-6)',
              textAlign: 'left',
            }}>
              <div className="t-sm muted strong" style={{ marginBottom: 'var(--space-2)' }}>Usage:</div>
              <code style={{
                display: 'block',
                background: 'var(--surface)',
                padding: 'var(--space-3)',
                borderRadius: 'var(--r-sm)',
                fontSize: 'var(--t-xs)',
                overflow: 'auto',
                marginBottom: 'var(--space-3)',
              }}>
                python tools/dashboard/dashboard.py -w 30
              </code>
              <div className="t-2xs muted">
                Live view with auto-refresh every 30 seconds (q or Ctrl+C to exit)
              </div>
            </div>

            <a
              href="/download/tools/dashboard/dashboard.py"
              download
              className="btn btn-primary"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)' }}
            >
              <Download size={16} />
              Download dashboard.py
            </a>

            <p style={{
              color: 'var(--text-muted)',
              fontSize: 'var(--t-xs)',
              marginTop: 'var(--space-4)',
            }}>
              Requires Python 3.9+ and database access configured
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
