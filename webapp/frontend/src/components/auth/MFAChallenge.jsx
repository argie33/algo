import { useState } from "react";
import {
  Box,
  Typography,
  TextField,
  Button,
  Alert,
  InputAdornment,
} from "@mui/material";
import { Security } from "@mui/icons-material";

function MFAChallenge({
  challengeType = "SMS_MFA",
  message = "Please enter the verification code sent to your device.",
  onSuccess,
  onCancel,
}) {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!code.trim()) {
      setError("Please enter the verification code");
      return;
    }

    setLoading(true);
    setError("");

    try {
      // Simulate MFA validation
      if (code === "123456") {
        onSuccess({
          username: "testuser",
          code: code,
          challengeType: challengeType,
        });
      } else {
        setError("Invalid verification code. Please try again.");
      }
    } catch (err) {
      setError("MFA verification failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const getChallengeTitle = () => {
    switch (challengeType) {
      case "SMS_MFA":
        return "SMS Verification";
      case "SOFTWARE_TOKEN_MFA":
        return "Authenticator App";
      default:
        return "Multi-Factor Authentication";
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" alignItems="center" mb={2}>
        <Security sx={{ mr: 1, color: "primary.main" }} />
        <Typography variant="h6" component="h2">
          {getChallengeTitle()}
        </Typography>
      </Box>

      <Typography variant="body2" color="text.secondary" mb={3}>
        {message}
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <form onSubmit={handleSubmit}>
        <TextField
          fullWidth
          label="Verification Code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Enter 6-digit code"
          inputProps={{
            maxLength: 6,
            pattern: "[0-9]{6}",
          }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Security />
              </InputAdornment>
            ),
          }}
          sx={{ mb: 3 }}
          required
        />

        <Box display="flex" gap={2} justifyContent="flex-end">
          <Button variant="outlined" onClick={onCancel} disabled={loading}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={loading || !code.trim()}
          >
            {loading ? "Verifying..." : "Verify"}
          </Button>
        </Box>
      </form>

      <Typography variant="caption" display="block" textAlign="center" mt={2}>
        Didn&apos;t receive a code? Check your spam folder or try again.
      </Typography>
    </Box>
  );
}

export default MFAChallenge;
