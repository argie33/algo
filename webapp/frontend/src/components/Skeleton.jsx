import React from 'react';

export function SkeletonBar({ width = '100%', height = 24, className = '', style = {} }) {
  return (
    <div
      className={`${className}`}
      style={{
        width,
        height: `${height}px`,
        background: 'linear-gradient(90deg, var(--surface-2) 0%, var(--surface) 50%, var(--surface-2) 100%)',
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.5s infinite',
        borderRadius: 'var(--r-sm)',
        ...style,
      }}
    />
  );
}

export function SkeletonKpi() {
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-3)' }}>
        <SkeletonBar width="120px" height={12} />
        <SkeletonBar width="16px" height={16} />
      </div>
      <SkeletonBar width="100%" height={28} style={{ marginBottom: 'var(--space-2)' }} />
      <SkeletonBar width="80%" height={12} />
    </div>
  );
}

export function SkeletonChart() {
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <SkeletonBar width="160px" height={16} style={{ marginBottom: 'var(--space-1)' }} />
          <SkeletonBar width="220px" height={12} />
        </div>
      </div>
      <div className="card-body">
        <SkeletonChartContent />
      </div>
    </div>
  );
}

export function SkeletonChartContent() {
  return <SkeletonBar width="100%" height={220} />;
}

export function SkeletonTable() {
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <SkeletonBar width="160px" height={16} style={{ marginBottom: 'var(--space-1)' }} />
          <SkeletonBar width="280px" height={12} />
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} style={{ padding: 'var(--space-3)', borderBottom: i < 4 ? '1px solid var(--border-soft)' : 'none' }}>
            <SkeletonBar width="100%" height={20} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonCircuitBreaker() {
  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <SkeletonBar width="160px" height={16} style={{ marginBottom: 'var(--space-1)' }} />
          <SkeletonBar width="240px" height={12} />
        </div>
      </div>
      <div className="card-body">
        <div className="grid grid-4" style={{ gap: 'var(--space-3)' }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card" style={{ padding: 'var(--space-3)' }}>
              <SkeletonBar width="80px" height={12} style={{ marginBottom: 'var(--space-2)' }} />
              <SkeletonBar width="100%" height={24} style={{ marginBottom: 'var(--space-2)' }} />
              <SkeletonBar width="100%" height={4} style={{ borderRadius: 'var(--r-pill)' }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function AddGlobalStyles() {
  React.useEffect(() => {
    const style = document.createElement('style');
    style.textContent = `
      @keyframes shimmer {
        0% { background-position: 200% 0; }
        100% { background-position: -200% 0; }
      }
    `;
    document.head.appendChild(style);
    return () => document.head.removeChild(style);
  }, []);
  return null;
}
