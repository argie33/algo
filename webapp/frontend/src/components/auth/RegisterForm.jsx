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
import { useAuth } from '../../contexts/AuthContext';
import PasswordStrengthValidator from './PasswordStrengthValidator';

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
  const [passwordValidation, setPasswordValidation] = useState(null);

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

    // Use advanced password validation
    if (!passwordValidation || !passwordValidation.isValid) {
      setLocalError('Password does not meet security requirements. Please check the requirements below.');
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
    <div className="bg-white shadow-md rounded-lg" sx={{ maxWidth: 500, mx: 'auto', mt: 4 }}>
      <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 4 }}>
        <div  display="flex" alignItems="center" justifyContent="center" mb={3}>
          <RegisterIcon sx={{ mr: 1, color: 'primary.main' }} />
          <div  variant="h4" component="h1" color="primary">
            Sign Up
          </div>
        </div>

        <div  variant="body1" color="text.secondary" align="center" mb={3}>
          Create your Financial Dashboard account
        </div>

        {displayError && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
            {displayError}
          </div>
        )}

        <div  component="form" onSubmit={handleSubmit} noValidate>
          <div className="grid" container spacing={2}>
            <div className="grid" item xs={12} sm={6}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                id="firstName"
                name="firstName"
                label="First Name"
                value={formData.firstName}
                onChange={handleChange}
                autoComplete="given-name"
                disabled={isLoading}
              />
            </div>
            <div className="grid" item xs={12} sm={6}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                id="lastName"
                name="lastName"
                label="Last Name"
                value={formData.lastName}
                onChange={handleChange}
                autoComplete="family-name"
                disabled={isLoading}
              />
            </div>
          </div>

          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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

          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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

          <PasswordStrengthValidator
            value={formData.password}
            onChange={handleChange}
            onValidationChange={setPasswordValidation}
            label="Password"
            placeholder="Create a strong password"
            name="password"
            autoComplete="new-password"
            disabled={isLoading}
            margin="normal"
            required
          />

          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                  <button className="p-2 rounded-full hover:bg-gray-100"
                    aria-label="toggle confirm password visibility"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    edge="end"
                    disabled={isLoading}
                  >
                    {showConfirmPassword ? <VisibilityOff /> : <Visibility />}
                  </button>
                </InputAdornment>
              )
            }}
          />

          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={isLoading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} /> : <RegisterIcon />}
          >
            {isLoading ? 'Creating Account...' : 'Create Account'}
          </button>

          <hr className="border-gray-200" sx={{ my: 2 }} />

          <div  textAlign="center">
            <div  variant="body2" color="text.secondary">
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
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default RegisterForm;