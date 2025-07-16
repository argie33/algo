import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Alert,
  CircularProgress,
  Link,
  InputAdornment,
  IconButton,
  Divider,
  Grid
} from '@mui/material';
import { Visibility, VisibilityOff, PersonAdd as RegisterIcon } from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';

function RegisterForm({ onSwitchToLogin, onRegistrationSuccess }) {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    firstName: '',
    lastName: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [localError, setLocalError] = useState('');

  const { register, isLoading, error, clearError } = useAuth();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
    // Clear errors when user starts typing
    if (error) clearError();
    if (localError) setLocalError('');
  };

  const validateForm = () => {
    if (!formData.username || !formData.email || !formData.password) {
      setLocalError('Please fill in all required fields');
      return false;
    }

    if (formData.password !== formData.confirmPassword) {
      setLocalError('Passwords do not match');
      return false;
    }

    if (formData.password.length < 8) {
      setLocalError('Password must be at least 8 characters long');
      return false;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      setLocalError('Please enter a valid email address');
      return false;
    }

    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError('');

    if (!validateForm()) {
      return;
    }

    const result = await register(
      formData.username,
      formData.password,
      formData.email,
      formData.firstName,
      formData.lastName
    );
    
    if (result.success) {
      onRegistrationSuccess?.(formData.username, result.nextStep);
    } else if (result.error) {
      setLocalError(result.error);
    }
  };

  const displayError = error || localError;

  return (
    <Card sx={{ maxWidth: 500, mx: 'auto', mt: 4 }}>
      <CardContent sx={{ p: 4 }}>
        <Box display="flex" alignItems="center" justifyContent="center" mb={3}>
          <RegisterIcon sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="h4" component="h1" color="primary">
            Sign Up
          </Typography>
        </Box>

        <Typography variant="body1" color="text.secondary" align="center" mb={3}>
          Create your Financial Dashboard account
        </Typography>

        {displayError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {displayError}
          </Alert>
        )}

        <Box component="form" onSubmit={handleSubmit} noValidate>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                id="firstName"
                name="firstName"
                label="First Name"
                value={formData.firstName}
                onChange={handleChange}
                autoComplete="given-name"
                disabled={isLoading}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                id="lastName"
                name="lastName"
                label="Last Name"
                value={formData.lastName}
                onChange={handleChange}
                autoComplete="family-name"
                disabled={isLoading}
              />
            </Grid>
          </Grid>

          <TextField
            fullWidth
            id="username"
            name="username"
            label="Username"
            value={formData.username}
            onChange={handleChange}
            margin="normal"
            required
            autoComplete="username"
            disabled={isLoading}
            helperText="This will be your unique identifier for signing in"
          />

          <TextField
            fullWidth
            id="email"
            name="email"
            label="Email Address"
            type="email"
            value={formData.email}
            onChange={handleChange}
            margin="normal"
            required
            autoComplete="email"
            disabled={isLoading}
            helperText="We'll send verification instructions to this email"
          />

          <TextField
            fullWidth
            id="password"
            name="password"
            label="Password"
            type={showPassword ? 'text' : 'password'}
            value={formData.password}
            onChange={handleChange}
            margin="normal"
            required
            autoComplete="new-password"
            disabled={isLoading}
            helperText="Must be at least 8 characters long"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    aria-label="toggle password visibility"
                    onClick={() => setShowPassword(!showPassword)}
                    edge="end"
                    disabled={isLoading}
                  >
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              )
            }}
          />

          <TextField
            fullWidth
            id="confirmPassword"
            name="confirmPassword"
            label="Confirm Password"
            type={showConfirmPassword ? 'text' : 'password'}
            value={formData.confirmPassword}
            onChange={handleChange}
            margin="normal"
            required
            autoComplete="new-password"
            disabled={isLoading}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    aria-label="toggle confirm password visibility"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    edge="end"
                    disabled={isLoading}
                  >
                    {showConfirmPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              )
            }}
          />

          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={isLoading ? <CircularProgress size={20} /> : <RegisterIcon />}
          >
            {isLoading ? 'Creating Account...' : 'Create Account'}
          </Button>

          <Divider sx={{ my: 2 }} />

          <Box textAlign="center">
            <Typography variant="body2" color="text.secondary">
              Already have an account?{' '}
              <Link
                component="button"
                type="button"
                variant="body2"
                onClick={onSwitchToLogin}
                disabled={isLoading}
                sx={{ fontWeight: 'medium' }}
              >
                Sign in here
              </Link>
            </Typography>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

export default RegisterForm;