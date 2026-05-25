import { useState } from "react";
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

const TITLES = {
  [AUTH_MODES.LOGIN]: "Sign In",
  [AUTH_MODES.REGISTER]: "Create Account",
  [AUTH_MODES.CONFIRM]: "Verify Account",
  [AUTH_MODES.FORGOT_PASSWORD]: "Reset Password",
  [AUTH_MODES.RESET_PASSWORD]: "Set New Password",
  [AUTH_MODES.MFA_CHALLENGE]: "Two-Factor Auth",
};

function AuthModal({ open, onClose, initialMode = AUTH_MODES.LOGIN, email = "", onSuccess }) {
  const [mode, setMode] = useState(initialMode);
  const [username, setUsername] = useState(email);
  const [successMessage, setSuccessMessage] = useState("");
  const [mfaNextStep, setMfaNextStep] = useState(null);
  const { checkAuthState } = useAuth();

  const handleRegistrationSuccess = (registeredUsername) => {
    setUsername(registeredUsername);
    setSuccessMessage("Check your email for a verification code.");
    setMode(AUTH_MODES.CONFIRM);
  };

  const handleConfirmationSuccess = () => {
    setSuccessMessage("Account verified! You can now sign in.");
    setMode(AUTH_MODES.LOGIN);
  };

  const handleForgotPasswordSuccess = (resetUsername) => {
    setUsername(resetUsername);
    setSuccessMessage("Reset code sent — check your email.");
    setMode(AUTH_MODES.RESET_PASSWORD);
  };

  const handlePasswordResetSuccess = () => {
    setSuccessMessage("Password reset! Sign in with your new password.");
    setMode(AUTH_MODES.LOGIN);
    onSuccess?.();
  };

  const handleMFAVerify = async (code) => {
    try {
      const { isSignedIn } = await confirmSignIn({ challengeResponse: code });
      return { success: isSignedIn, error: isSignedIn ? null : "Verification did not complete sign-in" };
    } catch (err) {
      return { success: false, error: err.message || "Verification failed" };
    }
  };

  const handleMFASuccess = async () => {
    setSuccessMessage("Two-factor authentication successful!");
    await checkAuthState();
    onSuccess?.();
    onClose();
  };

  const handleClose = () => {
    setMode(initialMode);
    setUsername("");
    setSuccessMessage("");
    onClose();
  };

  if (!open) return null;

  return (
    <div className="card animate-in" style={{ padding: 0, overflow: "hidden" }}>
      {/* Header */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "var(--space-4) var(--space-5)",
        borderBottom: "1px solid var(--border)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <div style={{
            width: "32px", height: "32px",
            borderRadius: "var(--r-sm)",
            background: "linear-gradient(135deg, var(--brand) 0%, var(--purple) 100%)",
            boxShadow: "0 2px 10px var(--brand-glow)",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
              <circle cx="12" cy="12" r="10"/>
              <circle cx="12" cy="12" r="6"/>
              <circle cx="12" cy="12" r="2"/>
            </svg>
          </div>
          <div>
            <div style={{ fontSize: "var(--t-md)", fontWeight: "var(--w-semibold)", color: "var(--text)", lineHeight: 1.2 }}>
              {TITLES[mode]}
            </div>
            <div style={{ fontSize: "var(--t-2xs)", color: "var(--text-faint)", marginTop: "2px", letterSpacing: "0.04em" }}>
              Bullseye Trading
            </div>
          </div>
        </div>
        <button
          className="btn btn-ghost btn-icon"
          onClick={handleClose}
          aria-label="Close"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: "var(--space-6)" }}>
        {successMessage && (
          <div className="alert alert-success" style={{ marginBottom: "var(--space-5)" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span style={{ fontSize: "var(--t-sm)" }}>{successMessage}</span>
          </div>
        )}

        {mode === AUTH_MODES.LOGIN && (
          <LoginForm
            onSwitchToRegister={() => { setSuccessMessage(""); setMode(AUTH_MODES.REGISTER); }}
            onSwitchToForgotPassword={() => { setSuccessMessage(""); setMode(AUTH_MODES.FORGOT_PASSWORD); }}
            onMFARequired={(nextStep) => { setMfaNextStep(nextStep); setMode(AUTH_MODES.MFA_CHALLENGE); }}
          />
        )}

        {mode === AUTH_MODES.REGISTER && (
          <RegisterForm
            onSwitchToLogin={() => { setSuccessMessage(""); setMode(AUTH_MODES.LOGIN); }}
            onRegistrationSuccess={handleRegistrationSuccess}
          />
        )}

        {mode === AUTH_MODES.CONFIRM && (
          <ConfirmationForm
            username={username}
            onConfirmationSuccess={handleConfirmationSuccess}
            onSwitchToLogin={() => { setSuccessMessage(""); setMode(AUTH_MODES.LOGIN); }}
          />
        )}

        {mode === AUTH_MODES.FORGOT_PASSWORD && (
          <ForgotPasswordForm
            onBack={() => { setSuccessMessage(""); setMode(AUTH_MODES.LOGIN); }}
            onForgotPasswordSuccess={handleForgotPasswordSuccess}
          />
        )}

        {mode === AUTH_MODES.RESET_PASSWORD && (
          <ResetPasswordForm
            username={username}
            onPasswordResetSuccess={handlePasswordResetSuccess}
            onSwitchToLogin={() => { setSuccessMessage(""); setMode(AUTH_MODES.LOGIN); }}
          />
        )}

        {mode === AUTH_MODES.MFA_CHALLENGE && (
          <MFAChallenge
            challengeType={mfaNextStep?.signInStep === "CONFIRM_SIGN_IN_WITH_TOTP_CODE" ? "SOFTWARE_TOKEN_MFA" : "SMS_MFA"}
            message="Enter the verification code sent to your device."
            onVerify={handleMFAVerify}
            onSuccess={handleMFASuccess}
            onCancel={() => setMode(AUTH_MODES.LOGIN)}
          />
        )}
      </div>
    </div>
  );
}

export default AuthModal;
