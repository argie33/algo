import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import AuthModal from '../components/auth/AuthModal';
import { useAuth } from '../contexts/AuthContext';

function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, user } = useAuth();
  const [authModalOpen, setAuthModalOpen] = useState(true);

  const from = new URLSearchParams(location.search).get('from') || '/app/portfolio';

  useEffect(() => {
    if (isAuthenticated && user) {
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, user, navigate, from]);

  const handleAuthModalClose = () => {
    setAuthModalOpen(false);
    navigate('/', { replace: true });
  };

  const handleAuthSuccess = () => {
    setAuthModalOpen(false);
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      background: 'var(--bg)',
      padding: 'var(--space-5)',
    }}>
      <div style={{ width: '100%', maxWidth: '420px' }}>
        <AuthModal
          open={authModalOpen}
          onClose={handleAuthModalClose}
          initialMode="login"
          onSuccess={handleAuthSuccess}
        />
        <p style={{
          textAlign: 'center',
          fontSize: 'var(--t-2xs)',
          color: 'var(--text-faint)',
          marginTop: 'var(--space-5)',
          letterSpacing: '0.04em',
        }}>
          © {new Date().getFullYear()} Bullseye Trading. All rights reserved.
        </p>
      </div>
    </div>
  );
}

export default LoginPage;
