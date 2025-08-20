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
} from "@mui/material";
import { CheckCircle as ConfirmIcon } from "@mui/icons-material";
import { useAuth } from "../../contexts/AuthContext";

function ConfirmationForm({
  username,
  onConfirmationSuccess,
  onSwitchToLogin,
}) {
  const [confirmationCode, setConfirmationCode] = useState("");
  const [localError, setLocalError] = useState("");

  const { confirmRegistration, isLoading, error, clearError } = useAuth();

  const handleChange = (e) => {
    setConfirmationCode(e.target.value);
    // Clear errors when user starts typing
    if (error) clearError();
    if (localError) setLocalError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError("");

    if (!confirmationCode) {
      setLocalError("Please enter the confirmation code");
      return;
    }

    const result = await confirmRegistration(username, confirmationCode);

    if (result.success) {
      onConfirmationSuccess?.();
    } else if (result.error) {
      setLocalError(result.error);
    }
  };

  const displayError = error || localError;

  return (
    <Card sx={{ maxWidth: 400, mx: "auto", mt: 4 }}>
      <CardContent sx={{ p: 4 }}>
        <Box display="flex" alignItems="center" justifyContent="center" mb={3}>
          <ConfirmIcon sx={{ mr: 1, color: "primary.main" }} />
          <Typography variant="h4" component="h1" color="primary">
            Verify Account
          </Typography>
        </Box>

        <Typography
          variant="body1"
          color="text.secondary"
          align="center"
          mb={3}
        >
          Enter the verification code sent to your email address
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
            label="Verification Code"
            type="text"
            value={confirmationCode}
            onChange={handleChange}
            margin="normal"
            required
            autoFocus
            disabled={isLoading}
            placeholder="Enter 6-digit code"
            inputProps={{ maxLength: 6 }}
          />

          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={
              isLoading ? <CircularProgress size={20} /> : <ConfirmIcon />
            }
          >
            {isLoading ? "Verifying..." : "Verify Account"}
          </Button>

          <Box textAlign="center" mt={2}>
            <Typography variant="body2" color="text.secondary">
              Didn't receive the code?{" "}
              <Link
                component="button"
                type="button"
                variant="body2"
                onClick={() => {
                  // TODO: Implement resend code functionality
                  console.log("Resend code for:", username);
                }}
                disabled={isLoading}
                sx={{ fontWeight: "medium" }}
              >
                Resend
              </Link>
            </Typography>

            <Typography variant="body2" color="text.secondary" mt={1}>
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

export default ConfirmationForm;
