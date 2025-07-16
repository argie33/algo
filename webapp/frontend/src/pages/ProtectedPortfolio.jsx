import React from 'react';
import ProtectedRoute from '../components/auth/ProtectedRoute';
import Portfolio from './Portfolio';

const ProtectedPortfolio = () => {
  return (
    <ProtectedRoute requireAuth={true} requireApiKeys={true}>
      <Portfolio />
    </ProtectedRoute>
  );
};

export default ProtectedPortfolio;