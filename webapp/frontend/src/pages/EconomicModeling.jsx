/**
 * Economic Modeling Page
 * Placeholder for economic data and modeling
 */

import React from 'react';
import ErrorBoundary from '../components/ErrorBoundary';

function EconomicModelingPage() {
  return (
    <div data-testid="economic-modeling">
      <h1>Economic Modeling</h1>
      <p>Economic data and analysis</p>
    </div>
  );
}

export default function EconomicModeling() {
  return (
    <ErrorBoundary>
      <EconomicModelingPage />
    </ErrorBoundary>
  );
}
