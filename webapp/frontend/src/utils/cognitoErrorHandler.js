/**
 * Cognito error message mapping and formatting
 * Extracted from AuthContext for reusability
 */

const errorMessageMap = {
  'InvalidParameterException': 'Invalid parameters provided',
  'NotAuthorizedException': 'Incorrect username or password',
  'UsernameExistsException': 'Username already exists',
  'InvalidPasswordException': 'Password does not meet requirements',
  'CodeMismatchException': 'Verification code is incorrect',
  'ExpiredCodeException': 'Verification code has expired',
  'LimitExceededException': 'Too many attempts. Please try again later',
  'TooManyRequestsException': 'Too many requests. Please try again later',
  'UserNotFoundException': 'User not found',
  'UserNotConfirmedException': 'User is not confirmed',
};

/**
 * Convert Cognito error to user-friendly message
 * @param {Error} error - Cognito error object
 * @returns {string} user-friendly error message
 */
export const getErrorMessage = (error) => {
  if (!error) return 'An error occurred';

  // Check error code first
  if (error.code) {
    return errorMessageMap[error.code] || error.message || 'An error occurred';
  }

  // Fall back to error message
  if (error.message) {
    // Check if message contains known error code
    for (const [code, message] of Object.entries(errorMessageMap)) {
      if (error.message.includes(code)) {
        return message;
      }
    }
    return error.message;
  }

  return 'An error occurred';
};

export default { getErrorMessage, errorMessageMap };
