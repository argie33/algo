/**
 * AppLayout — Bullseye platform shell (Tailwind, no MUI)
 *
 * Left nav (240px desktop, drawer on mobile) + Header (56px) + Footer (40px)
 * per the standards in DESIGN_REDESIGN_PLAN.md and the user-approved plan.
 *
 * Light-theme default with dark mode toggle. Polls /algo/markets and
 * /algo/notifications every 30s for live status pills.
 */

import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { createPortal } from 'react-dom';
import {
  Menu, Settings, LogOut, LogIn, User as UserIcon, X,
  TrendingUp, Briefcase, Globe, Activity, Heart, Target,
  BarChart3, Layers, Wallet, History, Sliders, GitBranch,
  HeartPulse, Zap, Award, Boxes, Sun, Moon,
  ShieldCheck,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';
import { cx, fmtAgo, Chip, StatusDot, Button } from './ui/Primitives';

// =============================================================================
// NAVIGATION STRUCTURE
// =============================================================================

const navSections = [
  {
    title: 'Markets',
    items: [
      { text: 'Market Overview', icon: TrendingUp, path: '/app/market' },
      { text: 'Sector Analysis', icon: Briefcase, path: '/app/sectors' },
      { text: 'Sentiment',       icon: Activity,  path: '/app/sentiment' },
      { text: 'Economic',        icon: Globe,     path: '/app/economic' },
      { text: 'Commodities',     icon: Boxes,     path: '/app/commodities' },
    ],
  },
  {
    title: 'Stocks',
    items: [
      { text: 'Stock Scores',     icon: Award,     path: '/app/scores' },
      { text: 'Trading Signals',  icon: Zap,       path: '/app/trading-signals' },
      { text: 'Swing Candidates', icon: Target,    path: '/app/swing' },
      { text: 'Deep Value Picks', icon: Layers,    path: '/app/deep-value' },
    ],
  },
  {
    title: 'Portfolio & Trading',
    items: [
      { text: 'Portfolio',     icon: Wallet,   path: '/app/portfolio' },
      { text: 'Trade Tracker', icon: History,  path: '/app/trades' },
      { text: 'Optimizer',     icon: Sliders,  path: '/app/optimizer' },
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
      { text: 'Settings',       icon: Settings,   path: '/app/settings' },
    ],
  },
];

// =============================================================================
// THEME TOGGLE — light/dark
// =============================================================================

function useTheme() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'light';
    return localStorage.getItem('algo-theme') || 'light';
  });
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    localStorage.setItem('algo-theme', theme);
  }, [theme]);
  return [theme, setTheme];
}

// =============================================================================
// MARKET STATUS PILL — exposure regime indicator in header
// =============================================================================

const REGIME_VARIANT = {
  confirmed_uptrend: 'bull',
  healthy_uptrend: 'brand',
  pressure: 'warn',
  caution: 'warn',
  correction: 'bear',
};

function ExposurePill({ exposure }) {
  if (!exposure) {
    return <Chip variant="muted" className="font-mono">EXP --</Chip>;
  }
  const regime = exposure.regime?.replace(/uptrend_under_pressure/, 'pressure') || 'unknown';
  const variant = REGIME_VARIANT[regime] || 'muted';
  return (
    <Chip variant={variant} className="font-mono tnum">
      EXP {exposure.exposure_pct}%
    </Chip>
  );
}

// =============================================================================
// LEFT NAV (drawer)
// =============================================================================

function LeftNav({ onNavigate, exposure, onClose }) {
  const location = useLocation();

  return (
    <aside className="h-full flex flex-col bg-bg-elev border-r border-border w-60 shrink-0">
      {/* Brand */}
      <div
        className="px-4 h-14 border-b border-border flex items-center gap-2 cursor-pointer hover:bg-brand-tint transition-colors"
        onClick={() => onNavigate('/')}
      >
        <div className="w-7 h-7 rounded-md bg-brand flex items-center justify-center shrink-0">
          <ShieldCheck size={16} className="text-white" />
        </div>
        <span className="text-lg font-black text-ink-strong tracking-tight">BULLSEYE</span>
        {onClose && (
          <button onClick={onClose} className="ml-auto md:hidden p-1 text-ink-muted hover:text-ink">
            <X size={18} />
          </button>
        )}
      </div>

      {/* Sections */}
      <nav className="flex-1 overflow-y-auto py-2">
        {navSections.map(section => (
          <div key={section.title} className="mb-3">
            <div className="px-4 py-1.5 text-2xs font-semibold uppercase text-ink-faint tracking-wider">
              {section.title}
            </div>
            <ul>
              {section.items.map(item => {
                const Icon = item.icon;
                const selected = location.pathname === item.path
                              || location.pathname.startsWith(item.path + '/');
                return (
                  <li key={item.path}>
                    <button
                      onClick={() => onNavigate(item.path)}
                      className={cx(
                        'w-full flex items-center gap-3 px-4 py-2 text-sm transition-colors',
                        'mx-0 rounded-none',
                        selected
                          ? 'bg-brand-soft text-brand font-semibold border-r-2 border-brand'
                          : 'text-ink hover:bg-bg-alt hover:text-ink-strong'
                      )}
                    >
                      <Icon size={16} strokeWidth={2} className={selected ? 'text-brand' : 'text-ink-muted'} />
                      <span className="truncate">{item.text}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer in nav */}
      <div className="border-t border-border px-4 py-2 bg-bg text-2xs font-mono text-ink-faint flex items-center justify-between">
        <span>v1.0</span>
        {exposure?.regime && (
          <span className="truncate ml-2">{exposure.regime.replace(/_/g, ' ')}</span>
        )}
      </div>
    </aside>
  );
}

// =============================================================================
// HEADER
// =============================================================================

function Header({ onMenu, exposure, notifications, theme, onToggleTheme, user, onLogin, onLogout }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const initials = user?.email?.[0]?.toUpperCase() || '?';

  return (
    <header className="h-14 bg-bg-elev border-b border-border flex items-center px-4 gap-3 shrink-0">
      {/* Hamburger (mobile only) */}
      <button onClick={onMenu} className="md:hidden p-1.5 text-ink hover:bg-bg-alt rounded-md">
        <Menu size={20} />
      </button>

      {/* Live status pills */}
      <div className="flex items-center gap-2 ml-auto">
        <ExposurePill exposure={exposure} />
        {notifications?.length > 0 && (
          <Chip variant="bear" className="font-mono">
            {notifications.length} ALERTS
          </Chip>
        )}
        <Chip variant="muted" className="hidden lg:inline-flex">
          <StatusDot status={exposure ? 'live' : 'unknown'} className="mr-1.5" />
          {exposure ? 'live' : 'connecting'}
        </Chip>
      </div>

      {/* Theme toggle */}
      <button
        onClick={onToggleTheme}
        title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
        className="p-1.5 text-ink-muted hover:text-ink hover:bg-bg-alt rounded-md transition-colors"
      >
        {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
      </button>

      {/* User menu */}
      <div className="relative">
        {user ? (
          <button
            onClick={() => setMenuOpen(o => !o)}
            className="w-8 h-8 rounded-full bg-brand-soft text-brand font-semibold text-sm flex items-center justify-center hover:ring-2 hover:ring-brand/30"
          >
            {initials}
          </button>
        ) : (
          <Button variant="primary" size="sm" icon={LogIn} onClick={onLogin}>Sign in</Button>
        )}
        {user && menuOpen && (
          <div
            className="absolute right-0 top-full mt-1 w-56 bg-bg-elev border border-border rounded-md shadow-md py-1 z-50"
            onMouseLeave={() => setMenuOpen(false)}
          >
            <div className="px-3 py-2 border-b border-border-light">
              <div className="text-xs font-semibold text-ink-strong truncate">{user.email}</div>
              <div className="text-2xs text-ink-faint">Signed in</div>
            </div>
            <button
              className="w-full px-3 py-2 text-left text-sm hover:bg-bg-alt flex items-center gap-2"
              onClick={() => { setMenuOpen(false); /* nav to settings */ }}
            >
              <Settings size={14} /> Settings
            </button>
            <button
              className="w-full px-3 py-2 text-left text-sm hover:bg-bg-alt flex items-center gap-2 text-bear"
              onClick={() => { setMenuOpen(false); onLogout(); }}
            >
              <LogOut size={14} /> Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

// =============================================================================
// FOOTER
// =============================================================================

function Footer({ exposure, lastUpdated }) {
  return (
    <footer className="hidden sm:flex h-10 bg-bg-elev border-t border-border px-4 items-center justify-between text-2xs font-mono text-ink-faint shrink-0">
      <div className="flex items-center gap-3">
        <span>BULLSEYE v1.0</span>
        {lastUpdated && <span>Updated {lastUpdated}</span>}
      </div>
      <div>Data: Yahoo Finance · Alpaca · Computed</div>
    </footer>
  );
}

// =============================================================================
// MOBILE DRAWER
// =============================================================================

function MobileDrawer({ open, onClose, ...navProps }) {
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 md:hidden">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="absolute left-0 top-0 bottom-0 w-70 bg-bg-elev shadow-lg animate-in slide-in-from-left">
        <LeftNav {...navProps} onClose={onClose} />
      </div>
    </div>,
    document.body,
  );
}

// =============================================================================
// MAIN LAYOUT
// =============================================================================

const AppLayout = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, user, logout } = useAuth();
  const [theme, setTheme] = useTheme();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [exposure, setExposure] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);

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
        setLastUpdated(fmtAgo(Date.now()));
      } catch (_) { /* silent */ }
    };
    fetchStatus();
    const id = setInterval(fetchStatus, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Close drawer on route change
  useEffect(() => { setDrawerOpen(false); }, [location.pathname]);

  const handleNav = (path) => {
    navigate(path);
    setDrawerOpen(false);
  };

  const navProps = { onNavigate: handleNav, exposure };

  return (
    <div className="min-h-screen flex bg-bg text-ink">
      {/* Desktop nav */}
      <div className="hidden md:flex md:w-60 shrink-0">
        <LeftNav {...navProps} />
      </div>

      {/* Mobile drawer */}
      <MobileDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} {...navProps} />

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        <Header
          onMenu={() => setDrawerOpen(true)}
          exposure={exposure}
          notifications={notifications}
          theme={theme}
          onToggleTheme={() => setTheme(t => t === 'light' ? 'dark' : 'light')}
          user={isAuthenticated ? user : null}
          onLogin={() => { /* TODO: wire to auth modal */ }}
          onLogout={logout}
        />

        <main className="flex-1 overflow-y-auto">
          {children}
        </main>

        <Footer exposure={exposure} lastUpdated={lastUpdated} />
      </div>
    </div>
  );
};

export default AppLayout;
