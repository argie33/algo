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

function PasswordField({ id, name, label, value, show, onToggle, onChange, disabled, placeholder, hint }) {
  return (
    <div className="field-group" style={{ marginBottom: "var(--space-4)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <label className="field-label" htmlFor={id}>{label}</label>
        {hint && <span style={{ fontSize: "var(--t-2xs)", color: "var(--text-faint)" }}>{hint}</span>}
      </div>
      <div style={{ position: "relative" }}>
        <input
          className="input"
          id={id}
          name={name}
          type={show ? "text" : "password"}
          value={value}
          onChange={onChange}
          autoComplete="new-password"
          disabled={disabled}
          placeholder={placeholder}
          style={{ paddingRight: "40px" }}
        />
        <button
          type="button"
          className="btn btn-ghost btn-icon"
          onClick={onToggle}
          disabled={disabled}
          aria-label="Toggle password visibility"
          style={{ position: "absolute", right: "6px", top: "50%", transform: "translateY(-50%)", width: "28px", height: "28px" }}
        >
          {show ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
    </div>
  );
}

function RegisterForm({ onSwitchToLogin, onRegistrationSuccess }) {
  const [formData, setFormData] = useState({
    email: "",
    password: "",
    confirmPassword: "",
    firstName: "",
    lastName: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [localError, setLocalError] = useState("");

  const { register, isLoading, error, clearError } = useAuth();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (error) clearError();
    if (localError) setLocalError("");
  };

  const validateForm = () => {
    if (!formData.email || !formData.password) {
      setLocalError("Please fill in all required fields");
      return false;
    }
    if (formData.password !== formData.confirmPassword) {
      setLocalError("Passwords do not match");
      return false;
    }
    if ((formData.password?.length || 0) < 12) {
      setLocalError("Password must be at least 12 characters");
      return false;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      setLocalError("Please enter a valid email address");
      return false;
    }
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError("");

    if (!validateForm()) return;

    // Cognito user pool uses email as username (username_attributes = ["email"])
    const result = await register(
      formData.email,
      formData.password,
      formData.email,
      formData.firstName,
      formData.lastName
    );

    if (result.success) {
      onRegistrationSuccess?.(formData.email, result.nextStep);
    } else if (result.error) {
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

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
        <div className="field-group">
          <label className="field-label" htmlFor="firstName">First Name</label>
          <input className="input" id="firstName" name="firstName" type="text" value={formData.firstName} onChange={handleChange} autoComplete="given-name" disabled={isLoading} placeholder="First" />
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="lastName">Last Name</label>
          <input className="input" id="lastName" name="lastName" type="text" value={formData.lastName} onChange={handleChange} autoComplete="family-name" disabled={isLoading} placeholder="Last" />
        </div>
      </div>

      <div className="field-group" style={{ marginBottom: "var(--space-4)" }}>
        <label className="field-label" htmlFor="email">Email Address <span style={{ color: "var(--danger)" }}>*</span></label>
        <input className="input" id="email" name="email" type="email" value={formData.email} onChange={handleChange} autoComplete="email" disabled={isLoading} placeholder="you@example.com" required />
      </div>

      <PasswordField
        id="password" name="password" label="Password" value={formData.password}
        show={showPassword} onToggle={() => setShowPassword(!showPassword)}
        onChange={handleChange} disabled={isLoading}
        placeholder="Min 12 characters" hint="12+ chars"
      />

      <PasswordField
        id="confirmPassword" name="confirmPassword" label="Confirm Password" value={formData.confirmPassword}
        show={showConfirmPassword} onToggle={() => setShowConfirmPassword(!showConfirmPassword)}
        onChange={handleChange} disabled={isLoading}
        placeholder="Re-enter password"
      />

      <button
        type="submit"
        className="btn btn-primary btn-lg w-full"
        disabled={isLoading}
        style={{ marginBottom: "var(--space-5)" }}
      >
        {isLoading ? "Creating account…" : "Create Account"}
      </button>

      <div style={{ borderTop: "1px solid var(--border)", paddingTop: "var(--space-4)", textAlign: "center" }}>
        <span style={{ fontSize: "var(--t-sm)", color: "var(--text-muted)" }}>
          Already have an account?{" "}
          <button
            type="button"
            onClick={onSwitchToLogin}
            disabled={isLoading}
            style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: "var(--t-sm)", color: "var(--brand-2)", fontWeight: "var(--w-semibold)" }}
          >
            Sign in
          </button>
        </span>
      </div>
    </form>
  );
}

export default RegisterForm;
