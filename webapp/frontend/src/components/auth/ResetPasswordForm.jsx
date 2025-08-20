import React, { useState } from "react";
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
} from "@mui/material";
import {
  Visibility,
  VisibilityOff,
  VpnKey
} from "@mui/icons-material";
import { useAuth } from "../../contexts/AuthContext";

function ResetPasswordForm({
  username,
  onPasswordResetSuccess,
  onSwitchToLogin,
}) {
  const [formData, setFormData] = useState({
    confirmationCode: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [localError, setLocalError] = useState("");

  const { confirmForgotPassword, isLoading, error, clearError } = useAuth();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
    // Clear errors when user starts typing
    if (error) clearError();
    if (localError) setLocalError("");
  };

  const validateForm = () => {
    if (
      !formData.confirmationCode ||
      !formData.newPassword ||
      !formData.confirmPassword
    ) {
      setLocalError("Please fill in all fields");
      return false;
    }

    if (formData.newPassword !== formData.confirmPassword) {
      setLocalError("Passwords do not match");
      return false;
    }

    if (formData.newPassword.length < 8) {
      setLocalError("Password must be at least 8 characters long");
      return false;
    }

    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError("");

    if (!validateForm()) {
      return;
    }

    const result = await confirmForgotPassword(
      username,
      formData.confirmationCode,
      formData.newPassword
    );

    if (result.success) {
      onPasswordResetSuccess?.();
    } else if (result.error) {
      setLocalError(result.error);
    }
  };

  const displayError = error || localError;

  return (
    <Card sx={{ maxWidth: 400, mx: "auto", mt: 4 }}>
      <CardContent sx={{ p: 4 }}>
        <Box display="flex" alignItems="center" justifyContent="center" mb={3}>
          <VpnKey sx={{ mr: 1, color: "primary.main" }} />
          <Typography variant="h4" component="h1" color="primary">
            Set New Password
          </Typography>
        </Box>

        <Typography
          variant="body1"
          color="text.secondary"
          align="center"
          mb={3}
        >
          Enter the code from your email and choose a new password
        </Typography>

        {displayError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {displayError}
          </Alert>
        )}

        <Box component="form" onSubmit={handleSubmit} noValidate>
          <TextField
            fullWidth
            id="confirmationCode"
            name="confirmationCode"
            label="Reset Code"
            type="text"
            value={formData.confirmationCode}
            onChange={handleChange}
            margin="normal"
            required
            autoFocus
            disabled={isLoading}
            placeholder="Enter 6-digit code"
            inputProps={{ maxLength: 6 }}
          />

          <TextField
            fullWidth
            id="newPassword"
            name="newPassword"
            label="New Password"
            type={showPassword ? "text" : "password"}
            value={formData.newPassword}
            onChange={handleChange}
            margin="normal"
            required
            disabled={isLoading}
            autoComplete="new-password"
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
              ),
            }}
          />

          <TextField
            fullWidth
            id="confirmPassword"
            name="confirmPassword"
            label="Confirm New Password"
            type={showConfirmPassword ? "text" : "password"}
            value={formData.confirmPassword}
            onChange={handleChange}
            margin="normal"
            required
            disabled={isLoading}
            autoComplete="new-password"
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
              ),
            }}
          />

          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={
              isLoading ? <CircularProgress size={20} /> : <VpnKey />
            }
          >
            {isLoading ? "Resetting..." : "Reset Password"}
          </Button>

          <Box textAlign="center" mt={2}>
            <Typography variant="body2" color="text.secondary">
              <Link
                component="button"
                type="button"
                variant="body2"
                onClick={onSwitchToLogin}
                disabled={isLoading}
                sx={{ fontWeight: "medium" }}
              >
                Back to Sign In
              </Link>
            </Typography>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

export default ResetPasswordForm;
