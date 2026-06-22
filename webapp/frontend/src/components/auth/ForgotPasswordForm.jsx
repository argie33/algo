import { useState } from "react";
import { useAuth } from "../../contexts/AuthContext";

const ForgotPasswordForm = ({ onBack, onForgotPasswordSuccess }) => {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const { forgotPassword } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const result = await forgotPassword(email);
      if (result.success) {
        if (onForgotPasswordSuccess) {
          onForgotPasswordSuccess(email);
        } else {
          setMessage(result.message || "Reset code sent. Check your email.");
        }
      } else {
        setError(result.error || "Failed to send reset email.");
      }
    } catch (err) {
      console.error(
        "[ForgotPasswordForm] Reset email send failed:",
        err?.message || err
      );
      setError("Failed to send reset email. Please try again.");
    } finally {
      setLoading(false);
    }
  };

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
          Enter your email address and we&apos;ll send you a reset code.
        </p>
      </div>

      {error && (
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
          <span style={{ fontSize: "var(--t-sm)" }}>{error}</span>
        </div>
      )}

      {message && (
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
          <span style={{ fontSize: "var(--t-sm)" }}>{message}</span>
        </div>
      )}

      <div className="field-group" style={{ marginBottom: "var(--space-5)" }}>
        <label className="field-label" htmlFor="email">
          Email Address
        </label>
        <input
          className="input"
          id="email"
          name="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          autoFocus
          disabled={loading}
          placeholder="you@example.com"
          required
        />
      </div>

      <button
        type="submit"
        className="btn btn-primary btn-lg w-full"
        disabled={loading || !email}
        style={{ marginBottom: "var(--space-3)" }}
      >
        {loading ? "Sending…" : "Send Reset Code"}
      </button>

      <button
        type="button"
        className="btn btn-ghost w-full"
        onClick={onBack}
        disabled={loading}
        style={{ justifyContent: "center" }}
      >
        Back to Sign In
      </button>
    </form>
  );
};

export default ForgotPasswordForm;
