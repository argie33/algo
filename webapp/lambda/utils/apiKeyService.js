const { CognitoJwtVerifier } = require("aws-jwt-verify");

/**
 * Cognito JWT Validator
 * Validates AWS Cognito access tokens and extracts user info + roles
 */

let verifier = null;

function getVerifier() {
  if (!verifier) {
    const userPoolId = process.env.COGNITO_USER_POOL_ID;
    const clientId = process.env.COGNITO_CLIENT_ID;

    if (!userPoolId || !clientId) {
      throw new Error(
        "Cognito environment variables not configured: COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID are required"
      );
    }

    verifier = CognitoJwtVerifier.create({
      userPoolId,
      tokenUse: "access",
      clientId,
    });
  }
  return verifier;
}

/**
 * Validate Cognito JWT token and extract user info + role
 * @param {string} token - JWT access token from Cognito
 * @returns {Promise<{valid: boolean, user?: object, error?: string}>}
 */
async function validateJwtToken(token) {
  try {
    const payload = await getVerifier().verify(token);

    // Extract groups from token and map to role
    const groups = payload["cognito:groups"] || [];
    const role = groups.includes("admin") ? "admin" : "user";

    return {
      valid: true,
      user: {
        sub: payload.sub,
        username:
          payload["cognito:username"] || payload.username || payload.sub,
        email: payload.email || null,
        role,
        groups,
        sessionId: payload.jti,
        tokenExpirationTime: payload.exp,
        tokenIssueTime: payload.iat,
      },
    };
  } catch (err) {
    return {
      valid: false,
      error: err.message,
    };
  }
}

module.exports = {
  validateJwtToken,
};
