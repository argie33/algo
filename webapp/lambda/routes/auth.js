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
      return res.error("Missing credentials", 400);
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
      return res.success({
        challenge: response.ChallengeName,
        challengeParameters: response.ChallengeParameters,
        session: response.Session,
      });
    }

    // Successful authentication
    return res.success({
      accessToken: response.AuthenticationResult.AccessToken,
      idToken: response.AuthenticationResult.IdToken,
      refreshToken: response.AuthenticationResult.RefreshToken,
      expiresIn: response.AuthenticationResult.ExpiresIn,
      tokenType: response.AuthenticationResult.TokenType,
    });
  } catch (error) {
    console.error("Login error:", error);

    if (error.name === "NotAuthorizedException") {
      return res.unauthorized("Invalid credentials");
    }

    if (error.name === "UserNotConfirmedException") {
      return res.unauthorized("Account not confirmed");
    }

    return res.error("Authentication failed", 500);
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
      return res.success({
        challenge: response.ChallengeName,
        challengeParameters: response.ChallengeParameters,
        session: response.Session,
      });
    }

    // Authentication completed
    return res.success({
      accessToken: response.AuthenticationResult.AccessToken,
      idToken: response.AuthenticationResult.IdToken,
      refreshToken: response.AuthenticationResult.RefreshToken,
      expiresIn: response.AuthenticationResult.ExpiresIn,
      tokenType: response.AuthenticationResult.TokenType,
    });
  } catch (error) {
    console.error("Challenge response error:", error);
    return res.error("Challenge failed", 400);
  }
});

// User registration
router.post("/register", async (req, res) => {
  try {
    const { username, password, email, firstName, lastName } = req.body;

    if (!username || !password || !email) {
      return res.error("Missing required fields", 400);
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

    return res.success({
      message: "User registered successfully",
      userSub: response.UserSub,
      codeDeliveryDetails: response.CodeDeliveryDetails,
    });
  } catch (error) {
    console.error("Registration error:", error);

    if (error.name === "UsernameExistsException") {
      return res.error("Username exists", 400);
    }

    if (error.name === "InvalidParameterException") {
      return res.error("Invalid parameters", 400);
    }

    return res.error("Registration failed", 500);
  }
});

// Confirm user registration
router.post("/confirm", async (req, res) => {
  try {
    const { username, confirmationCode } = req.body;

    if (!username || !confirmationCode) {
      return res.error("Missing parameters", 400);
    }

    const command = new ConfirmSignUpCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
      ConfirmationCode: confirmationCode,
    });

    await cognitoClient.send(command);

    return res.success({
      message: "Account confirmed successfully",
    });
  } catch (error) {
    console.error("Confirmation error:", error);

    if (error.name === "CodeMismatchException") {
      return res.error("Invalid code", 400);
    }

    return res.error("Confirmation failed", 400);
  }
});

// Forgot password
router.post("/forgot-password", async (req, res) => {
  try {
    const { username } = req.body;

    if (!username) {
      return res.error("Missing username", 400);
    }

    const command = new ForgotPasswordCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
    });

    const response = await cognitoClient.send(command);

    return res.success({
      message: "Password reset code sent",
      codeDeliveryDetails: response.CodeDeliveryDetails,
    });
  } catch (error) {
    console.error("Forgot password error:", error);
    return res.error("Password reset failed", 400);
  }
});

// Confirm forgot password
router.post("/reset-password", async (req, res) => {
  try {
    const { username, confirmationCode, newPassword } = req.body;

    if (!username || !confirmationCode || !newPassword) {
      return res.error("Missing parameters", 400);
    }

    const command = new ConfirmForgotPasswordCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
      ConfirmationCode: confirmationCode,
      Password: newPassword,
    });

    await cognitoClient.send(command);

    return res.success({
      message: "Password reset successfully",
    });
  } catch (error) {
    console.error("Reset password error:", error);
    return res.error("Password reset failed", 400);
  }
});

// Route aliases for test compatibility
router.post("/confirm-forgot-password", async (req, res) => {
  // Alias for reset-password endpoint to match test expectations
  const { username, confirmationCode, newPassword } = req.body;

  if (!username || !confirmationCode || !newPassword) {
    return res.error("Missing required parameters", 400);
  }

  try {
    const command = new ConfirmForgotPasswordCommand({
      ClientId: process.env.COGNITO_CLIENT_ID,
      Username: username,
      ConfirmationCode: confirmationCode,
      Password: newPassword,
    });

    await cognitoClient.send(command);
    res.success({
      message: "Password reset successfully",
    });
  } catch (error) {
    console.error("Password reset error:", error);
    res.error(error.message || "Password reset failed", 400);
  }
});

router.post("/respond-to-challenge", async (req, res) => {
  // Alias for challenge endpoint to match test expectations
  const { challengeName, session, challengeResponses } = req.body;

  if (!challengeName || !session) {
    return res.error("Missing required parameters", 400);
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
      res.success({
        tokens: {
          accessToken: response.AuthenticationResult.AccessToken,
          idToken: response.AuthenticationResult.IdToken,
          refreshToken: response.AuthenticationResult.RefreshToken,
        },
        user: response.AuthenticationResult.User || {},
      });
    } else if (response.ChallengeName) {
      res.success({
        challenge: response.ChallengeName,
        challengeParameters: response.ChallengeParameters,
        session: response.Session,
      });
    } else {
      res.success({
        message: "Challenge response processed",
      });
    }
  } catch (error) {
    console.error("Challenge response error:", error);
    res.error(error.message || "Challenge response failed", 400);
  }
});

// Get current user info (protected route)
router.get("/me", authenticateToken, (req, res) => {
  res.success({
    user: req.user,
  });
});

// Health check for auth service
router.get("/health", (req, res) => {
  res.success({
    status: "healthy",
    service: "Authentication Service",
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
