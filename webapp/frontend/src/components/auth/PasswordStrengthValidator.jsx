import React, { useState, useEffect } from 'react';
import {
  Box,
  TextField,
  Typography,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip,
  Alert,
  Collapse,
  IconButton
} from '@mui/material';
import {
  CheckCircle,
  Cancel,
  Visibility,
  VisibilityOff,
  Security,
  Warning,
  Info,
  ExpandMore,
  ExpandLess
} from '@mui/icons-material';
import { green, red, orange, blue } from '@mui/material/colors';

// Password strength calculation and validation
class PasswordValidator {
  constructor() {
    // Common weak passwords and patterns
    this.commonPasswords = [
      'password', '123456', '123456789', 'qwerty', 'abc123', 'password123',
      'admin', 'letmein', 'welcome', 'monkey', 'football', 'iloveyou',
      'princess', 'dragon', 'sunshine', 'master', 'shadow', 'jesus'
    ];
    
    this.weakPatterns = [
      /(.)\1{2,}/, // Repeated characters (aaa, bbb)
      /123|234|345|456|567|678|789|890/, // Sequential numbers
      /abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz/i, // Sequential letters
      /qwerty|asdf|zxcv/i, // Keyboard patterns
    ];
  }

  validatePassword(password) {
    const checks = this.runAllChecks(password);
    const score = this.calculateScore(checks);
    const strength = this.getStrengthLevel(score);
    
    return {
      password,
      score,
      strength,
      checks,
      isValid: checks.length >= 12 && score >= 80,
      suggestions: this.getSuggestions(checks)
    };
  }

  runAllChecks(password) {
    const checks = {
      length: password.length >= 12,
      minLength: password.length >= 8,
      maxLength: password.length <= 128,
      hasUppercase: /[A-Z]/.test(password),
      hasLowercase: /[a-z]/.test(password),
      hasNumbers: /\d/.test(password),
      hasSymbols: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password),
      noCommonPassword: !this.commonPasswords.includes(password.toLowerCase()),
      noWeakPatterns: !this.weakPatterns.some(pattern => pattern.test(password)),
      noPersonalInfo: true, // Would check against user info in real implementation
      hasVariety: this.hasCharacterVariety(password),
      noRepeatingChars: !/(.).*\1.*\1/.test(password),
      strongLength: password.length >= 16,
      hasUnicode: /[^\x00-\x7F]/.test(password),
      entropy: this.calculateEntropy(password) >= 50
    };

    return checks;
  }

  hasCharacterVariety(password) {
    const types = [
      /[a-z]/.test(password), // lowercase
      /[A-Z]/.test(password), // uppercase
      /\d/.test(password),    // numbers
      /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password), // symbols
    ];
    return types.filter(Boolean).length >= 3;
  }

  calculateEntropy(password) {
    const charsetSize = this.getCharsetSize(password);
    return password.length * Math.log2(charsetSize);
  }

  getCharsetSize(password) {
    let size = 0;
    if (/[a-z]/.test(password)) size += 26;
    if (/[A-Z]/.test(password)) size += 26;
    if (/\d/.test(password)) size += 10;
    if (/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password)) size += 32;
    if (/[^\x00-\x7F]/.test(password)) size += 100; // Unicode estimate
    return size;
  }

  calculateScore(checks) {
    const weights = {
      length: 15,
      hasUppercase: 10,
      hasLowercase: 10,
      hasNumbers: 10,
      hasSymbols: 15,
      noCommonPassword: 20,
      noWeakPatterns: 10,
      hasVariety: 5,
      noRepeatingChars: 5,
      strongLength: 10,
      entropy: 15
    };

    let score = 0;
    Object.keys(weights).forEach(check => {
      if (checks[check]) {
        score += weights[check];
      }
    });

    return Math.min(100, score);
  }

  getStrengthLevel(score) {
    if (score >= 90) return { level: 'Excellent', color: green[600] };
    if (score >= 80) return { level: 'Strong', color: green[500] };
    if (score >= 60) return { level: 'Good', color: blue[500] };
    if (score >= 40) return { level: 'Fair', color: orange[500] };
    return { level: 'Weak', color: red[500] };
  }

  getSuggestions(checks) {
    const suggestions = [];
    
    if (!checks.length) {
      suggestions.push('Use at least 12 characters (16+ recommended)');
    }
    if (!checks.hasUppercase) {
      suggestions.push('Add uppercase letters (A-Z)');
    }
    if (!checks.hasLowercase) {
      suggestions.push('Add lowercase letters (a-z)');
    }
    if (!checks.hasNumbers) {
      suggestions.push('Add numbers (0-9)');
    }
    if (!checks.hasSymbols) {
      suggestions.push('Add special characters (!@#$%^&*)');
    }
    if (!checks.noCommonPassword) {
      suggestions.push('Avoid common passwords');
    }
    if (!checks.noWeakPatterns) {
      suggestions.push('Avoid predictable patterns (123, abc, qwerty)');
    }
    if (!checks.noRepeatingChars) {
      suggestions.push('Avoid repeating characters (aaa, 111)');
    }
    if (!checks.entropy) {
      suggestions.push('Increase password complexity and randomness');
    }

    return suggestions;
  }
}

function PasswordStrengthValidator({ 
  value, 
  onChange, 
  onValidationChange,
  label = "Password",
  placeholder = "Enter a strong password",
  showRequirements = true,
  autoFocus = false,
  ...textFieldProps 
}) {
  const [password, setPassword] = useState(value || '');
  const [showPassword, setShowPassword] = useState(false);
  const [validation, setValidation] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const [validator] = useState(new PasswordValidator());

  useEffect(() => {
    if (password) {
      const result = validator.validatePassword(password);
      setValidation(result);
      if (onValidationChange) {
        onValidationChange(result);
      }
    } else {
      setValidation(null);
      if (onValidationChange) {
        onValidationChange(null);
      }
    }
  }, [password, validator, onValidationChange]);

  const handlePasswordChange = (event) => {
    const newPassword = event.target.value;
    setPassword(newPassword);
    if (onChange) {
      onChange(event);
    }
  };

  const getRequirementIcon = (met) => {
    return met ? (
      <CheckCircle sx={{ color: green[600], fontSize: 20 }} />
    ) : (
      <Cancel sx={{ color: red[500], fontSize: 20 }} />
    );
  };

  const getRequirementColor = (met) => {
    return met ? green[600] : red[500];
  };

  const requirements = validation ? [
    { label: 'At least 12 characters', met: validation.checks.length, critical: true },
    { label: 'Uppercase letters (A-Z)', met: validation.checks.hasUppercase, critical: true },
    { label: 'Lowercase letters (a-z)', met: validation.checks.hasLowercase, critical: true },
    { label: 'Numbers (0-9)', met: validation.checks.hasNumbers, critical: true },
    { label: 'Special characters (!@#$%^&*)', met: validation.checks.hasSymbols, critical: true },
    { label: 'Not a common password', met: validation.checks.noCommonPassword, critical: true },
    { label: 'No predictable patterns', met: validation.checks.noWeakPatterns, critical: false },
    { label: 'No repeating characters', met: validation.checks.noRepeatingChars, critical: false },
    { label: '16+ characters (recommended)', met: validation.checks.strongLength, critical: false },
    { label: 'High entropy/randomness', met: validation.checks.entropy, critical: false }
  ] : [];

  const criticalRequirements = requirements.filter(req => req.critical);
  const additionalRequirements = requirements.filter(req => !req.critical);

  return (
    <Box>
      <TextField
        {...textFieldProps}
        fullWidth
        label={label}
        placeholder={placeholder}
        type={showPassword ? 'text' : 'password'}
        value={password}
        onChange={handlePasswordChange}
        autoFocus={autoFocus}
        InputProps={{
          endAdornment: (
            <IconButton
              onClick={() => setShowPassword(!showPassword)}
              edge="end"
              aria-label="toggle password visibility"
            >
              {showPassword ? <VisibilityOff /> : <Visibility />}
            </IconButton>
          ),
        }}
        sx={{ mb: 1 }}
      />

      {validation && (
        <Box sx={{ mb: 2 }}>
          {/* Strength Indicator */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Security sx={{ color: validation.strength.color, fontSize: 20 }} />
            <Typography variant="body2" sx={{ color: validation.strength.color, fontWeight: 600 }}>
              {validation.strength.level}
            </Typography>
            <Chip 
              label={`${validation.score}%`} 
              size="small" 
              sx={{ 
                backgroundColor: validation.strength.color,
                color: 'white',
                fontWeight: 600
              }} 
            />
          </Box>

          {/* Progress Bar */}
          <LinearProgress 
            variant="determinate" 
            value={validation.score} 
            sx={{ 
              height: 8, 
              borderRadius: 4,
              backgroundColor: 'grey.200',
              '& .MuiLinearProgress-bar': {
                backgroundColor: validation.strength.color,
                borderRadius: 4
              }
            }} 
          />

          {/* Quick Status */}
          {validation.score < 80 && (
            <Alert 
              severity={validation.score < 40 ? "error" : "warning"} 
              sx={{ mt: 1, mb: 1 }}
              icon={validation.score < 40 ? <Warning /> : <Info />}
            >
              {validation.score < 40 
                ? "This password is too weak for financial data security"
                : "Consider strengthening your password for better security"
              }
            </Alert>
          )}

          {validation.isValid && (
            <Alert severity="success" sx={{ mt: 1, mb: 1 }}>
              Great! This password meets our security requirements
            </Alert>
          )}
        </Box>
      )}

      {showRequirements && validation && (
        <Box>
          {/* Critical Requirements */}
          <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Security fontSize="small" />
            Security Requirements
          </Typography>
          
          <List dense sx={{ mb: 1 }}>
            {criticalRequirements.map((req, index) => (
              <ListItem key={index} sx={{ py: 0.25 }}>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  {getRequirementIcon(req.met)}
                </ListItemIcon>
                <ListItemText 
                  primary={req.label}
                  sx={{ 
                    '& .MuiListItemText-primary': { 
                      fontSize: '0.875rem',
                      color: getRequirementColor(req.met)
                    }
                  }}
                />
              </ListItem>
            ))}
          </List>

          {/* Additional Requirements (Collapsible) */}
          {additionalRequirements.length > 0 && (
            <Box>
              <Box 
                sx={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  cursor: 'pointer',
                  '&:hover': { backgroundColor: 'action.hover' },
                  borderRadius: 1,
                  p: 0.5
                }}
                onClick={() => setShowDetails(!showDetails)}
              >
                <Typography variant="caption" color="text.secondary">
                  Additional Security Features
                </Typography>
                {showDetails ? <ExpandLess /> : <ExpandMore />}
              </Box>
              
              <Collapse in={showDetails}>
                <List dense>
                  {additionalRequirements.map((req, index) => (
                    <ListItem key={index} sx={{ py: 0.25 }}>
                      <ListItemIcon sx={{ minWidth: 32 }}>
                        {getRequirementIcon(req.met)}
                      </ListItemIcon>
                      <ListItemText 
                        primary={req.label}
                        sx={{ 
                          '& .MuiListItemText-primary': { 
                            fontSize: '0.8rem',
                            color: getRequirementColor(req.met)
                          }
                        }}
                      />
                    </ListItem>
                  ))}
                </List>
              </Collapse>
            </Box>
          )}

          {/* Suggestions */}
          {validation.suggestions.length > 0 && (
            <Alert severity="info" sx={{ mt: 1 }}>
              <Typography variant="body2" gutterBottom>
                Suggestions to improve your password:
              </Typography>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {validation.suggestions.slice(0, 3).map((suggestion, index) => (
                  <li key={index}>
                    <Typography variant="caption">{suggestion}</Typography>
                  </li>
                ))}
              </ul>
            </Alert>
          )}
        </Box>
      )}
    </Box>
  );
}

export default PasswordStrengthValidator;