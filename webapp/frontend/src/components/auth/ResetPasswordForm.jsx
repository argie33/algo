import { useState } from "react";
import { useAuth } from "../../contexts/AuthContext";

const EyeIcon = () => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
  >
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const EyeOffIcon = () => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
  >
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24M1 1l22 22" />
  </svg>
);

function ResetPasswordForm({
  username,
  onPasswordResetSuccess,
  onSwitchToLogin,
}) {
  const [formData, setFormData] = useState({
    confirmationCode: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [localError, setLocalError] = useState("");

  const { confirmForgotPassword, isLoading, error, clearError } = useAuth();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (error) clearError();
    if (localError) setLocalError("");
  };

  const validateForm = () => {
    if (
      !formData.confirmationCode ||
      !formData.newPassword ||
      !formData.confirmPassword
    ) {
      setLocalError("Please fill in all fields");
      return false;
    }
    if (formData.newPassword !== formData.confirmPassword) {
      setLocalError("Passwords do not match");
      return false;
    }
    if ((formData.newPassword?.length || 0) < 8) {
      setLocalError("Password must be at least 8 characters");
      return false;
    }
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError("");

    if (!validateForm()) return;

    const result = await confirmForgotPassword(
      username,
      formData.confirmationCode,
      formData.newPassword
    );

    if (result.success) {
      onPasswordResetSuccess?.();
    } else if (result.error) {
      setLocalError(result.error);
    }
  };

  const displayError = error || localError;

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div style={{ marginBottom: "var(--space-5)" }}>
        <p
          style={{
            fontSize: "var(--t-sm)",
            color: "var(--text-muted)",
            margin: 0,
          }}
        >
          Enter the code from your email and choose a new password.
        </p>
      </div>

      {displayError && (
        <div
          className="alert alert-danger"
          style={{ marginBottom: "var(--space-4)" }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          <span style={{ fontSize: "var(--t-sm)" }}>{displayError}</span>
        </div>
      )}

      <div className="field-group" style={{ marginBottom: "var(--space-4)" }}>
        <label className="field-label" htmlFor="confirmationCode">
          Reset Code
        </label>
        <input
          className="input"
          id="confirmationCode"
          name="confirmationCode"
          type="text"
          value={formData.confirmationCode}
          onChange={handleChange}
          autoFocus
          disabled={isLoading}
          placeholder="000000"
          maxLength={6}
          style={{
            textAlign: "center",
            fontSize: "var(--t-xl)",
            fontFamily: "var(--font-mono)",
            letterSpacing: "0.3em",
            fontWeight: "var(--w-semibold)",
          }}
        />
      </div>

      <div className="field-group" style={{ marginBottom: "var(--space-4)" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
          }}
        >
          <label className="field-label" htmlFor="newPassword">
            New Password
          </label>
          <span
            style={{ fontSize: "var(--t-2xs)", color: "var(--text-faint)" }}
          >
            8+ chars
          </span>
        </div>
        <div style={{ position: "relative" }}>
          <input
            className="input"
            id="newPassword"
            name="newPassword"
            type={showPassword ? "text" : "password"}
            value={formData.newPassword}
            onChange={handleChange}
            autoComplete="new-password"
            disabled={isLoading}
            placeholder="New password"
            style={{ paddingRight: "40px" }}
          />
          <button
            type="button"
            className="btn btn-ghost btn-icon"
            onClick={() => setShowPassword(!showPassword)}
            disabled={isLoading}
            aria-label="Toggle password visibility"
            style={{
              position: "absolute",
              right: "6px",
              top: "50%",
              transform: "translateY(-50%)",
              width: "28px",
              height: "28px",
            }}
          >
            {showPassword ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        </div>
      </div>

      <div className="field-group" style={{ marginBottom: "var(--space-5)" }}>
        <label className="field-label" htmlFor="confirmPassword">
          Confirm New Password
        </label>
        <div style={{ position: "relative" }}>
          <input
            className="input"
            id="confirmPassword"
            name="confirmPassword"
            type={showConfirmPassword ? "text" : "password"}
            value={formData.confirmPassword}
            onChange={handleChange}
            autoComplete="new-password"
            disabled={isLoading}
            placeholder="Confirm password"
            style={{ paddingRight: "40px" }}
          />
          <button
            type="button"
            className="btn btn-ghost btn-icon"
            onClick={() => setShowConfirmPassword(!showConfirmPassword)}
            disabled={isLoading}
            aria-label="Toggle password visibility"
            style={{
              position: "absolute",
              right: "6px",
              top: "50%",
              transform: "translateY(-50%)",
              width: "28px",
              height: "28px",
            }}
          >
            {showConfirmPassword ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        </div>
      </div>

      <button
        type="submit"
        className="btn btn-primary btn-lg w-full"
        disabled={isLoading}
        style={{ marginBottom: "var(--space-4)" }}
      >
        {isLoading ? "Resetting…" : "Reset Password"}
      </button>

      <div
        style={{
          textAlign: "center",
          paddingTop: "var(--space-4)",
          borderTop: "1px solid var(--border)",
        }}
      >
        <button
          type="button"
          onClick={onSwitchToLogin}
          disabled={isLoading}
          style={{
            background: "none",
            border: "none",
            padding: 0,
            cursor: "pointer",
            fontSize: "var(--t-sm)",
            color: "var(--text-muted)",
          }}
        >
          Back to Sign In
        </button>
      </div>
    </form>
  );
}

export default ResetPasswordForm;
