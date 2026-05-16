import React, { useState } from 'react';
import { api } from '../services/api';
import { AlertTriangle, CheckCircle, AlertCircle } from 'lucide-react';

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
      setResult(response);
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
          Current: {typeof value === 'number' ? value.toFixed(2) : value}{unit}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <div style={{ minWidth: '100px', textAlign: 'right' }}>
          <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{typeof value === 'number' ? value.toFixed(2) : value}{unit}</div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Max: {limit}{unit}</div>
        </div>
        {passed ? (
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
                <span style={{ fontWeight: 'bold' }}>${result.entry_price.toFixed(2)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Position Size</span>
                <span style={{ fontWeight: 'bold' }}>${result.position_size_dollars.toFixed(2)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>% of Portfolio</span>
                <span style={{ fontWeight: 'bold', color: 'var(--amber)' }}>{result.position_size_percent.toFixed(2)}%</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Sector</span>
                <span style={{ fontWeight: 'bold' }}>{result.sector}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Risk Score</span>
                <span style={{ fontWeight: 'bold' }}>{(result.risk_score * 100).toFixed(0)}%</span>
              </div>
            </div>
          </div>

          {/* Constraints Check */}
          <div style={{ background: 'var(--bg-secondary)', padding: '20px', borderRadius: '8px' }}>
            <h3 style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>Constraint Check</span>
              {result.all_constraints_met ? (
                <CheckCircle size={20} color='var(--success)' />
              ) : (
                <AlertCircle size={20} color='var(--danger)' />
              )}
            </h3>
            <div style={{
              padding: '12px',
              marginBottom: '12px',
              borderRadius: '4px',
              background: result.all_constraints_met ? '#064e3b' : '#7f1d1d',
              color: result.all_constraints_met ? '#a7f3d0' : '#fca5a5',
              fontWeight: 'bold',
              textAlign: 'center'
            }}>
              {result.recommendation}
            </div>

            <div style={{ border: '1px solid var(--border-color)', borderRadius: '4px' }}>
              <ConstraintRow
                label="Position Limit"
                value={result.portfolio_impact.new_total_positions}
                limit={result.portfolio_impact.position_limit}
                passed={result.portfolio_impact.position_limit_ok}
              />
              <ConstraintRow
                label="Position Size"
                value={result.portfolio_impact.new_position_percent}
                limit={result.portfolio_impact.max_position_percent}
                passed={result.portfolio_impact.position_size_ok}
                unit="%"
              />
              <ConstraintRow
                label="Sector Concentration"
                value={result.portfolio_impact.new_sector_percent}
                limit={result.portfolio_impact.max_sector_percent}
                passed={result.portfolio_impact.sector_limit_ok}
                unit="%"
              />
              <ConstraintRow
                label="Drawdown Risk"
                value={result.portfolio_impact.worst_case_drawdown_impact}
                limit={result.portfolio_impact.max_acceptable_impact}
                passed={result.portfolio_impact.drawdown_risk_ok}
                unit="%"
              />
              <ConstraintRow
                label="Cash Available"
                value={result.portfolio_impact.cash_available}
                limit={result.portfolio_impact.cash_required}
                passed={result.portfolio_impact.cash_ok}
                unit="$"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PreTradeSimulator;
