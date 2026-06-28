import { useState, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";

function ConfirmationForm({
  username,
  onConfirmationSuccess,
  onSwitchToLogin,
}) {
  const [confirmationCode, setConfirmationCode] = useState("");
  const [localError, setLocalError] = useState("");
  const [resendSuccess, setResendSuccess] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);

  const {
    confirmRegistration,
    resendConfirmationCode,
    isLoading,
    error,
    clearError,
  } = useAuth();

  const handleChange = (e) => {
    setConfirmationCode(e.target.value);
    if (error) clearError();
    if (localError) setLocalError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError("");

    if (!confirmationCode) {
      setLocalError("Please enter the verification code");
      return;
    }

    const result = await confirmRegistration(username, confirmationCode);

    if (result.success) {
      onConfirmationSuccess?.();
    } else if (result.error) {
      setLocalError(result.error);
    }
  };

  useEffect(() => {
    if (resendCooldown > 0) {
      const timer = setTimeout(
        () => setResendCooldown(resendCooldown - 1),
        1000
      );
      return () => clearTimeout(timer);
    }
  }, [resendCooldown]);

  const handleResendCode = async () => {
    setLocalError("");
    setResendSuccess("");
    const result = await resendConfirmationCode(username);
    if (result.success) {
      setResendSuccess(result.message);
      setResendCooldown(60);
    } else {
      setLocalError(result.error);
    }
  };

  const displayError = error || localError;

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div style={{ textAlign: "center", marginBottom: "var(--space-5)" }}>
        <div
          style={{
            width: "48px",
            height: "48px",
            borderRadius: "var(--r-pill)",
            background: "var(--brand-tint)",
            border: "1px solid var(--brand-soft)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto var(--space-3)",
          }}
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--brand-2)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
            <polyline points="22,6 12,13 2,6" />
          </svg>
        </div>
        <p style={{ fontSize: "var(--t-sm)", color: "var(--text-muted)" }}>
          Enter the 6-digit code sent to your email
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

      {resendSuccess && (
        <div
          className="alert alert-success"
          style={{ marginBottom: "var(--space-4)" }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
          <span style={{ fontSize: "var(--t-sm)" }}>{resendSuccess}</span>
        </div>
      )}

      <div className="field-group" style={{ marginBottom: "var(--space-5)" }}>
        <label className="field-label" htmlFor="confirmationCode">
          Verification Code
        </label>
        <input
          className="input"
          id="confirmationCode"
          name="confirmationCode"
          type="text"
          value={confirmationCode}
          onChange={handleChange}
          autoFocus
          disabled={isLoading}
          placeholder="000000"
          maxLength={6}
          style={{
            textAlign: "center",
            fontSize: "var(--t-2xl)",
            fontFamily: "var(--font-mono)",
            letterSpacing: "0.35em",
            fontWeight: "var(--w-semibold)",
          }}
        />
      </div>

      <button
        type="submit"
        className="btn btn-primary btn-lg w-full"
        disabled={isLoading}
        style={{ marginBottom: "var(--space-4)" }}
      >
        {isLoading ? "Verifying…" : "Verify Account"}
      </button>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          paddingTop: "var(--space-4)",
          borderTop: "1px solid var(--border)",
        }}
      >
        <span style={{ fontSize: "var(--t-sm)", color: "var(--text-muted)" }}>
          Didn&apos;t get a code?{" "}
          <button
            type="button"
            onClick={handleResendCode}
            disabled={isLoading || resendCooldown > 0}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              cursor: resendCooldown > 0 ? "default" : "pointer",
              fontSize: "var(--t-sm)",
              color:
                resendCooldown > 0 ? "var(--text-faint)" : "var(--brand-2)",
              fontWeight: "var(--w-semibold)",
            }}
          >
            {resendCooldown > 0 ? `Resend (${resendCooldown}s)` : "Resend"}
          </button>
        </span>
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
          Back to sign in
        </button>
      </div>
    </form>
  );
}

export default ConfirmationForm;
