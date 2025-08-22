const express = require("express");
const {
  CognitoIdentityProviderClient,
  InitiateAuthCommand,
  RespondToAuthChallengeCommand,
  SignUpCommand,
  ConfirmSignUpCommand,
  ForgotPasswordCommand,
  ConfirmForgotPasswordCommand,
} = require("@aws-sdk/client-cognito-identity-provider");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Initialize Cognito client
const cognitoClient = new CognitoIdentityProviderClient({
  region:
    process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION || "us-east-1",
});

// User login
router.post("/login", async (req, res) => {
  try {
    const { username, password } = req.body;

    if (!username || !password) {
      return res.status(400).json({
        error: "Missing credentials",
        message: "Username and password are required",
      });
    }

    const command = new InitiateAuthCommand({
      AuthFlow: "USER_PASSWORD_AUTH",
      ClientId: process.env.COGNITO_CLIENT_ID,
      AuthParameters: {
        USERNAME: username,
        PASSWORD: password,
      },
    });

    const response = await cognitoClient.send(command);

    if (response.ChallengeName) {
      // Handle auth challenges (MFA, password change, etc.)
      return res.json({
        challenge: response.ChallengeName,
        challengeParameters: response.ChallengeParameters,
        session: response.Session,
      });
    }

    // Successful authentication
    return res.json({
      accessToken: response.AuthenticationResult.AccessToken,
      idToken: response.AuthenticationResult.IdToken,
      refreshToken: response.AuthenticationResult.RefreshToken,
      expiresIn: response.AuthenticationResult.ExpiresIn,
      tokenType: response.AuthenticationResult.TokenType,
    });
  } catch (error) {
    console.error("Login error:", error);

    if (error.name === "NotAuthorizedException") {
      return res.status(401).json({
        error: "Invalid credentials",
        message: "The username or password is incorrect",
      });
    }

    if (error.name === "UserNotConfirmedException") {
      return res.status(401).json({
        error: "Account not confirmed",
        message: "Please confirm your account before signing in",
      });
    }

    return res.status(500).json({
      error: "Authentication failed",
      message: "An error occurred during authentication",
    });
  }
});

// Handle auth challenges (MFA, password reset, etc.)
router.post("/challenge", async (req, res) => {
  try {
    const { challengeName, challengeResponses, session } = req.body;

    const command = new RespondToAuthChallengeCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      ChallengeName: challengeName,
      ChallengeResponses: challengeResponses,
      Session: session,
    });

    const response = await cognitoClient.send(command);

    if (response.ChallengeName) {
      // Another challenge is required
      return res.json({
        challenge: response.ChallengeName,
        challengeParameters: response.ChallengeParameters,
        session: response.Session,
      });
    }

    // Authentication completed
    return res.json({
      accessToken: response.AuthenticationResult.AccessToken,
      idToken: response.AuthenticationResult.IdToken,
      refreshToken: response.AuthenticationResult.RefreshToken,
      expiresIn: response.AuthenticationResult.ExpiresIn,
      tokenType: response.AuthenticationResult.TokenType,
    });
  } catch (error) {
    console.error("Challenge response error:", error);
    return res.status(400).json({
      error: "Challenge failed",
      message: "Failed to respond to authentication challenge",
    });
  }
});

// User registration
router.post("/register", async (req, res) => {
  try {
    const { username, password, email, firstName, lastName } = req.body;

    if (!username || !password || !email) {
      return res.status(400).json({
        error: "Missing required fields",
        message: "Username, password, and email are required",
      });
    }

    const command = new SignUpCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
      Password: password,
      UserAttributes: [
        { Name: "email", Value: email },
        ...(firstName ? [{ Name: "given_name", Value: firstName }] : []),
        ...(lastName ? [{ Name: "family_name", Value: lastName }] : []),
      ],
    });

    const response = await cognitoClient.send(command);

    return res.json({
      message: "User registered successfully",
      userSub: response.UserSub,
      codeDeliveryDetails: response.CodeDeliveryDetails,
    });
  } catch (error) {
    console.error("Registration error:", error);

    if (error.name === "UsernameExistsException") {
      return res.status(400).json({
        error: "Username exists",
        message: "A user with this username already exists",
      });
    }

    if (error.name === "InvalidParameterException") {
      return res.status(400).json({
        error: "Invalid parameters",
        message: error.message,
      });
    }

    return res.status(500).json({
      error: "Registration failed",
      message: "An error occurred during registration",
    });
  }
});

// Confirm user registration
router.post("/confirm", async (req, res) => {
  try {
    const { username, confirmationCode } = req.body;

    if (!username || !confirmationCode) {
      return res.status(400).json({
        error: "Missing parameters",
        message: "Username and confirmation code are required",
      });
    }

    const command = new ConfirmSignUpCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
      ConfirmationCode: confirmationCode,
    });

    await cognitoClient.send(command);

    return res.json({
      message: "Account confirmed successfully",
    });
  } catch (error) {
    console.error("Confirmation error:", error);

    if (error.name === "CodeMismatchException") {
      return res.status(400).json({
        error: "Invalid code",
        message: "The confirmation code is incorrect",
      });
    }

    return res.status(400).json({
      error: "Confirmation failed",
      message: "Failed to confirm account",
    });
  }
});

// Forgot password
router.post("/forgot-password", async (req, res) => {
  try {
    const { username } = req.body;

    if (!username) {
      return res.status(400).json({
        error: "Missing username",
        message: "Username is required",
      });
    }

    const command = new ForgotPasswordCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
    });

    const response = await cognitoClient.send(command);

    return res.json({
      message: "Password reset code sent",
      codeDeliveryDetails: response.CodeDeliveryDetails,
    });
  } catch (error) {
    console.error("Forgot password error:", error);
    return res.status(400).json({
      error: "Password reset failed",
      message: "Failed to initiate password reset",
    });
  }
});

// Confirm forgot password
router.post("/reset-password", async (req, res) => {
  try {
    const { username, confirmationCode, newPassword } = req.body;

    if (!username || !confirmationCode || !newPassword) {
      return res.status(400).json({
        error: "Missing parameters",
        message: "Username, confirmation code, and new password are required",
      });
    }

    const command = new ConfirmForgotPasswordCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
      ConfirmationCode: confirmationCode,
      Password: newPassword,
    });

    await cognitoClient.send(command);

    return res.json({
      message: "Password reset successfully",
    });
  } catch (error) {
    console.error("Reset password error:", error);
    return res.status(400).json({
      error: "Password reset failed",
      message: "Failed to reset password",
    });
  }
});

// Route aliases for test compatibility
router.post("/confirm-forgot-password", async (req, res) => {
  // Alias for reset-password endpoint to match test expectations
  const { username, confirmationCode, newPassword } = req.body;

  if (!username || !confirmationCode || !newPassword) {
    return res.status(400).json({
      error: "Missing required parameters",
      message: "Username, confirmation code, and new password are required",
    });
  }

  try {
    const command = new ConfirmForgotPasswordCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
      ConfirmationCode: confirmationCode,
      Password: newPassword,
    });

    await cognitoClient.send(command);
    res.json({
      message: "Password reset successfully",
    });
  } catch (error) {
    console.error("Password reset error:", error);
    res.status(400).json({
      error: error.message || "Password reset failed",
    });
  }
});

router.post("/respond-to-challenge", async (req, res) => {
  // Alias for challenge endpoint to match test expectations
  const { challengeName, session, challengeResponses } = req.body;

  if (!challengeName || !session) {
    return res.status(400).json({
      error: "Missing required parameters",
      message: "Challenge name and session are required",
    });
  }

  try {
    const command = new RespondToAuthChallengeCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      ChallengeName: challengeName,
      Session: session,
      ChallengeResponses: challengeResponses || {},
    });

    const response = await cognitoClient.send(command);

    if (response.AuthenticationResult) {
      res.json({
        tokens: {
          accessToken: response.AuthenticationResult.AccessToken,
          idToken: response.AuthenticationResult.IdToken,
          refreshToken: response.AuthenticationResult.RefreshToken,
        },
        user: response.AuthenticationResult.User || {},
      });
    } else if (response.ChallengeName) {
      res.json({
        challenge: response.ChallengeName,
        challengeParameters: response.ChallengeParameters,
        session: response.Session,
      });
    } else {
      res.json({
        message: "Challenge response processed",
      });
    }
  } catch (error) {
    console.error("Challenge response error:", error);
    res.status(400).json({
      error: error.message || "Challenge response failed",
    });
  }
});

// Get current user info (protected route)
router.get("/me", authenticateToken, (req, res) => {
  res.json({
    user: req.user,
  });
});

// Health check for auth service
router.get("/health", (req, res) => {
  res.json({
    status: "healthy",
    service: "Authentication Service",
    timestamp: new Date().toISOString(),
    cognito: {
      userPoolId: process.env.COGNITO_USER_POOL_ID
        ? "configured"
        : "not_configured",
      clientId: process.env.COGNITO_CLIENT_ID ? "configured" : "not_configured",
      region:
        process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION || "us-east-1",
    },
  });
});

module.exports = router;
