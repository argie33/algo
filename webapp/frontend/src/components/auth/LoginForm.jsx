import { useState } from "react";
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
  Checkbox,
  FormControlLabel,
} from "@mui/material";
import {
  Visibility,
  VisibilityOff,
  Login as LoginIcon,
} from "@mui/icons-material";
import { useAuth } from "../../contexts/AuthContext";

function LoginForm({ onSwitchToRegister, onSwitchToForgotPassword }) {
  const [formData, setFormData] = useState({
    username: "",
    password: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState("");
  const [rememberMe, setRememberMe] = useState(false);

  const { login, isLoading, error, clearError } = useAuth();

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

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError("");

    if (!formData.username || !formData.password) {
      setLocalError("Please enter both username and password");
      return;
    }

    // Store remember me preference
    localStorage.setItem("rememberMe", rememberMe.toString());

    const result = await login(formData.username, formData.password);

    if (!result.success && result.error) {
      setLocalError(result.error);
    }
  };

  const displayError = error || localError;

  return (
    <Card sx={{ maxWidth: 400, mx: "auto", mt: 4 }}>
      <CardContent sx={{ p: 4 }}>
        <Box display="flex" alignItems="center" justifyContent="center" mb={3}>
          <LoginIcon sx={{ mr: 1, color: "primary.main" }} />
          <Typography variant="h4" component="h1" color="primary">
            Sign In
          </Typography>
        </Box>

        <Typography
          variant="body1"
          color="text.secondary"
          align="center"
          mb={3}
        >
          Access your Financial Dashboard
        </Typography>

        {displayError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {displayError}
          </Alert>
        )}

        <Box component="form" onSubmit={handleSubmit} noValidate>
          <TextField
            fullWidth
            id="username"
            name="username"
            label="Username or Email"
            type="text"
            value={formData.username}
            onChange={handleChange}
            margin="normal"
            required
            autoComplete="username"
            autoFocus
            disabled={isLoading}
          />

          <TextField
            fullWidth
            id="password"
            name="password"
            label="Password"
            type={showPassword ? "text" : "password"}
            value={formData.password}
            onChange={handleChange}
            margin="normal"
            required
            autoComplete="current-password"
            disabled={isLoading}
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

          <FormControlLabel
            control={
              <Checkbox
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                color="primary"
                disabled={isLoading}
              />
            }
            label="Remember me for 30 days"
            sx={{ mt: 1, mb: 1 }}
          />

          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={
              isLoading ? <CircularProgress size={20} /> : <LoginIcon />
            }
          >
            {isLoading ? "Signing In..." : "Sign In"}
          </Button>

          <Box
            display="flex"
            justifyContent="space-between"
            alignItems="center"
            mt={2}
          >
            <Link
              component="button"
              type="button"
              variant="body2"
              onClick={onSwitchToForgotPassword}
              disabled={isLoading}
            >
              Forgot password?
            </Link>
          </Box>

          <Divider sx={{ my: 2 }} />

          <Box textAlign="center">
            <Typography variant="body2" color="text.secondary">
              Don&apos;t have an account?{" "}
              <Link
                component="button"
                type="button"
                variant="body2"
                onClick={onSwitchToRegister}
                disabled={isLoading}
                sx={{ fontWeight: "medium" }}
              >
                Sign up here
              </Link>
            </Typography>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

export default LoginForm;
