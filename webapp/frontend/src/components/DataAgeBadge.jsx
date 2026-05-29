import React from 'react';
import './DataAgeBadge.css';

/**
 * DataAgeBadge - Shows how old the API response data is
 * Uses data_freshness metadata from API responses
 */
const DataAgeBadge = ({ dataFreshness, label = 'Updated' }) => {
  if (!dataFreshness) {
    return null;
  }

  const { data_age_days, is_stale, max_date, warning } = dataFreshness;

  // If no data at all
  if (data_age_days === null) {
    return (
      <span
        className="badge badge-danger data-age-badge"
        title="No data available"
      >
        ❌ No Data
      </span>
    );
  }

  let color, icon;

  // Color coding based on age
  if (data_age_days === 0) {
    color = 'success';
    icon = '✓';
  } else if (data_age_days === 1) {
    color = 'info';
    icon = '✓';
  } else if (data_age_days <= 3) {
    color = 'warning';
    icon = '⚠️';
  } else {
    color = 'danger';
    icon = '❌';
  }

  const ageText =
    data_age_days === 0
      ? 'Just now'
      : data_age_days === 1
        ? '1 day ago'
        : `${data_age_days}d ago`;

  return (
    <span
      className={`badge badge-${color} data-age-badge`}
      title={`Last updated: ${max_date}${warning ? ` - ${warning}` : ''}`}
    >
      {icon} {label} {ageText}
    </span>
  );
};

export default DataAgeBadge;
