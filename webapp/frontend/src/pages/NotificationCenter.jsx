/**
 * Notification Center — Real-time alerts, trade execution notifications, risk breaches
 * Surfaces algo notifications (entries, exits, errors, safeguards) in one dashboard
 */

import React, { useState, useEffect } from 'react';
import { useApiQuery } from '../hooks/useApiQuery';
import { api, getApiConfig } from '../services/api';
import {
  Bell, X, CheckCircle, AlertCircle, AlertTriangle, XCircle,
  Clock, Trash2, RefreshCw, Filter
} from 'lucide-react';

const NotificationCenter = () => {
  const [filters, setFilters] = useState({
    kind: 'all',
    severity: 'all',
    limit: 50
  });
  const [unreadOnly, setUnreadOnly] = useState(false);

  const { data: notifs, loading, refetch } = useApiQuery(
    ['notifications', filters, unreadOnly],
    async () => {
      const params = new URLSearchParams();
      if (filters.kind !== 'all') params.set('kind', filters.kind);
      if (filters.severity !== 'all') params.set('severity', filters.severity);
      if (unreadOnly) params.set('unread', 'true');
      params.set('limit', filters.limit);

      const response = await api.get(`/api/algo/notifications?${params.toString()}`);
      return response.data;
    },
    { refetchInterval: 15000 }
  );

  const items = notifs?.items || [];
  const unreadCount = items.filter(n => !n.seen).length;

  const getSeverityIcon = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical':
        return <XCircle size={18} style={{ color: 'var(--danger)' }} />;
      case 'error':
        return <AlertCircle size={18} style={{ color: 'var(--danger)' }} />;
      case 'warning':
        return <AlertTriangle size={18} style={{ color: 'var(--amber)' }} />;
      default:
        return <CheckCircle size={18} style={{ color: 'var(--success)' }} />;
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical':
      case 'error':
        return 'var(--danger)';
      case 'warning':
        return 'var(--amber)';
      default:
        return 'var(--success)';
    }
  };

  const getKindBadgeColor = (kind) => {
    switch (kind?.toLowerCase()) {
      case 'trade':
        return 'badge-indigo';
      case 'error':
      case 'alert':
        return 'badge-danger';
      case 'safeguard':
        return 'badge-warning';
      default:
        return 'badge-neutral';
    }
  };

  const formatTime = (dateString) => {
    if (!dateString) return '—';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;

    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (seconds < 60) return `${seconds}s ago`;
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days}d ago`;

    return date.toLocaleDateString('en-US', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
    });
  };

  const markAsRead = async (id) => {
    try {
      await api.patch(`/api/notifications/${id}/read`);
      refetch();
    } catch (err) {
      console.error('Failed to mark as read:', err);
    }
  };

  const deleteNotification = async (id) => {
    try {
      await api.delete(`/api/notifications/${id}`);
      refetch();
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  return (
    <div style={{ padding: '20px', background: 'var(--bg)' }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '20px'
      }}>
        <div>
          <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Bell size={24} />
            Notifications
            {unreadCount > 0 && (
              <span style={{
                background: 'var(--danger)',
                color: 'white',
                borderRadius: '50%',
                width: '24px',
                height: '24px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 'var(--t-sm)',
                fontWeight: 'bold'
              }}>
                {unreadCount}
              </span>
            )}
          </h2>
          <p style={{ color: 'var(--text-muted)', margin: '4px 0 0 0', fontSize: 'var(--t-sm)' }}>
            Real-time trade alerts, risk breaches, and system notifications
          </p>
        </div>
        <button
          onClick={() => refetch()}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 12px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--r-sm)',
            color: 'var(--text)',
            cursor: 'pointer',
            fontSize: 'var(--t-sm)'
          }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Filters */}
      <div style={{
        display: 'flex',
        gap: '12px',
        marginBottom: '20px',
        flexWrap: 'wrap'
      }}>
        <select
          value={filters.kind}
          onChange={(e) => setFilters({ ...filters, kind: e.target.value })}
          style={{
            padding: '8px 12px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--r-sm)',
            color: 'var(--text)',
            fontSize: 'var(--t-sm)'
          }}
        >
          <option value="all">All kinds</option>
          <option value="trade">Trade alerts</option>
          <option value="alert">Alerts</option>
          <option value="error">Errors</option>
          <option value="safeguard">Safeguards</option>
        </select>

        <select
          value={filters.severity}
          onChange={(e) => setFilters({ ...filters, severity: e.target.value })}
          style={{
            padding: '8px 12px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--r-sm)',
            color: 'var(--text)',
            fontSize: 'var(--t-sm)'
          }}
        >
          <option value="all">All severity</option>
          <option value="critical">Critical</option>
          <option value="error">Error</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>

        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '8px 12px',
          background: unreadOnly ? 'var(--brand-soft)' : 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--r-sm)',
          cursor: 'pointer',
          fontSize: 'var(--t-sm)',
          color: 'var(--text)'
        }}>
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(e) => setUnreadOnly(e.target.checked)}
            style={{ cursor: 'pointer' }}
          />
          Unread only
        </label>
      </div>

      {/* Notifications List */}
      {loading ? (
        <div style={{
          textAlign: 'center',
          padding: '40px',
          color: 'var(--text-muted)'
        }}>
          Loading notifications...
        </div>
      ) : items.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '60px 20px',
          color: 'var(--text-muted)'
        }}>
          <Bell size={48} style={{ opacity: 0.3, marginBottom: '16px' }} />
          <p style={{ fontSize: 'var(--t-lg)', fontWeight: 'bold' }}>No notifications</p>
          <p style={{ fontSize: 'var(--t-sm)' }}>You're all caught up!</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {items.map((notif) => (
            <div
              key={notif.id}
              style={{
                padding: '16px',
                background: notif.seen ? 'var(--surface)' : 'var(--surface-2)',
                border: `1px solid ${notif.seen ? 'var(--border)' : 'var(--border-2)'}`,
                borderLeft: `3px solid ${getSeverityColor(notif.severity)}`,
                borderRadius: 'var(--r-sm)',
                display: 'flex',
                gap: '16px',
                alignItems: 'flex-start'
              }}
            >
              {/* Icon */}
              <div style={{ marginTop: '2px', flexShrink: 0 }}>
                {getSeverityIcon(notif.severity)}
              </div>

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  display: 'flex',
                  gap: '10px',
                  alignItems: 'center',
                  marginBottom: '6px'
                }}>
                  <span style={{
                    fontSize: 'var(--t-sm)',
                    fontWeight: 'bold',
                    color: 'var(--text)'
                  }}>
                    {notif.title}
                  </span>
                  <span className={`badge ${getKindBadgeColor(notif.kind)}`} style={{
                    padding: '2px 8px',
                    fontSize: 'var(--t-2xs)',
                    fontWeight: 'bold'
                  }}>
                    {notif.kind?.toUpperCase()}
                  </span>
                  {notif.symbol && (
                    <span style={{
                      fontSize: 'var(--t-sm)',
                      fontWeight: 'bold',
                      color: 'var(--brand)',
                      background: 'var(--brand-soft)',
                      padding: '2px 8px',
                      borderRadius: '3px'
                    }}>
                      {notif.symbol}
                    </span>
                  )}
                </div>

                {notif.message && (
                  <p style={{
                    margin: '8px 0 8px 0',
                    color: 'var(--text-2)',
                    fontSize: 'var(--t-sm)',
                    lineHeight: '1.4'
                  }}>
                    {notif.message}
                  </p>
                )}

                {notif.details && typeof notif.details === 'object' && Object.keys(notif.details).length > 0 && (
                  <div style={{
                    background: 'var(--bg)',
                    padding: '8px 12px',
                    borderRadius: '3px',
                    fontSize: 'var(--t-2xs)',
                    fontFamily: 'var(--font-mono)',
                    maxHeight: '120px',
                    overflow: 'auto',
                    margin: '8px 0'
                  }}>
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordWrap: 'break-word' }}>
                      {JSON.stringify(notif.details, null, 2)}
                    </pre>
                  </div>
                )}

                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  fontSize: 'var(--t-xs)',
                  color: 'var(--text-muted)',
                  marginTop: '8px'
                }}>
                  <Clock size={12} />
                  {formatTime(notif.created_at)}
                </div>
              </div>

              {/* Actions */}
              <div style={{
                display: 'flex',
                gap: '8px',
                flexShrink: 0
              }}>
                {!notif.seen && (
                  <button
                    onClick={() => markAsRead(notif.id)}
                    title="Mark as read"
                    style={{
                      padding: '6px',
                      background: 'var(--brand-soft)',
                      border: '1px solid var(--border)',
                      borderRadius: '3px',
                      cursor: 'pointer',
                      color: 'var(--brand)',
                      display: 'flex',
                      alignItems: 'center'
                    }}
                  >
                    <CheckCircle size={14} />
                  </button>
                )}
                <button
                  onClick={() => deleteNotification(notif.id)}
                  title="Delete"
                  style={{
                    padding: '6px',
                    background: 'var(--danger-soft)',
                    border: '1px solid var(--border)',
                    borderRadius: '3px',
                    cursor: 'pointer',
                    color: 'var(--danger)',
                    display: 'flex',
                    alignItems: 'center'
                  }}
                >
                  <X size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default NotificationCenter;
