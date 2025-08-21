import React, { useState } from "react";
import {
  Dialog,
  DialogContent,
  Box,
  Typography,
  Button,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Card,
  CardContent,
  Alert,
  Chip,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  LinearProgress,
  IconButton,
  Link,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from "@mui/material";
import {
  Close,
  CheckCircle,
  TrendingUp,
  Security,
  Speed,
  Analytics,
  AccountBalance,
  Api,
  School,
  PlayArrow,
  ExpandMore,
  OpenInNew,
  Star,
} from "@mui/icons-material";
import { useAuth } from "../../contexts/AuthContext";
import api from "../../services/api";

const steps = [
  {
    label: "Welcome",
    title: "Welcome to Your Financial Platform",
    icon: <Star />,
  },
  {
    label: "API Keys Setup",
    title: "Connect Your Brokerage Account",
    icon: <Api />,
  },
  {
    label: "Preferences",
    title: "Customize Your Experience",
    icon: <Security />,
  },
  {
    label: "Features Tour",
    title: "Discover Platform Features",
    icon: <School />,
  },
  {
    label: "Complete",
    title: "You're All Set!",
    icon: <CheckCircle />,
  },
];

const OnboardingWizard = ({ open, onClose, onComplete }) => {
  const [activeStep, setActiveStep] = useState(0);
  const [apiKeys, setApiKeys] = useState({
    alpaca: { key: "", secret: "" },
    polygon: { key: "" },
    finnhub: { key: "" },
  });
  const [preferences, setPreferences] = useState({
    riskTolerance: "moderate",
    investmentStyle: "growth",
    notifications: true,
    autoRefresh: true,
  });
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});

  const { user: _user } = useAuth();

  const handleNext = () => {
    setActiveStep((prevActiveStep) => prevActiveStep + 1);
  };

  const handleBack = () => {
    setActiveStep((prevActiveStep) => prevActiveStep - 1);
  };

  const handleSkip = () => {
    setActiveStep((prevActiveStep) => prevActiveStep + 1);
  };

  const handleApiKeyChange = (provider, field, value) => {
    setApiKeys((prev) => ({
      ...prev,
      [provider]: {
        ...prev[provider],
        [field]: value,
      },
    }));

    // Clear any existing errors
    if (errors[`${provider}_${field}`]) {
      setErrors((prev) => ({
        ...prev,
        [`${provider}_${field}`]: null,
      }));
    }
  };

  const validateApiKeys = () => {
    const newErrors = {};

    // At least one API key should be provided
    const hasAnyKey =
      apiKeys.alpaca.key || apiKeys.polygon.key || apiKeys.finnhub.key;

    if (!hasAnyKey) {
      newErrors.general = "Please provide at least one API key to continue";
    }

    // Validate key formats
    if (apiKeys.alpaca.key && !apiKeys.alpaca.key.startsWith("PK")) {
      newErrors.alpaca_key = 'Alpaca API key should start with "PK"';
    }

    if (apiKeys.alpaca.key && !apiKeys.alpaca.secret) {
      newErrors.alpaca_secret =
        "Alpaca secret is required when key is provided";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const saveApiKeys = async () => {
    if (!validateApiKeys()) return false;

    setLoading(true);
    try {
      const keysToSave = [];

      if (apiKeys.alpaca.key) {
        keysToSave.push({
          provider: "alpaca",
          apiKey: apiKeys.alpaca.key,
          apiSecret: apiKeys.alpaca.secret,
        });
      }

      if (apiKeys.polygon.key) {
        keysToSave.push({
          provider: "polygon",
          apiKey: apiKeys.polygon.key,
        });
      }

      if (apiKeys.finnhub.key) {
        keysToSave.push({
          provider: "finnhub",
          apiKey: apiKeys.finnhub.key,
        });
      }

      // Save each API key
      for (const keyData of keysToSave) {
        await api.post("/api/settings/api-keys", keyData);
      }

      return true;
    } catch (error) {
      console.error("Failed to save API keys:", error);
      setErrors({ general: "Failed to save API keys. Please try again." });
      return false;
    } finally {
      setLoading(false);
    }
  };

  const savePreferences = async () => {
    setLoading(true);
    try {
      await api.post("/api/settings/preferences", preferences);
      return true;
    } catch (error) {
      console.error("Failed to save preferences:", error);
      setErrors({ general: "Failed to save preferences. Please try again." });
      return false;
    } finally {
      setLoading(false);
    }
  };

  const handleStepAction = async () => {
    switch (activeStep) {
      case 1: {
        // API Keys
        const apiSuccess = await saveApiKeys();
        if (apiSuccess) handleNext();
        break;
      }
      case 2: {
        // Preferences
        const prefSuccess = await savePreferences();
        if (prefSuccess) handleNext();
        break;
      }
      case 4: // Complete
        // Mark onboarding as completed
        try {
          await api.post("/api/settings/onboarding-complete");
          if (onComplete) onComplete();
          onClose();
        } catch (error) {
          console.error("Failed to mark onboarding complete:", error);
          if (onComplete) onComplete();
          onClose();
        }
        break;
      default:
        handleNext();
    }
  };

  const WelcomeStep = () => (
    <Box>
      <Typography variant="h6" gutterBottom>
        Welcome to your professional financial analysis platform! 🎉
      </Typography>

      <Typography variant="body1" paragraph>
        This powerful platform provides institutional-grade financial analysis
        tools that were previously only available to hedge funds and investment
        banks.
      </Typography>

      <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
        What you&apos;ll get:
      </Typography>

      <List>
        <ListItem>
          <ListItemIcon>
            <TrendingUp color="primary" />
          </ListItemIcon>
          <ListItemText
            primary="AI-Powered Stock Analysis"
            secondary="Advanced scoring system based on academic research"
          />
        </ListItem>
        <ListItem>
          <ListItemIcon>
            <Analytics color="primary" />
          </ListItemIcon>
          <ListItemText
            primary="Real-time Market Data"
            secondary="Live quotes, technical indicators, and sentiment analysis"
          />
        </ListItem>
        <ListItem>
          <ListItemIcon>
            <AccountBalance color="primary" />
          </ListItemIcon>
          <ListItemText
            primary="Portfolio Management"
            secondary="Track performance with institutional-grade metrics"
          />
        </ListItem>
        <ListItem>
          <ListItemIcon>
            <Security color="primary" />
          </ListItemIcon>
          <ListItemText
            primary="Bank-Level Security"
            secondary="Your data is encrypted and secure"
          />
        </ListItem>
      </List>

      <Alert severity="info" sx={{ mt: 2 }}>
        This setup will take about 5 minutes and will greatly enhance your
        experience.
      </Alert>
    </Box>
  );

  const ApiKeysStep = () => (
    <Box>
      <Typography variant="h6" gutterBottom>
        Connect Your Brokerage Account
      </Typography>

      <Typography variant="body2" color="text.secondary" paragraph>
        To provide personalized analysis and portfolio tracking, we need to
        connect to your brokerage account. Your API keys are encrypted and
        stored securely.
      </Typography>

      {errors.general && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errors.general}
        </Alert>
      )}

      {/* Alpaca Section */}
      <Accordion defaultExpanded>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Box display="flex" alignItems="center" gap={1}>
            <Typography variant="subtitle1">Alpaca Trading</Typography>
            <Chip label="Recommended" color="primary" size="small" />
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary" paragraph>
            Connect to Alpaca for commission-free stock trading and portfolio
            management.
            <Link
              href="https://alpaca.markets/docs/api-documentation/"
              target="_blank"
              sx={{ ml: 1 }}
            >
              Get API Keys <OpenInNew fontSize="small" />
            </Link>
          </Typography>

          <TextField
            fullWidth
            label="API Key"
            value={apiKeys.alpaca.key}
            onChange={(e) =>
              handleApiKeyChange("alpaca", "key", e.target.value)
            }
            error={!!errors.alpaca_key}
            helperText={errors.alpaca_key || 'Starts with "PK"'}
            sx={{ mb: 2 }}
            placeholder="PKTEST_..."
          />

          <TextField
            fullWidth
            label="Secret Key"
            type="password"
            value={apiKeys.alpaca.secret}
            onChange={(e) =>
              handleApiKeyChange("alpaca", "secret", e.target.value)
            }
            error={!!errors.alpaca_secret}
            helperText={errors.alpaca_secret}
            placeholder="Your secret key"
          />
        </AccordionDetails>
      </Accordion>

      {/* Polygon Section */}
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="subtitle1">Polygon.io (Market Data)</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary" paragraph>
            Connect to Polygon for enhanced market data and real-time quotes.
            <Link
              href="https://polygon.io/dashboard/api-keys"
              target="_blank"
              sx={{ ml: 1 }}
            >
              Get API Key <OpenInNew fontSize="small" />
            </Link>
          </Typography>

          <TextField
            fullWidth
            label="API Key"
            value={apiKeys.polygon.key}
            onChange={(e) =>
              handleApiKeyChange("polygon", "key", e.target.value)
            }
            placeholder="Your Polygon API key"
          />
        </AccordionDetails>
      </Accordion>

      {/* Finnhub Section */}
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="subtitle1">Finnhub (Financial Data)</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary" paragraph>
            Connect to Finnhub for comprehensive financial data and news.
            <Link
              href="https://finnhub.io/dashboard"
              target="_blank"
              sx={{ ml: 1 }}
            >
              Get API Key <OpenInNew fontSize="small" />
            </Link>
          </Typography>

          <TextField
            fullWidth
            label="API Key"
            value={apiKeys.finnhub.key}
            onChange={(e) =>
              handleApiKeyChange("finnhub", "key", e.target.value)
            }
            placeholder="Your Finnhub API key"
          />
        </AccordionDetails>
      </Accordion>

      <Alert severity="warning" sx={{ mt: 2 }}>
        <Typography variant="body2">
          <strong>Security Note:</strong> API keys are encrypted using
          bank-level security before storage. We never store them in plain text.
        </Typography>
      </Alert>
    </Box>
  );

  const PreferencesStep = () => (
    <Box>
      <Typography variant="h6" gutterBottom>
        Customize Your Experience
      </Typography>

      <Typography variant="body2" color="text.secondary" paragraph>
        Tell us about your investment preferences to provide personalized
        recommendations.
      </Typography>

      <Box sx={{ mb: 3 }}>
        <FormControl fullWidth>
          <InputLabel>Risk Tolerance</InputLabel>
          <Select
            value={preferences.riskTolerance}
            label="Risk Tolerance"
            onChange={(e) =>
              setPreferences((prev) => ({
                ...prev,
                riskTolerance: e.target.value,
              }))
            }
          >
            <MenuItem value="conservative">
              Conservative - Prefer stable returns
            </MenuItem>
            <MenuItem value="moderate">
              Moderate - Balanced risk/reward
            </MenuItem>
            <MenuItem value="aggressive">
              Aggressive - Higher risk for higher returns
            </MenuItem>
          </Select>
        </FormControl>
      </Box>

      <Box sx={{ mb: 3 }}>
        <FormControl fullWidth>
          <InputLabel>Investment Style</InputLabel>
          <Select
            value={preferences.investmentStyle}
            label="Investment Style"
            onChange={(e) =>
              setPreferences((prev) => ({
                ...prev,
                investmentStyle: e.target.value,
              }))
            }
          >
            <MenuItem value="value">Value - Undervalued stocks</MenuItem>
            <MenuItem value="growth">Growth - High growth potential</MenuItem>
            <MenuItem value="dividend">Dividend - Income focused</MenuItem>
            <MenuItem value="momentum">Momentum - Trending stocks</MenuItem>
          </Select>
        </FormControl>
      </Box>
    </Box>
  );

  const FeaturesTourStep = () => (
    <Box>
      <Typography variant="h6" gutterBottom>
        Discover Platform Features
      </Typography>

      <Typography variant="body2" color="text.secondary" paragraph>
        Here&apos;s what you can do with your new financial platform:
      </Typography>

      <List>
        <ListItem>
          <ListItemIcon>
            <TrendingUp color="primary" />
          </ListItemIcon>
          <ListItemText
            primary="Stock Analysis Dashboard"
            secondary="Comprehensive scoring system analyzing 50+ financial metrics"
          />
        </ListItem>
        <ListItem>
          <ListItemIcon>
            <Analytics color="primary" />
          </ListItemIcon>
          <ListItemText
            primary="Portfolio Optimization"
            secondary="Modern portfolio theory with risk-adjusted returns"
          />
        </ListItem>
        <ListItem>
          <ListItemIcon>
            <Speed color="primary" />
          </ListItemIcon>
          <ListItemText
            primary="Real-time Market Data"
            secondary="Live quotes, technical indicators, and market sentiment"
          />
        </ListItem>
        <ListItem>
          <ListItemIcon>
            <Security color="primary" />
          </ListItemIcon>
          <ListItemText
            primary="AI-Powered Insights"
            secondary="Machine learning models for price predictions and risk assessment"
          />
        </ListItem>
      </List>

      <Card
        sx={{
          mt: 2,
          backgroundColor: "primary.light",
          color: "primary.contrastText",
        }}
      >
        <CardContent>
          <Typography variant="subtitle1" gutterBottom>
            🎯 Pro Tip
          </Typography>
          <Typography variant="body2">
            Start by exploring the Dashboard and Stock Analysis pages. Use the
            search function to analyze your current holdings or stocks
            you&apos;re interested in.
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );

  const CompleteStep = () => (
    <Box textAlign="center">
      <CheckCircle sx={{ fontSize: 80, color: "success.main", mb: 2 }} />

      <Typography variant="h5" gutterBottom>
        Welcome Aboard! 🚀
      </Typography>

      <Typography variant="body1" paragraph>
        You&apos;re all set up and ready to start your journey to smarter
        investing. Your personalized dashboard is waiting for you.
      </Typography>

      <Card sx={{ mt: 3, backgroundColor: "background.default" }}>
        <CardContent>
          <Typography variant="subtitle1" gutterBottom>
            What&apos;s Next?
          </Typography>
          <List dense>
            <ListItem>
              <ListItemIcon>
                <PlayArrow color="primary" />
              </ListItemIcon>
              <ListItemText primary="Explore your personalized dashboard" />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <PlayArrow color="primary" />
              </ListItemIcon>
              <ListItemText primary="Analyze your first stock" />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <PlayArrow color="primary" />
              </ListItemIcon>
              <ListItemText primary="Set up portfolio tracking" />
            </ListItem>
          </List>
        </CardContent>
      </Card>
    </Box>
  );

  const renderStepContent = (step) => {
    switch (step) {
      case 0:
        return <WelcomeStep />;
      case 1:
        return <ApiKeysStep />;
      case 2:
        return <PreferencesStep />;
      case 3:
        return <FeaturesTourStep />;
      case 4:
        return <CompleteStep />;
      default:
        return <WelcomeStep />;
    }
  };

  const getActionLabel = (step) => {
    switch (step) {
      case 0:
        return "Let's Get Started";
      case 1:
        return "Save & Continue";
      case 2:
        return "Save Preferences";
      case 3:
        return "I'm Ready!";
      case 4:
        return "Enter Platform";
      default:
        return "Continue";
    }
  };

  const canSkip = activeStep === 1 || activeStep === 2;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: { borderRadius: 2, minHeight: "600px" },
      }}
    >
      <Box position="absolute" top={8} right={8}>
        <IconButton onClick={onClose} size="small">
          <Close />
        </IconButton>
      </Box>

      <DialogContent sx={{ p: 4 }}>
        <Box mb={3}>
          <Typography variant="h4" gutterBottom textAlign="center">
            {steps[activeStep].title}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={(activeStep / (steps.length - 1)) * 100}
            sx={{ height: 6, borderRadius: 3 }}
          />
        </Box>

        <Stepper activeStep={activeStep} orientation="vertical">
          {steps.map((step, index) => (
            <Step key={step.label}>
              <StepLabel
                icon={step.icon}
                optional={
                  index === activeStep ? (
                    <Typography variant="caption">
                      Step {index + 1} of {steps.length}
                    </Typography>
                  ) : null
                }
              >
                {step.label}
              </StepLabel>
              <StepContent>
                {renderStepContent(index)}

                <Box sx={{ mb: 2, mt: 3 }}>
                  <Button
                    variant="contained"
                    onClick={handleStepAction}
                    disabled={loading}
                    sx={{ mr: 1 }}
                  >
                    {loading ? "Saving..." : getActionLabel(index)}
                  </Button>

                  {activeStep > 0 && (
                    <Button onClick={handleBack} sx={{ mr: 1 }}>
                      Back
                    </Button>
                  )}

                  {canSkip && (
                    <Button onClick={handleSkip} color="inherit">
                      Skip for now
                    </Button>
                  )}
                </Box>
              </StepContent>
            </Step>
          ))}
        </Stepper>
      </DialogContent>
    </Dialog>
  );
};

export default OnboardingWizard;
