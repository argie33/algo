import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import {
  Container,
  Typography,
  Card,
  CardContent,
  Button,
  Box,
} from "@mui/material";

const AuthTest = () => {
  const auth = useAuth();
  const [debugInfo, setDebugInfo] = useState([]);

  const addDebugInfo = (message) => {
    const timestamp = new Date().toLocaleTimeString();
    const logMessage = `${timestamp}: ${message}`;
    if (import.meta.env && import.meta.env.DEV) {
      console.log("🔐 AUTH DEBUG:", logMessage);
    }
    setDebugInfo((prev) => [...prev, logMessage]);
  };

  useEffect(() => {
    addDebugInfo("AuthTest component mounted");
    addDebugInfo(
      `Initial auth state: loading=${auth.isLoading}, authenticated=${auth.isAuthenticated}`
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    addDebugInfo(
      `Auth state changed: loading=${auth.isLoading}, authenticated=${auth.isAuthenticated}, user=${auth.user?.username || "none"}`
    );
  }, [auth.isLoading, auth.isAuthenticated, auth.user]);

  const loginWithTestUser = async () => {
    addDebugInfo("Attempting to login with test user...");
    try {
      const result = await auth.login("testuser", "testpass");
      addDebugInfo(`Login result: ${JSON.stringify(result)}`);
    } catch (error) {
      addDebugInfo(`Login error: ${error.message}`);
    }
  };

  const logout = async () => {
    addDebugInfo("Attempting to logout...");
    try {
      await auth.logout();
      addDebugInfo("Logout successful");
    } catch (error) {
      addDebugInfo(`Logout error: ${error.message}`);
    }
  };

  const checkAuthState = async () => {
    addDebugInfo("Manually checking auth state...");
    try {
      await auth.checkAuthState();
      addDebugInfo("Auth state check completed");
    } catch (error) {
      addDebugInfo(`Auth state check error: ${error.message}`);
    }
  };

  return (
    <Container maxWidth="md">
      <Typography variant="h4" gutterBottom>
        Authentication Test Page
      </Typography>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Current Auth State:
          </Typography>
          <Typography>
            Loading: {auth.isLoading ? "⏳ Yes" : "✅ No"}
          </Typography>
          <Typography>
            Authenticated: {auth.isAuthenticated ? "✅ Yes" : "❌ No"}
          </Typography>
          <Typography>
            User: {auth.user ? `✅ ${auth.user.username}` : "❌ None"}
          </Typography>
          <Typography>Error: {auth.error || "❌ None"}</Typography>
          <Typography>
            Tokens: {auth.tokens ? "✅ Present" : "❌ None"}
          </Typography>

          <Box sx={{ mt: 2, display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Button
              onClick={loginWithTestUser}
              variant="contained"
              size="small"
            >
              Login Test User
            </Button>
            <Button onClick={logout} variant="outlined" size="small">
              Logout
            </Button>
            <Button onClick={checkAuthState} variant="outlined" size="small">
              Check Auth State
            </Button>
          </Box>
        </CardContent>
      </Card>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Local Storage Tokens:
          </Typography>
          <Typography>
            accessToken:{" "}
            {localStorage.getItem("accessToken") ? "✅ Present" : "❌ Missing"}
          </Typography>
          <Typography>
            authToken:{" "}
            {localStorage.getItem("authToken") ? "✅ Present" : "❌ Missing"}
          </Typography>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Debug Log ({debugInfo?.length || 0} entries):
          </Typography>
          <Box
            sx={{ maxHeight: 300, overflow: "auto", bgcolor: "grey.50", p: 1 }}
          >
            {(debugInfo || []).map((info, index) => (
              <Typography
                key={index}
                variant="body2"
                sx={{
                  fontFamily: "monospace",
                  marginBottom: "2px",
                  fontSize: "0.75rem",
                }}
              >
                {info}
              </Typography>
            ))}
          </Box>
          <Button
            onClick={() => setDebugInfo([])}
            variant="outlined"
            size="small"
            sx={{ mt: 1 }}
          >
            Clear Log
          </Button>
        </CardContent>
      </Card>
    </Container>
  );
};

export default AuthTest;
