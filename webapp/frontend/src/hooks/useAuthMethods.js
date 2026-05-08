/**
 * Auth method logic extracted from AuthContext
 * Handles login, signup, password reset, etc.
 * Works with both Cognito and dev auth
 */

import { useCallback } from 'react';
import {
  signIn,
  signUp,
  confirmSignUp,
  resetPassword,
  confirmResetPassword,
} from 'aws-amplify/auth';
import { isCognitoConfigured } from '../config/amplify';
import { tokenManager } from '../services/tokenManager';
import devAuth from '../services/devAuth';
import { getErrorMessage } from '../utils/cognitoErrorHandler';

const forceDevAuth = import.meta.env.VITE_FORCE_DEV_AUTH === 'true';

export const useAuthMethods = (dispatch, AUTH_ACTIONS) => {
  const cognitoConfigured = isCognitoConfigured();

  const login = useCallback(
    async (email, password) => {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });

      try {
        // Try Cognito first if configured
        if (cognitoConfigured && !forceDevAuth && !import.meta.env.DEV) {
          const user = await signIn({ username: email, password });
          const session = await getAuthSession?.();

          if (user && session?.tokens) {
            const tokens = {
              accessToken: session.tokens.accessToken.toString(),
              idToken: session.tokens.idToken?.toString(),
              refreshToken: session.tokens.refreshToken?.toString(),
            };
            tokenManager.setTokens({
              access: tokens.accessToken,
              id: tokens.idToken,
              refresh: tokens.refreshToken,
            });

            dispatch({
              type: AUTH_ACTIONS.LOGIN_SUCCESS,
              payload: { user: { username: user.username, userId: user.userId, email }, tokens },
            });
            return;
          }
        }

        // Fall back to dev auth
        const result = await devAuth.login(email, password);
        if (!result.success) {
          throw new Error(result.error || 'Login failed');
        }

        tokenManager.setToken(result.tokens.accessToken, 'access');
        dispatch({
          type: AUTH_ACTIONS.LOGIN_SUCCESS,
          payload: { user: result.user, tokens: result.tokens },
        });
      } catch (error) {
        const errorMsg = getErrorMessage(error);
        dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: errorMsg });
        throw error;
      }
    },
    [cognitoConfigured, dispatch, AUTH_ACTIONS]
  );

  const signup = useCallback(
    async (email, password, firstName, lastName) => {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });

      try {
        if (cognitoConfigured && !forceDevAuth && !import.meta.env.DEV) {
          await signUp({
            username: email,
            password,
            options: {
              userAttributes: {
                email,
                given_name: firstName,
                family_name: lastName,
              },
            },
          });
          dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: 'Check email for verification code' });
          return;
        }

        const result = await devAuth.signup(email, password, { firstName, lastName });
        if (!result.success) {
          throw new Error(result.error || 'Signup failed');
        }

        dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: 'Signup successful. Please log in.' });
      } catch (error) {
        const errorMsg = getErrorMessage(error);
        dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: errorMsg });
        throw error;
      }
    },
    [cognitoConfigured, dispatch, AUTH_ACTIONS]
  );

  const confirmAccount = useCallback(
    async (email, code) => {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });

      try {
        if (cognitoConfigured && !forceDevAuth && !import.meta.env.DEV) {
          await confirmSignUp({ username: email, confirmationCode: code });
          dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });
          return;
        }

        // Dev auth doesn't require confirmation
        dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });
      } catch (error) {
        const errorMsg = getErrorMessage(error);
        dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMsg });
        throw error;
      }
    },
    [cognitoConfigured, dispatch, AUTH_ACTIONS]
  );

  const forgotPassword = useCallback(
    async (email) => {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });

      try {
        if (cognitoConfigured && !forceDevAuth && !import.meta.env.DEV) {
          await resetPassword({ username: email });
          dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: 'Check email for reset code' });
          return;
        }

        const result = await devAuth.forgotPassword(email);
        if (!result.success) {
          throw new Error(result.error || 'Password reset request failed');
        }

        dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: 'Check email for reset code' });
      } catch (error) {
        const errorMsg = getErrorMessage(error);
        dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMsg });
        throw error;
      }
    },
    [cognitoConfigured, dispatch, AUTH_ACTIONS]
  );

  const resetPasswordConfirm = useCallback(
    async (email, code, newPassword) => {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });

      try {
        if (cognitoConfigured && !forceDevAuth && !import.meta.env.DEV) {
          await confirmResetPassword({
            username: email,
            confirmationCode: code,
            newPassword,
          });
          dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });
          return;
        }

        const result = await devAuth.resetPassword(email, code, newPassword);
        if (!result.success) {
          throw new Error(result.error || 'Password reset failed');
        }

        dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });
      } catch (error) {
        const errorMsg = getErrorMessage(error);
        dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMsg });
        throw error;
      }
    },
    [cognitoConfigured, dispatch, AUTH_ACTIONS]
  );

  return {
    login,
    signup,
    confirmAccount,
    forgotPassword,
    resetPasswordConfirm,
  };
};

export default useAuthMethods;
