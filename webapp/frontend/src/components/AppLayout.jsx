/**
 * AppLayout — Bullseye Trading platform shell
 *
 * Pure JSX + theme.css classes. No MUI. No Tailwind.
 * Light theme is default per FRONTEND_DESIGN_SYSTEM.md (finance UX research);
 * dark is opt-in via the user-menu toggle (persisted to localStorage).
 * All visual tokens live in src/styles/tokens.css.
 *
 * Layout: 260px left sidebar (brand · nav · user) + main content + footer.
 * Mobile: drawer slides over.
 */

import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Menu, Settings, LogOut, LogIn, X, Sun, Moon,
  TrendingUp, Briefcase, Globe, Activity, Target,
  Award, Layers, Wallet, History, Sliders, GitBranch,
  HeartPulse, Zap, Boxes, ShieldCheck, Crosshair,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';

// ═════════════════════════════════════════════════════════════════════════
// NAVIGATION
// ═════════════════════════════════════════════════════════════════════════

const NAV_SECTIONS = [
  {
    title: 'Markets',
    items: [
      { text: 'Market Health',   icon: TrendingUp, path: '/app/market' },
      { text: 'Sector Analysis', icon: Briefcase,  path: '/app/sectors' },
      { text: 'Sentiment',       icon: Activity,   path: '/app/sentiment' },
      { text: 'Economic',        icon: Globe,      path: '/app/economic' },
      { text: 'Commodities',     icon: Boxes,      path: '/app/commodities' },
    ],
  },
  {
    title: 'Stocks',
    items: [
      { text: 'Stock Scores',     icon: Award,    path: '/app/scores' },
      { text: 'Trading Signals',  icon: Zap,      path: '/app/trading-signals' },
      { text: 'Swing Candidates', icon: Target,   path: '/app/swing' },
      { text: 'Deep Value Picks', icon: Layers,   path: '/app/deep-value' },
    ],
  },
  {
    title: 'Portfolio',
    items: [
      { text: 'Portfolio',     icon: Wallet,  path: '/app/portfolio' },
      { text: 'Trade Tracker', icon: History, path: '/app/trades' },
      { text: 'Optimizer',     icon: Sliders, path: '/app/optimizer' },
    ],
  },
  {
    title: 'Research',
    items: [
      { text: 'Backtests', icon: GitBranch, path: '/app/backtests' },
    ],
  },
  {
    title: 'System',
    items: [
      { text: 'Service Health', icon: HeartPulse, path: '/app/health' },
    ],
  },
];

// ═════════════════════════════════════════════════════════════════════════
// MAIN
// ═════════════════════════════════════════════════════════════════════════

export default function AppLayout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, user, logout } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [exposure, setExposure] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('theme') === 'dark' ? 'dark' : 'light'; }
    catch { return 'light'; }
  });

  // Apply class on <html> + persist whenever the user toggles
  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light');
    try { localStorage.setItem('theme', theme); } catch { /* localStorage blocked */ }
  }, [theme]);

  const toggleTheme = () => setTheme(t => (t === 'light' ? 'dark' : 'light'));

  // Poll status every 30s
  useEffect(() => {
    let cancelled = false;
    const fetchStatus = async () => {
      try {
        const [e, n] = await Promise.all([
          api.get('/api/algo/markets').catch(() => null),
          api.get('/api/algo/notifications').catch(() => null),
        ]);
        if (cancelled) return;
        setExposure(e?.data?.data?.current || null);
        setNotifications(n?.data?.items || []);
      } catch { /* silent */ }
    };
    fetchStatus();
    const id = setInterval(fetchStatus, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Close drawer on route change
  useEffect(() => { setDrawerOpen(false); setUserMenuOpen(false); }, [location.pathname]);

  // Close user menu on outside click
  useEffect(() => {
    if (!userMenuOpen) return;
    const onClick = () => setUserMenuOpen(false);
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, [userMenuOpen]);

  const go = (path) => { navigate(path); setDrawerOpen(false); };
  const userInitial = (user?.email || user?.username || '?')[0].toUpperCase();
  const userLabel = user?.email || user?.username || 'Account';

  return (
    <div className="app-shell">
      {/* SIDEBAR */}
      <aside className={`sidebar${drawerOpen ? ' open' : ''}`}>
        {/* Brand */}
        <div className="sidebar-brand" onClick={() => go('/')}>
          <div className="sidebar-brand-mark">
            <Crosshair size={22} strokeWidth={2.25} />
          </div>
          <div className="flex-1">
            <div className="sidebar-brand-name grad">BULLSEYE</div>
            <div className="sidebar-brand-tag">Swing Trading</div>
          </div>
          <button
            type="button"
            className="btn-icon btn btn-ghost hidden"
            onClick={(e) => { e.stopPropagation(); setDrawerOpen(false); }}
            style={{ display: drawerOpen ? 'inline-flex' : 'none' }}
            aria-label="Close menu"
          >
            <X size={16} />
          </button>
        </div>

        {/* Nav */}
        <nav className="sidebar-nav">
          {NAV_SECTIONS.map(section => (
            <div className="sidebar-section" key={section.title}>
              <div className="sidebar-section-label">{section.title}</div>
              {section.items.map(item => {
                const Icon = item.icon;
                const active = location.pathname === item.path
                            || location.pathname.startsWith(item.path + '/');
                return (
                  <div
                    key={item.path}
                    className={`sidebar-link${active ? ' active' : ''}`}
                    onClick={() => go(item.path)}
                    role="link"
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') go(item.path); }}
                  >
                    <Icon size={16} strokeWidth={2} />
                    <span>{item.text}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </nav>

        {/* User box at bottom */}
        <div
          className="sidebar-user"
          onClick={(e) => { e.stopPropagation(); isAuthenticated ? setUserMenuOpen(o => !o) : go('/login'); }}
          role="button"
          tabIndex={0}
        >
          {isAuthenticated ? (
            <>
              <div className="sidebar-user-avatar">{userInitial}</div>
              <div className="sidebar-user-info">
                <div className="sidebar-user-name">{userLabel}</div>
                <div className="sidebar-user-meta">Signed in · click for menu</div>
              </div>
              <Settings size={14} className="shrink-0" style={{ color: 'var(--text-faint)' }} />
            </>
          ) : (
            <>
              <div className="sidebar-user-avatar" style={{ background: 'var(--surface-2)' }}>
                <LogIn size={14} />
              </div>
              <div className="sidebar-user-info">
                <div className="sidebar-user-name">Sign in</div>
                <div className="sidebar-user-meta">Access your portfolio</div>
              </div>
            </>
          )}
        </div>
        {userMenuOpen && (
          <div
            style={{
              position: 'absolute', left: 12, bottom: 84,
              width: 232, background: 'var(--surface)',
              border: '1px solid var(--border-2)', borderRadius: 'var(--r-md)',
              boxShadow: 'var(--shadow-md)', overflow: 'hidden', zIndex: 60,
            }}
            onClick={e => e.stopPropagation()}
          >
            <button className="btn btn-ghost w-full" style={{ justifyContent: 'flex-start', borderRadius: 0, padding: '10px 14px' }}
              onClick={() => { setUserMenuOpen(false); go('/app/settings'); }}>
              <Settings size={14} /> Settings
            </button>
            <div style={{ borderTop: '1px solid var(--border-soft)' }} />
            <button className="btn btn-ghost w-full" style={{ justifyContent: 'flex-start', borderRadius: 0, padding: '10px 14px' }}
              onClick={() => { toggleTheme(); }}
              title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}>
              {theme === 'light' ? <Moon size={14} /> : <Sun size={14} />}
              {theme === 'light' ? 'Dark theme' : 'Light theme'}
            </button>
            <div style={{ borderTop: '1px solid var(--border-soft)' }} />
            <button className="btn btn-ghost w-full" style={{ justifyContent: 'flex-start', borderRadius: 0, padding: '10px 14px', color: 'var(--danger)' }}
              onClick={() => { setUserMenuOpen(false); logout?.(); }}>
              <LogOut size={14} /> Sign out
            </button>
          </div>
        )}
      </aside>

      {/* Drawer backdrop */}
      {drawerOpen && (
        <div
          onClick={() => setDrawerOpen(false)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
            zIndex: 40, animation: 'fade-in var(--t-base)',
          }}
        />
      )}

      {/* MAIN */}
      <div id="main">
        {/* Header */}
        <header className="app-header">
          <button
            type="button"
            className="btn btn-icon btn-ghost"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open menu"
            style={{ display: 'none' }}
            // shown on mobile via inline media query workaround:
            data-mobile-only="true"
          >
            <Menu size={18} />
          </button>
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            {exposure && <ExposurePill exposure={exposure} />}
            {notifications?.length > 0 && (
              <span className="badge badge-danger">{notifications.length} ALERT{notifications.length === 1 ? '' : 'S'}</span>
            )}
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 animate-in" style={{ overflowY: 'auto' }}>
          {children}
        </main>

        {/* Footer */}
        <footer className="app-footer">
          <div>BULLSEYE</div>
          <div>Yahoo Finance · Alpaca · Computed</div>
        </footer>
      </div>

      {/* Mobile drawer toggle visibility — inline media query rule */}
      <style>{`
        @media (max-width: 900px) {
          [data-mobile-only="true"] { display: inline-flex !important; }
        }
      `}</style>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════
// EXPOSURE PILL
// ═════════════════════════════════════════════════════════════════════════

const REGIME_VARIANT = {
  confirmed_uptrend: 'badge-success',
  healthy_uptrend:   'badge-brand',
  pressure:          'badge-amber',
  uptrend_under_pressure: 'badge-amber',
  caution:           'badge-amber',
  correction:        'badge-danger',
};

function ExposurePill({ exposure }) {
  const regime = (exposure.regime || '').replace(/uptrend_under_pressure/, 'pressure');
  const variant = REGIME_VARIANT[regime] || '';
  return (
    <span className={`badge ${variant} mono tnum`}>
      EXP {exposure.exposure_pct}%
    </span>
  );
}
