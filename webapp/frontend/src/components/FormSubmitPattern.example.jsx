/**
 * EXAMPLE: Correct form submission pattern with error handling.
 *
 * This demonstrates the proper way to handle form submissions:
 * 1. Form state is local only
 * 2. API call is made
 * 3. State is ONLY updated AFTER API succeeds
 * 4. If API fails, form state is unchanged and error is shown
 * 5. User can retry without data loss
 */

import React, { useState } from 'react';
import { api } from '../services/api';
import { useFormSubmit } from '../hooks/useFormSubmit';
import FormErrorBoundary from './FormErrorBoundary';

function TradeSubmitForm({ onSuccess, onCancel }) {
  // Form input state (not committed until API succeeds)
  const [formData, setFormData] = useState({
    symbol: '',
    quantity: '',
    price: '',
    stopLoss: '',
  });

  // Form submission state (API status)
  const { submit, isSubmitting, error, success } = useFormSubmit(
    async (data) => {
      // This API call happens AFTER user submits
      // Local state is NOT updated optimistically
      const response = await api.post('/api/trades/manual', {
        symbol: data.symbol,
        quantity: parseInt(data.quantity, 10),
        price: parseFloat(data.price),
        stop_loss_price: parseFloat(data.stopLoss),
      });

      // Only if API succeeds do we return the result
      return response.data;
    },
    {
      onSuccess: (result) => {
        // API succeeded — NOW we can do things like:
        // - Navigate to success page
        // - Close modal
        // - Update parent state
        if (onSuccess) {
          onSuccess(result);
        }
      },
      onError: (err) => {
        // API failed — form data is STILL in the form
        // User can see what went wrong and retry
        console.error('Trade submission failed:', err);
      },
      timeout: 30000,
    }
  );

  const handleChange = (e) => {
    const { name, value } = e.target;
    // Update local form state only (not API state)
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    // Validate form before submitting
    if (!formData.symbol || !formData.quantity || !formData.price) {
      alert('Please fill in all required fields');
      return;
    }

    // Submit to API — result will contain either success or error
    const result = await submit(formData);

    if (!result.success) {
      // Error is already in state and displayed to user
      // Form data is still in the form for retry
      return;
    }

    // API succeeded — form can be cleared or parent can be notified
    setFormData({ symbol: '', quantity: '', price: '', stopLoss: '' });
  };

  return (
    <FormErrorBoundary>
      <form onSubmit={handleSubmit} className="form">
        {/* Display API errors */}
        {error && (
          <div className="alert alert-danger" style={{ marginBottom: 'var(--space-4)' }}>
            <strong>Failed to submit trade:</strong>
            {' '}
            {error}
          </div>
        )}

        {/* Display success */}
        {success && (
          <div className="alert alert-success" style={{ marginBottom: 'var(--space-4)' }}>
            Trade submitted successfully!
          </div>
        )}

        {/* Form fields */}
        <div className="field-group" style={{ marginBottom: 'var(--space-4)' }}>
          <label className="field-label" htmlFor="symbol">
            Symbol
          </label>
          <input
            className="input"
            id="symbol"
            name="symbol"
            type="text"
            value={formData.symbol}
            onChange={handleChange}
            disabled={isSubmitting}
            placeholder="AAPL"
            required
          />
        </div>

        <div className="field-group" style={{ marginBottom: 'var(--space-4)' }}>
          <label className="field-label" htmlFor="quantity">
            Quantity
          </label>
          <input
            className="input"
            id="quantity"
            name="quantity"
            type="number"
            value={formData.quantity}
            onChange={handleChange}
            disabled={isSubmitting}
            placeholder="100"
            required
          />
        </div>

        <div className="field-group" style={{ marginBottom: 'var(--space-4)' }}>
          <label className="field-label" htmlFor="price">
            Entry Price
          </label>
          <input
            className="input"
            id="price"
            name="price"
            type="number"
            step="0.01"
            value={formData.price}
            onChange={handleChange}
            disabled={isSubmitting}
            placeholder="150.00"
            required
          />
        </div>

        <div className="field-group" style={{ marginBottom: 'var(--space-4)' }}>
          <label className="field-label" htmlFor="stopLoss">
            Stop Loss
          </label>
          <input
            className="input"
            id="stopLoss"
            name="stopLoss"
            type="number"
            step="0.01"
            value={formData.stopLoss}
            onChange={handleChange}
            disabled={isSubmitting}
            placeholder="145.00"
            required
          />
        </div>

        {/* Buttons */}
        <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Submitting...' : 'Submit Trade'}
          </button>
          <button
            type="button"
            className="btn btn-default"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            Cancel
          </button>
        </div>
      </form>
    </FormErrorBoundary>
  );
}

export default TradeSubmitForm;
