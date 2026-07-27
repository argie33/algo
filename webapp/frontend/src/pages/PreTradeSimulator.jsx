import React, { useState } from 'react';
import { api } from '../services/api';
import { AlertTriangle, CheckCircle, AlertCircle } from 'lucide-react';
import { formatNumber } from '../utils/formatters';

const PreTradeSimulator = () => {
  const [symbol, setSymbol] = useState('');
  const [entryPrice, setEntryPrice] = useState('');
  const [positionType, setPositionType] = useState('dollars');
  const [positionValue, setPositionValue] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSimulate = async () => {
    if (!symbol || !positionValue) {
      setError('Symbol and position size required');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = {
        symbol: symbol.toUpperCase(),
        entry_price: entryPrice ? parseFloat(entryPrice) : null
      };

      if (positionType === 'dollars') {
        payload.position_dollars = parseFloat(positionValue);
      } else {
        payload.position_pct = parseFloat(positionValue);
      }

      const response = await api.post('/api/algo/pre-trade-impact', payload);
      const data = response.data;

      // Check for error responses (success: false indicates API error)
      if (data?.success === false) {
        setError(data?.error || 'Failed to run simulation');
        return;
      }

      setResult(data);
    } catch (err) {
      setError(err.message || 'Failed to run simulation');
    } finally {
      setLoading(false);
    }
  };

  const ConstraintRow = ({ label, value, limit, passed, unit = '' }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', borderBottom: '1px solid var(--border-color)', alignItems: 'center' }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{label}</div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          Current: {typeof value === 'number' ? formatNumber(value, 2) : value}{unit}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <div style={{ minWidth: '100px', textAlign: 'right' }}>
          <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{typeof value === 'number' ? value.toFixed(2) : value}{unit}</div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Max: {limit}{unit}</div>
        </div>
        {passed == null ? (
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }} title="Constraint check unavailable - no data returned">N/A</span>
        ) : passed ? (
          <CheckCircle size={20} color='var(--success)' />
        ) : (
          <AlertCircle size={20} color='var(--danger)' />
        )}
      </div>
    </div>
  );

  return (
    <div style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
      <h2 style={{ marginBottom: '20px' }}>Pre-Trade Impact Simulator</h2>

      {/* Input Section */}
      <div style={{ background: 'var(--bg-secondary)', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', marginBottom: '16px' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontSize: '12px', fontWeight: 'bold', color: 'var(--text-secondary)' }}>
              Symbol
            </label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="AAPL"
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-color)',
                borderRadius: '4px',
                color: 'var(--text)',
                fontWeight: 'bold',
                fontSize: '14px'
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontSize: '12px', fontWeight: 'bold', color: 'var(--text-secondary)' }}>
              Entry Price (optional)
            </label>
            <input
              type="number"
              value={entryPrice}
              onChange={(e) => setEntryPrice(e.target.value)}
              placeholder="Current price"
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-color)',
                borderRadius: '4px',
                color: 'var(--text)',
                fontSize: '14px'
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontSize: '12px', fontWeight: 'bold', color: 'var(--text-secondary)' }}>
              Position Size
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="number"
                value={positionValue}
                onChange={(e) => setPositionValue(e.target.value)}
                placeholder={positionType === 'dollars' ? '5000' : '2.5'}
                style={{
                  flex: 1,
                  padding: '10px',
                  background: 'var(--bg-primary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '4px',
                  color: 'var(--text)',
                  fontSize: '14px'
                }}
              />
              <select
                value={positionType}
                onChange={(e) => setPositionType(e.target.value)}
                style={{
                  padding: '10px',
                  background: 'var(--bg-primary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '4px',
                  color: 'var(--text)',
                  fontSize: '12px'
                }}
              >
                <option value="dollars">$</option>
                <option value="percent">%</option>
              </select>
            </div>
          </div>
        </div>

        <button
          onClick={handleSimulate}
          disabled={loading || !symbol || !positionValue}
          style={{
            width: '100%',
            padding: '12px',
            background: loading || !symbol || !positionValue ? 'var(--bg-tertiary)' : 'var(--accent-color)',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            fontWeight: 'bold',
            cursor: loading || !symbol || !positionValue ? 'not-allowed' : 'pointer',
            opacity: loading || !symbol || !positionValue ? 0.5 : 1
          }}
        >
          {loading ? 'Running Simulation...' : 'Simulate Impact'}
        </button>
      </div>

      {error && (
        <div style={{ background: '#7f1d1d', color: '#fca5a5', padding: '12px', borderRadius: '4px', marginBottom: '20px' }}>
          <AlertTriangle size={18} style={{ marginRight: '8px' }} />
          {error}
        </div>
      )}

      {result && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          {/* Trade Details */}
          <div style={{ background: 'var(--bg-secondary)', padding: '20px', borderRadius: '8px' }}>
            <h3 style={{ marginBottom: '16px' }}>Trade Details</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Symbol</span>
                <span style={{ fontWeight: 'bold', color: 'var(--accent-color)' }}>{result.symbol}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Entry Price</span>
                <span style={{ fontWeight: 'bold' }}>{result.entry_price != null ? `$${Number(result.entry_price).toFixed(2)}` : '—'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Shares</span>
                <span style={{ fontWeight: 'bold' }}>{result.shares ?? '—'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Position Size</span>
                <span style={{ fontWeight: 'bold' }}>{result.position_dollars != null ? `$${Number(result.position_dollars).toFixed(2)}` : '—'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>% of Portfolio</span>
                <span style={{ fontWeight: 'bold', color: 'var(--amber)' }}>{result.pct_of_portfolio != null ? `${Number(result.pct_of_portfolio).toFixed(2)}%` : '—'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Sector</span>
                <span style={{ fontWeight: 'bold' }}>{result.sector ?? '—'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Available Slots</span>
                <span style={{ fontWeight: 'bold' }}>{result.available_slots ?? '—'} of 15</span>
              </div>
            </div>
          </div>

          {/* Sector Concentration */}
          <div style={{ background: 'var(--bg-secondary)', padding: '20px', borderRadius: '8px' }}>
            <h3 style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>Sector Concentration</span>
              {!result.sector_exposure ? (
                <AlertCircle size={20} color='var(--text-secondary)' title="No sector exposure data returned" />
              ) : result.sector_exposure.warning ? (
                <AlertCircle size={20} color='var(--danger)' />
              ) : (
                <CheckCircle size={20} color='var(--success)' />
              )}
            </h3>
            {/* CRITICAL: !result.sector_exposure?.warning defaulted to true (green "within
                limits") when sector_exposure was entirely missing from the API response - a
                pre-trade safety check silently reporting PASS for a check that never actually
                ran, instead of surfacing "unknown". Now explicitly three-state: no data / warn
                / ok. */}
            <div style={{
              padding: '12px',
              marginBottom: '12px',
              borderRadius: '4px',
              background: !result.sector_exposure ? 'var(--bg-primary)' : result.sector_exposure.warning ? '#7f1d1d' : '#064e3b',
              color: !result.sector_exposure ? 'var(--text-secondary)' : result.sector_exposure.warning ? '#fca5a5' : '#a7f3d0',
              fontWeight: 'bold',
              textAlign: 'center'
            }}>
              {!result.sector_exposure
                ? 'Sector concentration data unavailable - not checked'
                : result.sector_exposure.warning_msg || 'Within sector concentration limits'}
            </div>

            <div style={{ border: '1px solid var(--border-color)', borderRadius: '4px' }}>
              <ConstraintRow
                label={`${result.sector ?? 'Sector'} - Current`}
                value={result.sector_exposure?.current_pct ?? '—'}
                limit={30}
                passed={result.sector_exposure ? !result.sector_exposure.warning : null}
                unit="%"
              />
              <ConstraintRow
                label={`${result.sector ?? 'Sector'} - After Trade`}
                value={result.sector_exposure?.projected_pct ?? '—'}
                limit={30}
                passed={result.sector_exposure ? !result.sector_exposure.warning : null}
                unit="%"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PreTradeSimulator;

