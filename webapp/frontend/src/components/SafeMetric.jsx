import React from 'react';
import PropTypes from 'prop-types';
import { AlertCircle } from 'lucide-react';

/**
 * SafeMetric component - displays a metric value safely, handling missing/invalid data.
 * Replaces patterns like: value ?? 0, percentage ?? 0%, etc.
 *
 * Props:
 *   value: The metric value to display
 *   label: Display label for the metric
 *   format: Function to format the value (e.g., (v) => `${v}%`)
 *   fallback: What to show when value is invalid (default: "—")
 *   showError: Boolean to show error state (default: false)
 *   errorMessage: Custom error message to display
 *   className: CSS class for container
 *   formatter: Shortcut formatter ('percentage', 'money', 'number', 'decimal2')
 */
export const SafeMetric = ({
  value,
  label = null,
  format = null,
  fallback = '—',
  showError = false,
  errorMessage = null,
  className = '',
  formatter = null,
  ...props
}) => {
  // Check if value is invalid (null, undefined, or DataError)
  const isInvalid = value === null || value === undefined;
  const isDataError =
    typeof value === 'object' && value?.isDataError === true;
  const hasError = showError || isDataError || isInvalid;

  // Determine what to display
  let displayValue = fallback;
  let displayError = errorMessage;

  if (!hasError && value !== null && value !== undefined) {
    // Apply formatter if specified
    if (formatter === 'percentage') {
      displayValue = `${Number(value).toFixed(2)}%`;
    } else if (formatter === 'money') {
      displayValue = `$${Number(value).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;
    } else if (formatter === 'number') {
      displayValue = Number(value).toLocaleString('en-US');
    } else if (formatter === 'decimal2') {
      displayValue = Number(value).toFixed(2);
    } else if (typeof format === 'function') {
      // Apply custom format function
      displayValue = format(value);
    } else {
      displayValue = value;
    }
  }

  if (isDataError && !displayError) {
    displayError = value?.message || 'Data validation error';
  }

  // Build className
  const containerClasses = [
    'safe-metric',
    hasError && 'safe-metric--error',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={containerClasses} {...props}>
      {label && (
        <span className="safe-metric__label">{label}</span>
      )}
      <span className="safe-metric__value">
        {hasError && <AlertCircle className="safe-metric__icon" size={16} />}
        {displayValue}
      </span>
      {displayError && (
        <span className="safe-metric__error">{displayError}</span>
      )}
    </div>
  );
};

SafeMetric.propTypes = {
  value: PropTypes.any,
  label: PropTypes.string,
  format: PropTypes.func,
  fallback: PropTypes.any,
  showError: PropTypes.bool,
  errorMessage: PropTypes.string,
  className: PropTypes.string,
  formatter: PropTypes.oneOf([
    'percentage',
    'money',
    'number',
    'decimal2',
  ]),
};

/**
 * SafeMetricValue - lightweight version that just returns formatted value string.
 * Use in contexts where you're building a string manually.
 *
 * Returns formatted value or fallback string.
 */
export const SafeMetricValue = ({
  value,
  formatter = null,
  format = null,
  fallback = '—',
}) => {
  if (value === null || value === undefined) {
    return fallback;
  }

  if (typeof value === 'object' && value?.isDataError === true) {
    return fallback;
  }

  // Apply formatter
  if (formatter === 'percentage') {
    return `${Number(value).toFixed(2)}%`;
  }
  if (formatter === 'money') {
    return `$${Number(value).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }
  if (formatter === 'number') {
    return Number(value).toLocaleString('en-US');
  }
  if (formatter === 'decimal2') {
    return Number(value).toFixed(2);
  }
  if (typeof format === 'function') {
    return format(value);
  }

  return value;
};

SafeMetricValue.propTypes = {
  value: PropTypes.any,
  formatter: PropTypes.oneOf([
    'percentage',
    'money',
    'number',
    'decimal2',
  ]),
  format: PropTypes.func,
  fallback: PropTypes.any,
};

/**
 * SafeMetricInline - single-line metric display, often used in text/labels.
 * Combines label and value in one span.
 */
export const SafeMetricInline = ({
  label = '',
  value,
  formatter = null,
  format = null,
  fallback = '—',
  separator = ': ',
  className = '',
}) => {
  const formatted = SafeMetricValue({ value, formatter, format, fallback });
  return (
    <span className={`safe-metric-inline ${className}`.trim()}>
      {label && <span className="safe-metric-inline__label">{label}</span>}
      {label && separator && (
        <span className="safe-metric-inline__separator">{separator}</span>
      )}
      <span className="safe-metric-inline__value">{formatted}</span>
    </span>
  );
};

SafeMetricInline.propTypes = {
  label: PropTypes.string,
  value: PropTypes.any,
  formatter: PropTypes.oneOf([
    'percentage',
    'money',
    'number',
    'decimal2',
  ]),
  format: PropTypes.func,
  fallback: PropTypes.any,
  separator: PropTypes.string,
  className: PropTypes.string,
};
