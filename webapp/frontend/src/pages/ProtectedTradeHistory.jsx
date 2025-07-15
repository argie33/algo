import React from 'react';
import ProtectedRoute from '../components/auth/ProtectedRoute';
import TradeHistory from './TradeHistory';

const ProtectedTradeHistory = () => {
  return (
    <ProtectedRoute requireAuth={true} requireApiKeys={true}>
      <TradeHistory />
    </ProtectedRoute>
  );
};

export default ProtectedTradeHistory;