import { useState } from "react";
import {
  Box,
  TextField,
  Button,
  Typography,
  Alert,
  Paper,
} from "@mui/material";
import { useAuth } from "../../contexts/AuthContext";

const ForgotPasswordForm = ({ onBack }) => {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const { forgotPassword } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const result = await forgotPassword(email);
      if (result.success) {
        setMessage(result.message || "Reset code sent to your email");
      } else {
        setError(result.error || "Failed to send password reset email.");
      }
    } catch (err) {
      setError("Failed to send password reset email. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Paper elevation={3} sx={{ p: 4, maxWidth: 400, width: "100%" }}>
      <Typography variant="h4" gutterBottom align="center">
        Reset Password
      </Typography>

      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ mb: 3 }}
        align="center"
      >
        Enter your email address and we&apos;ll send you a password reset link.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {message && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {message}
        </Alert>
      )}

      <Box component="form" onSubmit={handleSubmit} sx={{ mt: 1 }}>
        <TextField
          margin="normal"
          required
          fullWidth
          id="email"
          label="Email Address"
          name="email"
          autoComplete="email"
          autoFocus
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={loading}
        />

        <Button
          type="submit"
          fullWidth
          variant="contained"
          sx={{ mt: 3, mb: 2 }}
          disabled={loading || !email}
        >
          {loading ? "Sending..." : "Send Reset Email"}
        </Button>

        <Button fullWidth variant="text" onClick={onBack} disabled={loading}>
          Back to Sign In
        </Button>
      </Box>
    </Paper>
  );
};

export default ForgotPasswordForm;
