import React, { useState } from 'react';
import { X, ChevronRight } from 'lucide-react';
import { api } from '../services/api';

export default function PreviewModal({ isOpen, onClose, onConfirm }) {
  const [symbol, setSymbol] = useState('');
  const [entryPrice, setEntryPrice] = useState('');
  const [stopPrice, setStopPrice] = useState('');
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);

  const handlePreview = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.post('/algo/preview', {
        symbol: symbol.toUpperCase(),
        entry_price: parseFloat(entryPrice),
        stop_loss_price: parseFloat(stopPrice)
      });
      if (!response.success) {
        setError(response.error || 'Failed');
        return;
      }
      setPreview(response.preview);
    } catch (err) {
      setError(err.message || 'Failed');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = () => {
    if (preview && onConfirm) {
      onConfirm({
        symbol,
        entry_price: parseFloat(entryPrice),
        stop_loss_price: parseFloat(stopPrice),
        shares: preview.shares
      });
      handleClose();
    }
  };

  const handleClose = () => {
    setSymbol('');
    setEntryPrice('');
    setStopPrice('');
    setLoading(false);
    setPreview(null);
    setError(null);
    onClose();
  };

  if (!isOpen) return null;

  const num = (v, dp = 2) => v == null ? 'N/A' : Number(v).toFixed(dp);
  const fmtMoney = (v) => v == null ? 'N/A' : `$${Number(v).toLocaleString()}`;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Trade Preview</h2>
          <button onClick={handleClose} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <X size={20} />
          </button>
        </div>

        {!preview ? (
          <div className="modal-body">
            <div className="form-group">
              <label>Symbol</label>
              <input
                type="text"
                placeholder="QQQ"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                disabled={loading}
              />
            </div>
            <div className="form-group">
              <label>Entry Price</label>
              <input
                type="number"
                placeholder="0.00"
                value={entryPrice}
                onChange={(e) => setEntryPrice(e.target.value)}
                step="0.01"
                disabled={loading}
              />
            </div>
            <div className="form-group">
              <label>Stop Loss Price</label>
              <input
                type="number"
                placeholder="0.00"
                value={stopPrice}
                onChange={(e) => setStopPrice(e.target.value)}
                step="0.01"
                disabled={loading}
              />
            </div>
            {error && <div className="error-message">{error}</div>}
            <button
              onClick={handlePreview}
              disabled={!symbol || !entryPrice || !stopPrice || loading}
              className="btn btn-primary"
            >
              {loading ? 'Calculating...' : 'Calculate Preview'}
            </button>
          </div>
        ) : (
          <div className="modal-body">
            <div className="preview-section">
              <h3>Position Summary</h3>
              <div className="grid-2">
                <div><span className="label">Shares</span><div className="value">{num(preview.shares)} sh</div></div>
                <div><span className="label">Position Value</span><div className="value">{fmtMoney(preview.position_value)}</div></div>
                <div><span className="label">% of Portfolio</span><div className="value">{num(preview.pct_of_portfolio)}%</div></div>
                <div><span className="label">Risk Amount</span><div className="value" style={{color: 'var(--red-400)'}}>{fmtMoney(preview.risk_amount)}</div></div>
              </div>
            </div>
            <div className="preview-section">
              <h3>Targets</h3>
              {Object.entries(preview.targets).map(([k, v]) => (
                <div key={k} className="target-item">
                  <div><strong>{v.r_multiple}R @ ${num(v.price, 3)}</strong></div>
                  <div>Sell {num(v.shares_to_sell)} sh = +{fmtMoney(v.profit_at_target)}</div>
                </div>
              ))}
            </div>
            <button onClick={() => setPreview(null)} className="btn">Back</button>
            <button onClick={handleConfirm} className="btn btn-primary">Confirm & Enter</button>
          </div>
        )}
      </div>
    </div>
  );
}
