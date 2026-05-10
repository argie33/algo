import React, { useState } from 'react';
import { useApiQuery } from '../hooks/useApiQuery';
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import { getApiConfig } from '../services/api';

const AuditViewer = () => {
  const { apiUrl: API_BASE_URL } = getApiConfig();
  const [limit, setLimit] = useState(100);
  const [expandedId, setExpandedId] = useState(null);

  const { data: auditData, loading: auditLoading, error: auditError, refetch } = useApiQuery(
    ['auditLog', limit],
    async () => {
      const response = await fetch(`${API_BASE_URL}/api/algo/audit-log?limit=${limit}`);
      if (!response.ok) throw new Error('Failed to fetch audit logs');
      return response.json();
    },
    { staleTime: 30000 }
  );

  const items = auditData?.items || [];

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  };

  const getStatusColor = (status) => {
    if (!status) return '#999';
    const s = status.toLowerCase();
    if (s.includes('success') || s.includes('filled')) return '#10b981';
    if (s.includes('pending')) return '#3b82f6';
    if (s.includes('failed') || s.includes('error') || s.includes('rejected')) return '#ef4444';
    return '#999';
  };

  const getActionTypeColor = (type) => {
    if (!type) return '#666';
    const t = type.toLowerCase();
    if (t.includes('entry')) return '#8b5cf6';
    if (t.includes('exit')) return '#f59e0b';
    if (t.includes('circuit')) return '#dc2626';
    if (t.includes('error')) return '#ef4444';
    return '#666';
  };

  return (
    <div style={{ padding: '20px', background: 'var(--bg-primary)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 style={{ margin: 0 }}>Audit Trail</h2>
        <button onClick={() => refetch()} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {auditError && (
        <div style={{ padding: '12px', background: '#7f1d1d', color: '#fca5a5', borderRadius: '4px', marginBottom: '16px' }}>
          Error: {auditError}
        </div>
      )}

      {auditLoading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
          Loading audit logs...
        </div>
      ) : items.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
          No audit logs found
        </div>
      ) : (
        <div>
          {items.map((item, idx) => (
            <div key={idx} style={{ marginBottom: '12px', border: '1px solid var(--border-color)', borderRadius: '4px', overflow: 'hidden' }}>
              <div onClick={() => setExpandedId(expandedId === idx ? null : idx)} style={{ padding: '12px 16px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-secondary)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flex: 1 }}>
                  <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: getStatusColor(item.status) }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                      <span style={{ padding: '2px 8px', borderRadius: '3px', fontSize: '12px', fontWeight: 'bold', background: getActionTypeColor(item.action_type), color: 'white' }}>
                        {item.action_type || 'UNKNOWN'}
                      </span>
                      {item.symbol && <span style={{ fontWeight: 'bold', color: 'var(--accent-color)' }}>{item.symbol}</span>}
                      <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>{formatDate(item.created_at)}</span>
                    </div>
                  </div>
                </div>
                {expandedId === idx ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>

              {expandedId === idx && (
                <div style={{ padding: '16px', background: 'var(--bg-primary)' }}>
                  <div style={{ marginBottom: '12px' }}>
                    <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>Status:</span>
                    <span style={{ marginLeft: '8px', fontWeight: 'bold', color: getStatusColor(item.status) }}>{item.status || 'UNKNOWN'}</span>
                  </div>
                  {item.actor && (
                    <div style={{ marginBottom: '12px' }}>
                      <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>Actor:</span>
                      <span style={{ marginLeft: '8px', fontFamily: 'monospace' }}>{item.actor}</span>
                    </div>
                  )}
                  {item.error_message && (
                    <div style={{ marginBottom: '12px', padding: '8px', background: '#7f1d1d', borderRadius: '3px' }}>
                      <span style={{ color: '#fca5a5', fontSize: '12px' }}>Error: {item.error_message}</span>
                    </div>
                  )}
                  {item.details && (
                    <div style={{ marginTop: '12px' }}>
                      <span style={{ color: 'var(--text-secondary)', fontSize: '12px', display: 'block', marginBottom: '6px' }}>Details:</span>
                      <pre style={{ background: 'var(--bg-secondary)', padding: '8px', borderRadius: '3px', overflow: 'auto', fontSize: '11px', maxHeight: '200px' }}>
                        {typeof item.details === 'string' ? item.details : JSON.stringify(item.details, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AuditViewer;
