import { useState } from "react";
import { useAuth } from "../../contexts/AuthContext";

const EyeIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>
);

const EyeOffIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24M1 1l22 22"/>
  </svg>
);

function LoginForm({ onSwitchToRegister, onSwitchToForgotPassword, onMFARequired }) {
  const [formData, setFormData] = useState({ username: "", password: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState("");
  const [rememberMe, setRememberMe] = useState(false);

  const { login, isLoading, error, clearError } = useAuth();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (error) clearError();
    if (localError) setLocalError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError("");

    if (!formData.username || !formData.password) {
      setLocalError("Please enter your email and password");
      return;
    }

    localStorage.setItem("rememberMe", rememberMe.toString());
    const result = await login(formData.username, formData.password);

    if (result.nextStep) {
      onMFARequired?.(result.nextStep);
      return;
    }

    if (!result.success && result.error) {
      setLocalError(result.error);
    }
  };

  const displayError = error || localError;

  return (
    <form onSubmit={handleSubmit} noValidate>
      {displayError && (
        <div className="alert alert-danger" style={{ marginBottom: "var(--space-4)" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
          <span style={{ fontSize: "var(--t-sm)" }}>{displayError}</span>
        </div>
      )}

      <div className="field-group" style={{ marginBottom: "var(--space-4)" }}>
        <label className="field-label" htmlFor="username">Email Address</label>
        <input
          className="input"
          id="username"
          name="username"
          type="email"
          value={formData.username}
          onChange={handleChange}
          autoComplete="email"
          autoFocus
          disabled={isLoading}
          placeholder="you@example.com"
        />
      </div>

      <div className="field-group" style={{ marginBottom: "var(--space-4)" }}>
        <label className="field-label" htmlFor="password">Password</label>
        <div style={{ position: "relative" }}>
          <input
            className="input"
            id="password"
            name="password"
            type={showPassword ? "text" : "password"}
            value={formData.password}
            onChange={handleChange}
            autoComplete="current-password"
            disabled={isLoading}
            placeholder="Enter password"
            style={{ paddingRight: "40px" }}
          />
          <button
            type="button"
            className="btn btn-ghost btn-icon"
            onClick={() => setShowPassword(!showPassword)}
            disabled={isLoading}
            aria-label="Toggle password visibility"
            style={{ position: "absolute", right: "6px", top: "50%", transform: "translateY(-50%)", width: "28px", height: "28px" }}
          >
            {showPassword ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-5)" }}>
        <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={rememberMe}
            onChange={(e) => setRememberMe(e.target.checked)}
            disabled={isLoading}
            style={{ width: "13px", height: "13px", accentColor: "var(--brand)" }}
          />
          <span style={{ fontSize: "var(--t-xs)", color: "var(--text-muted)" }}>Remember me for 30 days</span>
        </label>
        <button
          type="button"
          onClick={onSwitchToForgotPassword}
          disabled={isLoading}
          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: "var(--t-xs)", color: "var(--brand-2)", fontWeight: "var(--w-medium)" }}
        >
          Forgot password?
        </button>
      </div>

      <button
        type="submit"
        className="btn btn-primary btn-lg w-full"
        disabled={isLoading}
        style={{ marginBottom: "var(--space-5)" }}
      >
        {isLoading ? "Signing in…" : "Sign In"}
      </button>

      <div style={{ borderTop: "1px solid var(--border)", paddingTop: "var(--space-4)", textAlign: "center" }}>
        <span style={{ fontSize: "var(--t-sm)", color: "var(--text-muted)" }}>
          Don&apos;t have an account?{" "}
          <button
            type="button"
            onClick={onSwitchToRegister}
            disabled={isLoading}
            style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: "var(--t-sm)", color: "var(--brand-2)", fontWeight: "var(--w-semibold)" }}
          >
            Sign up
          </button>
        </span>
      </div>
    </form>
  );
}

export default LoginForm;