import React from 'react';
import ProtectedRoute from '../components/auth/ProtectedRoute';
import Settings from './Settings';

const ProtectedSettings = () => {
  return (
    <ProtectedRoute requireAuth={true} requireApiKeys={false}>
      <Settings />
    </ProtectedRoute>
  );
};

export default ProtectedSettings;