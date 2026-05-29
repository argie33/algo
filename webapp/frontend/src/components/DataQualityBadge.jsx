import React, { useEffect, useState } from 'react';
import { apiCall } from '../utils/apiService';
import './DataQualityBadge.css'; // We'll create this CSS

/**
 * DataQualityBadge - Shows data completeness percentage
 * Fetches data from an API endpoint and calculates what % has all required fields
 */
const DataQualityBadge = ({
  apiEndpoint = '/api/scores?limit=500',
  requiredFields = [],
  componentName = 'DataQualityBadge'
}) => {
  const [completeness, setCompleteness] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const data = await apiCall(apiEndpoint, {}, componentName);

        if (data && data.items && data.items.length > 0) {
          let completeCount = 0;

          data.items.forEach((item) => {
            let hasAllFields = true;
            requiredFields.forEach((field) => {
              if (item[field] == null) {
                hasAllFields = false;
              }
            });
            if (hasAllFields) completeCount++;
          });

          const pct = Math.round((completeCount / data.items.length) * 100);
          setCompleteness(pct);
        }
      } catch (err) {
        console.error('Failed to check data completeness:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [apiEndpoint, requiredFields, componentName]);

  if (loading) {
    return <span className="badge badge-info">⏳ Loading...</span>;
  }

  if (error) {
    return <span className="badge badge-warning">⚠️ Data check failed</span>;
  }

  if (completeness === null) {
    return null;
  }

  let colorClass = 'badge-success';
  let icon = '✓';

  if (completeness < 80) {
    colorClass = 'badge-warning';
    icon = '⚠️';
  }
  if (completeness < 50) {
    colorClass = 'badge-danger';
    icon = '❌';
  }

  return (
    <span
      className={`badge ${colorClass} data-quality-badge`}
      title={`${completeness}% of records have complete data`}
    >
      {icon} Data Quality: {completeness}%
    </span>
  );
};

export default DataQualityBadge;
