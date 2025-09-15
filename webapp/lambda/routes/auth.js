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
      return res
        .status(400)
        .json({ success: false, error: "Missing credentials" });
    }

    // Check if AWS Cognito is configured
    if (!process.env.COGNITO_CLIENT_ID) {
      console.log("🔧 DEV: Using development auth for login");

      // Development fallback - generate proper JWT tokens for dev/test
      if (
        (username === "devuser" || username === "argeropolos@gmail.com") &&
        password === "password123"
      ) {
        const jwt = require("jsonwebtoken");
        const secret = process.env.JWT_SECRET || "dev-secret-key";

        const userPayload = {
          sub: `dev-user-${Date.now()}`,
          username: username,
          email: username.includes("@") ? username : `${username}@dev.local`,
          "cognito:username": username,
          token_use: "id",
          auth_time: Math.floor(Date.now() / 1000),
          iss: "dev-issuer",
          exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24, // 24 hours
        };

        const accessPayload = {
          ...userPayload,
          token_use: "access",
          scope: "aws.cognito.signin.user.admin",
        };

        return res.json({
          accessToken: jwt.sign(accessPayload, secret, { algorithm: "HS256" }),
          idToken: jwt.sign(userPayload, secret, { algorithm: "HS256" }),
          refreshToken: jwt.sign(
            { ...userPayload, token_use: "refresh" },
            secret,
            { algorithm: "HS256" }
          ),
          expiresIn: 3600,
          tokenType: "Bearer",
        });
      }

      // Invalid credentials
      return res
        .status(401)
        .json({ success: false, error: "Invalid credentials" });
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
      return res.unauthorized("Invalid credentials");
    }

    if (error.name === "UserNotConfirmedException") {
      return res.unauthorized("Account not confirmed");
    }

    return res
      .status(500)
      .json({ success: false, error: "Authentication failed" });
  }
});

// Handle auth challenges (MFA, password reset, etc.)
router.post("/challenge", async (req, res) => {
  try {
    // Check if AWS Cognito is configured
    if (!process.env.COGNITO_CLIENT_ID) {
      console.log("🔧 DEV: Using development auth for challenge");

      // Development fallback - simulate challenge response
      const { challengeName, challengeResponses } = req.body;

      if (
        challengeName === "SMS_MFA" &&
        challengeResponses?.SMS_MFA_CODE === "123456"
      ) {
        const jwt = require("jsonwebtoken");
        const secret = process.env.JWT_SECRET || "dev-secret-key";

        const userPayload = {
          sub: `mfa-user-${Date.now()}`,
          username: "mfa-dev-user",
          email: "mfa-user@dev.local",
          "cognito:username": "mfa-dev-user",
          token_use: "id",
          auth_time: Math.floor(Date.now() / 1000),
          iss: "dev-issuer",
          exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24, // 24 hours
          mfa_verified: true,
        };

        const accessPayload = {
          ...userPayload,
          token_use: "access",
          scope: "aws.cognito.signin.user.admin",
        };

        return res.json({
          accessToken: jwt.sign(accessPayload, secret, { algorithm: "HS256" }),
          idToken: jwt.sign(userPayload, secret, { algorithm: "HS256" }),
          refreshToken: jwt.sign(
            { ...userPayload, token_use: "refresh" },
            secret,
            { algorithm: "HS256" }
          ),
          expiresIn: 3600,
          tokenType: "Bearer",
        });
      }

      return res.status(400).json({
        success: false,
        error: "Invalid challenge response",
        message: "Development mode: use SMS_MFA_CODE = '123456'",
      });
    }

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
    return res.status(400).json({ success: false, error: "Challenge failed" });
  }
});

// User registration
router.post("/register", async (req, res) => {
  try {
    const { username, password, email, firstName, lastName } = req.body;

    if (!username || !password || !email) {
      return res
        .status(400)
        .json({ success: false, error: "Missing required fields" });
    }

    // Check if AWS Cognito is configured
    if (!process.env.COGNITO_CLIENT_ID) {
      console.log("🔧 DEV: Using development auth for registration");

      // Development fallback - simulate successful registration
      return res.json({
        success: true,
        message: "User registered successfully",
        userSub: "mock-user-sub",
        userConfirmed: false,
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
      return res.status(400).json({ success: false, error: "Username exists" });
    }

    if (error.name === "InvalidParameterException") {
      return res
        .status(400)
        .json({ success: false, error: "Invalid parameters" });
    }

    return res
      .status(500)
      .json({ success: false, error: "Registration failed" });
  }
});

// Confirm registration
router.post("/confirm", async (req, res) => {
  try {
    const { username, confirmationCode } = req.body;

    if (!username || !confirmationCode) {
      return res
        .status(400)
        .json({ success: false, error: "Missing parameters" });
    }

    // Check if AWS Cognito is configured
    if (!process.env.COGNITO_CLIENT_ID) {
      console.log("🔧 DEV: Using development auth for confirmation");

      // Development fallback - simulate successful confirmation
      if (confirmationCode === "123456") {
        return res.json({
          success: true,
          message: "Account confirmed successfully",
        });
      } else {
        return res.status(400).json({ success: false, error: "Invalid code" });
      }
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
      return res.status(400).json({ success: false, error: "Invalid code" });
    }

    return res
      .status(400)
      .json({ success: false, error: "Confirmation failed" });
  }
});

// Forgot password
router.post("/forgot-password", async (req, res) => {
  try {
    const { username } = req.body;

    if (!username) {
      return res
        .status(400)
        .json({ success: false, error: "Missing username" });
    }

    // Check if AWS Cognito is configured
    if (!process.env.COGNITO_CLIENT_ID) {
      console.log("🔧 DEV: Using development auth for forgot password");

      // Development fallback - simulate password reset initiated
      return res.json({
        success: true,
        message: "Password reset code sent",
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
    return res
      .status(400)
      .json({ success: false, error: "Password reset failed" });
  }
});

// Confirm forgot password
router.post("/reset-password", async (req, res) => {
  try {
    // Check if AWS Cognito is configured
    if (!process.env.COGNITO_CLIENT_ID) {
      console.log("🔧 DEV: Using development auth for password reset");

      // Development fallback - simulate password reset
      const { username, confirmationCode, newPassword } = req.body;

      if (!username || !confirmationCode || !newPassword) {
        return res
          .status(400)
          .json({ success: false, error: "Missing parameters" });
      }

      if (confirmationCode === "123456") {
        return res.json({
          success: true,
          message: "Password reset successfully",
        });
      } else {
        return res.status(400).json({
          success: false,
          error: "Invalid confirmation code",
          message: "Development mode: use code '123456'",
        });
      }
    }

    const { username, confirmationCode, newPassword } = req.body;

    if (!username || !confirmationCode || !newPassword) {
      return res
        .status(400)
        .json({ success: false, error: "Missing parameters" });
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
    return res
      .status(400)
      .json({ success: false, error: "Password reset failed" });
  }
});

// Route aliases for test compatibility
router.post("/confirm-forgot-password", async (req, res) => {
  // Check if AWS Cognito is configured
  if (!process.env.COGNITO_CLIENT_ID) {
    console.log("🔧 DEV: Using development auth for confirm forgot password");

    // Development fallback - simulate password reset confirmation
    const { username, confirmationCode, newPassword } = req.body;

    if (!username || !confirmationCode || !newPassword) {
      return res
        .status(400)
        .json({ success: false, error: "Missing required parameters" });
    }

    if (confirmationCode === "123456") {
      return res.json({
        success: true,
        message: "Password reset successfully",
      });
    } else {
      return res.status(400).json({
        success: false,
        error: "Invalid confirmation code",
        message: "Development mode: use code '123456'",
      });
    }
  }

  // Alias for reset-password endpoint to match test expectations
  const { username, confirmationCode, newPassword } = req.body;

  if (!username || !confirmationCode || !newPassword) {
    return res
      .status(400)
      .json({ success: false, error: "Missing required parameters" });
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
    res.error(error.message || "Password reset failed", 400);
  }
});

router.post("/respond-to-challenge", async (req, res) => {
  // Check if AWS Cognito is configured
  if (!process.env.COGNITO_CLIENT_ID) {
    console.log("🔧 DEV: Using development auth for respond to challenge");

    // Development fallback - simulate challenge response
    const { challengeName, challengeResponses } = req.body;

    if (
      challengeName === "SMS_MFA" &&
      challengeResponses?.SMS_MFA_CODE === "123456"
    ) {
      const jwt = require("jsonwebtoken");
      const secret = process.env.JWT_SECRET || "dev-secret-key";

      const userPayload = {
        sub: `challenge-user-${Date.now()}`,
        username: "devuser",
        email: "dev@example.com",
        "cognito:username": "devuser",
        token_use: "id",
        auth_time: Math.floor(Date.now() / 1000),
        iss: "dev-issuer",
        exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24, // 24 hours
        challenge_verified: true,
      };

      const accessPayload = {
        ...userPayload,
        token_use: "access",
        scope: "aws.cognito.signin.user.admin",
      };

      return res.json({
        tokens: {
          accessToken: jwt.sign(accessPayload, secret, { algorithm: "HS256" }),
          idToken: jwt.sign(userPayload, secret, { algorithm: "HS256" }),
          refreshToken: jwt.sign(
            { ...userPayload, token_use: "refresh" },
            secret,
            { algorithm: "HS256" }
          ),
        },
        user: {
          username: userPayload.username,
          email: userPayload.email,
        },
      });
    }

    return res.status(400).json({
      success: false,
      error: "Invalid challenge response",
      message: "Development mode: use SMS_MFA_CODE = '123456'",
    });
  }

  // Alias for challenge endpoint to match test expectations
  const { challengeName, session, challengeResponses } = req.body;

  if (!challengeName || !session) {
    return res
      .status(400)
      .json({ success: false, error: "Missing required parameters" });
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
    res.error(error.message || "Challenge response failed", 400);
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
