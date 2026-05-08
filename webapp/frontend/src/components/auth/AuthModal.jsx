import { useState } from "react";
import {
  Dialog,
  DialogContent,
  Box,
  IconButton,
  Typography,
  Alert,
} from "@mui/material";
import { Close } from "@mui/icons-material";
import { confirmSignIn } from "aws-amplify/auth";
import { useAuth } from "../../contexts/AuthContext";
import LoginForm from "./LoginForm";
import RegisterForm from "./RegisterForm";
import ConfirmationForm from "./ConfirmationForm";
import ForgotPasswordForm from "./ForgotPasswordForm";
import ResetPasswordForm from "./ResetPasswordForm";
import MFAChallenge from "./MFAChallenge";

const AUTH_MODES = {
  LOGIN: "login",
  REGISTER: "register",
  CONFIRM: "confirm",
  FORGOT_PASSWORD: "forgot_password",
  RESET_PASSWORD: "reset_password",
  MFA_CHALLENGE: "mfa_challenge",
};

function AuthModal({ open, onClose, initialMode = AUTH_MODES.LOGIN, email = "", onSuccess }) {
  const [mode, setMode] = useState(initialMode);
  const [username, setUsername] = useState(email);
  const [successMessage, setSuccessMessage] = useState("");
  const [mfaNextStep, setMfaNextStep] = useState(null);
  const [pendingUsername, setPendingUsername] = useState("");
  const { checkAuthState } = useAuth();

  const handleRegistrationSuccess = (registeredUsername, _nextStep) => {
    setUsername(registeredUsername);
    setSuccessMessage(
      "Registration successful! Please check your email for a verification code."
    );
    setMode(AUTH_MODES.CONFIRM);
  };

  const handleConfirmationSuccess = () => {
    setSuccessMessage("Account confirmed! You can now sign in.");
    setMode(AUTH_MODES.LOGIN);
  };

  const handleForgotPasswordSuccess = (resetUsername) => {
    setUsername(resetUsername);
    setSuccessMessage("Password reset code sent! Please check your email.");
    setMode(AUTH_MODES.RESET_PASSWORD);
  };

  const handlePasswordResetSuccess = () => {
    setSuccessMessage(
      "Password reset successful! You can now sign in with your new password."
    );
    setMode(AUTH_MODES.LOGIN);
    onSuccess?.();
  };

  const handleMFAVerify = async (code) => {
    try {
      const { isSignedIn } = await confirmSignIn({ challengeResponse: code });
      return {
        success: isSignedIn,
        error: isSignedIn ? null : "Verification did not complete sign-in",
      };
    } catch (err) {
      return { success: false, error: err.message || "Verification failed" };
    }
  };

  const handleMFASuccess = async (_result) => {
    setSuccessMessage("Multi-factor authentication successful!");
    // Fetch the authenticated user and dispatch LOGIN_SUCCESS
    await checkAuthState();
    onSuccess?.();
    onClose();
  };

  const handleMFACancel = () => {
    setMode(AUTH_MODES.LOGIN);
  };

  const handleClose = () => {
    setMode(initialMode);
    setUsername("");
    setSuccessMessage("");
    onClose();
  };

  const getTitle = () => {
    switch (mode) {
      case AUTH_MODES.LOGIN:
        return "Sign In";
      case AUTH_MODES.REGISTER:
        return "Create Account";
      case AUTH_MODES.CONFIRM:
        return "Verify Account";
      case AUTH_MODES.FORGOT_PASSWORD:
        return "Reset Password";
      case AUTH_MODES.RESET_PASSWORD:
        return "Set New Password";
      case AUTH_MODES.MFA_CHALLENGE:
        return "Multi-Factor Authentication";
      default:
        return "Authentication";
    }
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: { borderRadius: 2 },
      }}
    >
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        p={2}
        borderBottom={1}
        borderColor="divider"
      >
        <Typography variant="h6" component="h2">
          {getTitle()}
        </Typography>
        <IconButton onClick={handleClose} size="small" aria-label="close">
          <Close />
        </IconButton>
      </Box>

      <DialogContent sx={{ p: 0 }}>
        {successMessage && (
          <Alert severity="success" sx={{ m: 2, mb: 0 }}>
            {successMessage}
          </Alert>
        )}

        {mode === AUTH_MODES.LOGIN && (
          <LoginForm
            onSwitchToRegister={() => {
              setSuccessMessage("");
              setMode(AUTH_MODES.REGISTER);
            }}
            onSwitchToForgotPassword={() => {
              setSuccessMessage("");
              setMode(AUTH_MODES.FORGOT_PASSWORD);
            }}
            onMFARequired={(nextStep) => {
              setMfaNextStep(nextStep);
              setMode(AUTH_MODES.MFA_CHALLENGE);
            }}
          />
        )}

        {mode === AUTH_MODES.REGISTER && (
          <RegisterForm
            onSwitchToLogin={() => {
              setSuccessMessage("");
              setMode(AUTH_MODES.LOGIN);
            }}
            onRegistrationSuccess={handleRegistrationSuccess}
          />
        )}

        {mode === AUTH_MODES.CONFIRM && (
          <ConfirmationForm
            username={username}
            onConfirmationSuccess={handleConfirmationSuccess}
            onSwitchToLogin={() => {
              setSuccessMessage("");
              setMode(AUTH_MODES.LOGIN);
            }}
          />
        )}

        {mode === AUTH_MODES.FORGOT_PASSWORD && (
          <ForgotPasswordForm
            onBack={() => {
              setSuccessMessage("");
              setMode(AUTH_MODES.LOGIN);
            }}
          />
        )}

        {mode === AUTH_MODES.RESET_PASSWORD && (
          <ResetPasswordForm
            username={username}
            onPasswordResetSuccess={handlePasswordResetSuccess}
            onSwitchToLogin={() => {
              setSuccessMessage("");
              setMode(AUTH_MODES.LOGIN);
            }}
          />
        )}

        {mode === AUTH_MODES.MFA_CHALLENGE && (
          <MFAChallenge
            challengeType={
              mfaNextStep?.signInStep === "CONFIRM_SIGN_IN_WITH_TOTP_CODE"
                ? "SOFTWARE_TOKEN_MFA"
                : "SMS_MFA"
            }
            message="Please enter the verification code sent to your device."
            onVerify={handleMFAVerify}
            onSuccess={handleMFASuccess}
            onCancel={handleMFACancel}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

export default AuthModal;
