import React from 'react';

export const FormField = ({ label, type = 'text', value, onChange, error, required = false, ...props }) => {
  return (
    <div className="form-field" style={{ marginBottom: '1rem' }}>
      {label && (
        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold' }}>
          {label}
          {required && <span style={{ color: 'red' }}>*</span>}
        </label>
      )}
      <input
        type={type}
        value={value}
        onChange={onChange}
        style={{
          width: '100%',
          padding: '0.5rem',
          border: `1px solid ${error ? '#f44336' : '#ddd'}`,
          borderRadius: '4px',
          fontSize: '1rem'
        }}
        {...props}
      />
      {error && <div style={{ color: '#f44336', fontSize: '0.875rem', marginTop: '0.25rem' }}>{error}</div>}
    </div>
  );
};