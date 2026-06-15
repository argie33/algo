import React, { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle, Edit2, Save, X, RotateCcw } from 'lucide-react';
import { getAlgoConfig, updateAlgoConfigKey, resetAlgoConfigKey } from '../services/api';

/**
 * ConfigurationViewer — TIER 3 Configuration Visibility
 *
 * Displays all algo configuration parameters organized by category.
 * Shows which values are custom vs using defaults.
 * Helps users understand what "rules" govern the trading system.
 */

const CATEGORY_ORDER = [
  'Risk Management',
  'Drawdown Defense',
  'Circuit Breakers',
  'Market Conditions',
  'Filter Thresholds',
  'Entry Rules (Minervini)',
  'Entry Quality Gates',
  'Exit Rules',
  'Pyramid & Re-engagement',
  'Position Monitoring',
  'Swing Trader Scoring',
  'Economic & Earnings',
  'Fundamental Filters',
  'Advanced Filters',
  'Risk Metrics',
  'Execution Mode',
  'Feature Flags',
  'Network Configuration',
  'Failsafe Configuration',
  'Other',
];

export default function ConfigurationViewer() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [config, setConfig] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  const loadConfig = async () => {
    try {
      setLoading(true);
      const response = await getAlgoConfig();
      // Extract items from response (could be array directly or wrapped in items property)
      const items = Array.isArray(response) ? response : response?.data?.items || response?.items || [];
      setConfig(items);
      // Auto-select first category
      if (items.length > 0) {
        const categories = [...new Set(items.map(item => item.category || 'Other'))];
        if (categories.length > 0) {
          setSelectedCategory(categories[0]);
        }
      }
    } catch (err) {
      console.error('Failed to load config:', err);
      setError('Failed to load configuration');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  const handleConfigUpdate = (key, newValue) => {
    // Update the local state to reflect the change immediately
    setConfig(config.map(item =>
      item.key === key
        ? { ...item, value: newValue, is_custom: true }
        : item
    ));
  };

  const groupedConfig = React.useMemo(() => {
    const groups = {};
    CATEGORY_ORDER.forEach(cat => {
      groups[cat] = [];
    });

    (config || []).forEach(item => {
      const category = item.category || 'Other';
      if (!groups[category]) {
        groups[category] = [];
      }
      groups[category].push(item);
    });

    return groups;
  }, [config]);

  const filteredByCategory = React.useMemo(() => {
    if (!selectedCategory) return [];
    const items = groupedConfig[selectedCategory] || [];
    if (!searchTerm) return items;

    return items.filter(item =>
      item.key.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.description?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.value?.toString().toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [groupedConfig, selectedCategory, searchTerm]);

  const categories = CATEGORY_ORDER.filter(cat => (groupedConfig[cat] || []).length > 0);

  if (loading) {
    return (
      <div className="main-content">
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
          <p>Loading configuration...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="main-content">
        <div style={{ padding: '20px' }}>
          <div className="alert alert-danger">
            <AlertCircle size={18} style={{ marginRight: '8px' }} />
            {error}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="main-content">
      {/* Page Header */}
      <div className="page-head">
        <div>
          <div className="page-head-title">Configuration</div>
          <div className="page-head-sub">View all trading parameters and thresholds</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '24px', padding: 'var(--space-6)', maxWidth: '1400px', margin: '0 auto' }}>
        {/* Sidebar: Categories */}
        <div style={{
          width: '240px',
          flexShrink: 0,
          borderRight: '1px solid var(--border)',
          paddingRight: '24px',
        }}>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ fontSize: '12px', fontWeight: 'bold', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Categories
            </label>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {categories.map(cat => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                style={{
                  padding: '8px 12px',
                  background: selectedCategory === cat ? 'var(--surface-2)' : 'transparent',
                  border: 'none',
                  borderRadius: '4px',
                  color: selectedCategory === cat ? 'var(--brand)' : 'var(--text)',
                  fontSize: '13px',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s',
                  borderLeft: selectedCategory === cat ? '3px solid var(--brand)' : '3px solid transparent',
                  paddingLeft: selectedCategory === cat ? '9px' : '12px',
                }}
                onMouseEnter={(e) => {
                  if (selectedCategory !== cat) {
                    e.target.style.background = 'var(--surface)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (selectedCategory !== cat) {
                    e.target.style.background = 'transparent';
                  }
                }}
              >
                {cat}
                <span style={{ fontSize: '11px', marginLeft: '4px', color: 'var(--text-muted)' }}>
                  ({(groupedConfig[cat] || []).length})
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Main: Config Items */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Search */}
          <div style={{ marginBottom: '24px' }}>
            <input
              type="text"
              placeholder="Search by key, description, or value..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid var(--border)',
                borderRadius: '4px',
                fontSize: '13px',
                background: 'var(--surface)',
                color: 'var(--text)',
              }}
            />
          </div>

          {/* Config Items */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {filteredByCategory.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '40px' }}>
                <p>No configuration items found</p>
              </div>
            ) : (
              filteredByCategory.map(item => (
                <ConfigItem key={item.key} item={item} onUpdate={handleConfigUpdate} />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ConfigItem({ item, onUpdate }) {
  const isCustom = item.is_custom;
  const defaultVal = item.default_value;
  const currentVal = item.value;
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(String(currentVal || ''));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  const valueHasChanged = editValue.trim() !== String(currentVal || '').trim();
  const valueEqualsDefault = String(currentVal || '').trim() === String(defaultVal || '').trim();

  const getInputType = () => {
    const type = item.value_type?.toLowerCase() || 'string';
    if (type === 'float' || type === 'number' || type === 'int') return 'number';
    if (type === 'boolean') return 'checkbox';
    return 'text';
  };

  const validateInput = () => {
    const trimmed = editValue.trim();

    if (trimmed === '') {
      return { valid: false, message: 'Value cannot be empty' };
    }

    const type = item.value_type?.toLowerCase() || 'string';

    if (type === 'float' || type === 'number' || type === 'int') {
      const num = parseFloat(trimmed);
      if (isNaN(num)) {
        return { valid: false, message: `Value must be a valid number` };
      }
      if (type === 'int' && !Number.isInteger(num)) {
        return { valid: false, message: `Value must be an integer` };
      }
    }

    if (type === 'boolean') {
      if (!['true', 'false', '0', '1', 'yes', 'no'].includes(trimmed.toLowerCase())) {
        return { valid: false, message: `Value must be true or false` };
      }
    }

    return { valid: true };
  };

  const handleSave = async () => {
    const trimmed = editValue.trim();

    if (trimmed === String(currentVal || '').trim()) {
      setSuccess(true);
      setTimeout(() => setSuccess(false), 2000);
      setIsEditing(false);
      return;
    }

    const validation = validateInput();
    if (!validation.valid) {
      setError(validation.message);
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const res = await updateAlgoConfigKey(item.key, trimmed);
      if (res?.status === 'success' || res?.statusCode === 200) {
        setIsEditing(false);
        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
        if (onUpdate) {
          onUpdate(item.key, trimmed);
        }
      } else {
        setError(res?.message || 'Failed to update config');
      }
    } catch (err) {
      setError(err?.message || 'Failed to update config');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm(`Reset ${item.key} to default value: ${defaultVal}?`)) {
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const res = await resetAlgoConfigKey(item.key);
      if (res?.status === 'success' || res?.statusCode === 200) {
        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
        if (onUpdate) {
          onUpdate(item.key, defaultVal);
        }
      } else {
        setError(res?.message || 'Failed to reset config');
      }
    } catch (err) {
      setError(err?.message || 'Failed to reset config');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEditValue(String(currentVal || ''));
    setIsEditing(false);
    setError(null);
  };

  return (
    <div style={{
      padding: '16px',
      border: '1px solid var(--border)',
      borderRadius: '6px',
      background: 'var(--bg)',
      transition: 'all 0.2s',
    }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--border-2)';
        e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      {/* Header: Key + Custom Badge + Edit Button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <code style={{
            fontSize: '13px',
            fontWeight: 'bold',
            color: 'var(--text)',
            fontFamily: 'monospace',
            letterSpacing: '0.5px',
          }}>
            {item.key}
          </code>
          {isCustom && (
            <span style={{
              fontSize: '10px',
              padding: '2px 6px',
              borderRadius: '3px',
              background: 'var(--amber-soft)',
              color: 'var(--amber)',
              fontWeight: 'bold',
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}>
              CUSTOM
            </span>
          )}
          {!isCustom && (
            <span style={{
              fontSize: '10px',
              padding: '2px 6px',
              borderRadius: '3px',
              background: 'var(--success-soft)',
              color: 'var(--success)',
              fontWeight: 'bold',
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}>
              DEFAULT
            </span>
          )}
        </div>
        {!isEditing && (
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setIsEditing(true)}
              style={{
                padding: '4px 8px',
                background: 'transparent',
                border: '1px solid var(--border)',
                borderRadius: '3px',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                fontSize: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => {
                e.target.style.borderColor = 'var(--brand)';
                e.target.style.color = 'var(--brand)';
              }}
              onMouseLeave={(e) => {
                e.target.style.borderColor = 'var(--border)';
                e.target.style.color = 'var(--text-muted)';
              }}
            >
              <Edit2 size={12} />
              Edit
            </button>
            {isCustom && (
              <button
                onClick={handleReset}
                disabled={saving}
                style={{
                  padding: '4px 8px',
                  background: 'transparent',
                  border: '1px solid var(--border)',
                  borderRadius: '3px',
                  color: 'var(--text-muted)',
                  cursor: saving ? 'not-allowed' : 'pointer',
                  fontSize: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  transition: 'all 0.2s',
                  opacity: saving ? 0.5 : 1,
                }}
                onMouseEnter={(e) => {
                  if (!saving) {
                    e.target.style.borderColor = 'var(--amber)';
                    e.target.style.color = 'var(--amber)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!saving) {
                    e.target.style.borderColor = 'var(--border)';
                    e.target.style.color = 'var(--text-muted)';
                  }
                }}
              >
                <RotateCcw size={12} />
                Reset
              </button>
            )}
          </div>
        )}
      </div>

      {/* Description */}
      {item.description && (
        <div style={{
          fontSize: '13px',
          color: 'var(--text-muted)',
          marginBottom: '12px',
          lineHeight: '1.4',
        }}>
          {item.description}
        </div>
      )}

      {/* Success Message */}
      {success && (
        <div style={{
          fontSize: '12px',
          color: 'var(--success)',
          background: 'var(--success-soft)',
          padding: '8px',
          borderRadius: '3px',
          marginBottom: '12px',
          marginTop: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}>
          <CheckCircle size={14} />
          Config updated successfully
        </div>
      )}

      {/* Error Message (if editing) */}
      {error && (
        <div style={{
          fontSize: '12px',
          color: 'var(--danger)',
          background: 'var(--danger-soft)',
          padding: '8px',
          borderRadius: '3px',
          marginBottom: '12px',
          marginTop: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}>
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {/* Values Grid / Edit Input */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '16px',
        marginTop: '12px',
      }}>
        <div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            {isEditing ? 'New Value' : 'Current Value'}
          </div>
          {isEditing ? (
            <div>
              <input
                type={getInputType()}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                disabled={saving}
                placeholder="Enter new value..."
                style={{
                  width: '100%',
                  padding: '6px 8px',
                  fontSize: '13px',
                  fontFamily: 'monospace',
                  background: 'var(--surface-2)',
                  border: error ? '1px solid var(--danger)' : '1px solid var(--brand)',
                  borderRadius: '3px',
                  color: 'var(--text)',
                  boxSizing: 'border-box',
                }}
              />
              {valueHasChanged && (
                <div style={{ fontSize: '11px', color: 'var(--brand)', marginTop: '4px', fontWeight: '500' }}>
                  ✓ Changes pending
                </div>
              )}
            </div>
          ) : (
            <div style={{
              fontSize: '13px',
              fontFamily: 'monospace',
              padding: '6px 8px',
              background: isCustom && !valueEqualsDefault ? 'var(--amber-soft)' : 'var(--surface-2)',
              borderRadius: '3px',
              color: isCustom && !valueEqualsDefault ? 'var(--amber)' : 'var(--text)',
              wordBreak: 'break-all',
              border: isCustom && !valueEqualsDefault ? '1px solid var(--amber)' : 'none',
            }}>
              {currentVal !== null && currentVal !== undefined ? String(currentVal) : '(null)'}
            </div>
          )}
          {item.value_type && (
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
              Type: <code style={{ fontFamily: 'monospace' }}>{item.value_type}</code>
            </div>
          )}
        </div>

        {defaultVal !== undefined && defaultVal !== null && (
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Default Value {!valueEqualsDefault && <span style={{ color: 'var(--amber)' }}>• Different</span>}
            </div>
            <div style={{
              fontSize: '13px',
              fontFamily: 'monospace',
              padding: '6px 8px',
              background: !valueEqualsDefault ? 'var(--surface-3)' : 'var(--surface-2)',
              borderRadius: '3px',
              color: !valueEqualsDefault ? 'var(--amber)' : 'var(--text-muted)',
              wordBreak: 'break-all',
              border: !valueEqualsDefault ? '1px solid var(--border)' : 'none',
              fontWeight: !valueEqualsDefault ? '500' : 'normal',
            }}>
              {String(defaultVal)}
            </div>
            {!valueEqualsDefault && (
              <div style={{ fontSize: '11px', color: 'var(--amber)', marginTop: '4px', fontWeight: '500' }}>
                💡 Current differs from default
              </div>
            )}
          </div>
        )}
      </div>

      {/* Edit Actions */}
      {isEditing && (
        <div>
          <div style={{
            display: 'flex',
            gap: '8px',
            marginTop: '12px',
          }}>
            <button
              onClick={handleSave}
              disabled={saving || !valueHasChanged}
              title={!valueHasChanged ? 'No changes to save' : 'Save changes'}
              style={{
                padding: '6px 12px',
                background: !valueHasChanged ? 'var(--border)' : 'var(--brand)',
                color: 'var(--text-on-brand)',
                border: 'none',
                borderRadius: '3px',
                cursor: (!valueHasChanged || saving) ? 'not-allowed' : 'pointer',
                fontSize: '12px',
                fontWeight: 'bold',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                opacity: (saving || !valueHasChanged) ? 0.6 : 1,
                transition: 'all 0.2s',
              }}
            >
              <Save size={12} />
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={handleCancel}
              disabled={saving}
              style={{
                padding: '6px 12px',
                background: 'transparent',
                color: 'var(--text-muted)',
                border: '1px solid var(--border)',
                borderRadius: '3px',
                cursor: saving ? 'not-allowed' : 'pointer',
                fontSize: '12px',
                opacity: saving ? 0.6 : 1,
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                transition: 'all 0.2s',
              }}
            >
              <X size={12} />
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Updated Info */}
      {item.updated_at && (
        <div style={{
          fontSize: '11px',
          color: 'var(--text-muted)',
          marginTop: '12px',
          paddingTop: '12px',
          borderTop: '1px solid var(--border)',
        }}>
          Last updated: {new Date(item.updated_at).toLocaleDateString()} {new Date(item.updated_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
