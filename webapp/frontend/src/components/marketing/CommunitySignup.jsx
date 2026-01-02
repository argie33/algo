import React, { useState } from 'react';
import {
  Box,
  Container,
  Typography,
  TextField,
  Button,
  useTheme,
  alpha,
  Alert,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { Email as EmailIcon } from '@mui/icons-material';

const CommunitySignup = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!email) {
      setMessage({ type: 'error', text: 'Please enter your email address' });
      return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setMessage({ type: 'error', text: 'Please enter a valid email address' });
      return;
    }

    setIsLoading(true);
    setMessage(null);

    try {
      // TODO: Replace with actual API endpoint when backend is ready
      const response = await fetch('/api/community/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || 'Failed to sign up');
      }

      setMessage({
        type: 'success',
        text: 'Success! Check your email to confirm your subscription.',
      });
      setEmail('');
    } catch (error) {
      setMessage({
        type: 'error',
        text: error.message || 'Failed to sign up. Please try again.',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Box
      sx={{
        py: { xs: 8, md: 10 },
        backgroundColor: alpha(theme.palette.primary.main, 0.08),
        borderTop: `1px solid ${theme.palette.divider}`,
        borderBottom: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Container maxWidth="md">
        <Box sx={{ textAlign: 'center' }}>
          {/* Icon */}
          <Box
            sx={{
              fontSize: '3rem',
              mb: 2,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 64,
              height: 64,
              borderRadius: '50%',
              backgroundColor: alpha(theme.palette.primary.main, 0.1),
              color: theme.palette.primary.main,
            }}
          >
            <EmailIcon sx={{ fontSize: '2rem' }} />
          </Box>

          {/* Headline */}
          <Typography
            variant="h3"
            component="h2"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.8rem' },
              fontWeight: 800,
              mb: 2,
              color: theme.palette.text.primary,
            }}
          >
            Join Our Free Community for Investors
          </Typography>

          {/* Subtitle */}
          <Typography
            variant="body1"
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              mb: 4,
              maxWidth: '600px',
              mx: 'auto',
              lineHeight: 1.8,
            }}
          >
            Receive our weekly newsletter and invitations to upcoming events and appearances featuring our research team and network of experts.
          </Typography>

          {/* Form */}
          <Box
            component="form"
            onSubmit={handleSubmit}
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', sm: 'row' },
              gap: 2,
              maxWidth: '500px',
              mx: 'auto',
              mb: 3,
            }}
          >
            <TextField
              fullWidth
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isLoading}
              sx={{
                '& .MuiOutlinedInput-root': {
                  backgroundColor: theme.palette.background.paper,
                  fontSize: '1rem',
                  '&:hover fieldset': {
                    borderColor: theme.palette.primary.main,
                  },
                },
                '& .MuiOutlinedInput-input::placeholder': {
                  opacity: 0.6,
                },
              }}
            />
            <Button
              type="submit"
              variant="contained"
              size="large"
              disabled={isLoading}
              sx={{
                px: 4,
                py: 1.75,
                fontSize: '1rem',
                fontWeight: 600,
                textTransform: 'none',
                whiteSpace: 'nowrap',
              }}
            >
              {isLoading ? 'Signing Up...' : 'Join Now'}
            </Button>
          </Box>

          {/* Message */}
          {message && (
            <Alert
              severity={message.type}
              sx={{
                maxWidth: '500px',
                mx: 'auto',
                mb: 2,
                backgroundColor: message.type === 'success'
                  ? alpha(theme.palette.success.main, 0.1)
                  : alpha(theme.palette.error.main, 0.1),
              }}
            >
              {message.text}
            </Alert>
          )}

          {/* Legal Text */}
          <Typography
            variant="caption"
            sx={{
              color: theme.palette.text.secondary,
              fontSize: '0.85rem',
              display: 'block',
            }}
          >
            By continuing, you agree to the{' '}
            <Box
              component="span"
              onClick={() => navigate('/terms')}
              sx={{
                color: theme.palette.primary.main,
                cursor: 'pointer',
                textDecoration: 'underline',
                '&:hover': {
                  opacity: 0.8,
                },
              }}
            >
              Terms of Service
            </Box>
            {' '}and{' '}
            <Box
              component="span"
              onClick={() => navigate('/privacy')}
              sx={{
                color: theme.palette.primary.main,
                cursor: 'pointer',
                textDecoration: 'underline',
                '&:hover': {
                  opacity: 0.8,
                },
              }}
            >
              Privacy Policy
            </Box>
          </Typography>
        </Box>
      </Container>
    </Box>
  );
};

export default CommunitySignup;
