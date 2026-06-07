import { useState } from "react";

function MFAChallenge({
  challengeType = "SMS_MFA",
  message = "Please enter the verification code sent to your device.",
  onSuccess,
  onCancel,
  onVerify = null,
}) {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!code.trim()) {
      setError("Please enter the verification code");
      return;
    }

    setLoading(true);
    setError("");

    try {
      if (onVerify && typeof onVerify === "function") {
        const result = await onVerify(code);
        if (result?.success) {
          onSuccess({ username: result.username || "user", code, challengeType });
        } else {
          setError(result?.error || "Invalid code. Please try again.");
        }
      } else {
        setError("MFA verification is not configured. Please contact support.");
      }
    } catch (err) {
      console.error('[MFAChallenge] Verification failed:', err?.message || err);
      setError("Verification failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const title = challengeType === "SOFTWARE_TOKEN_MFA" ? "Authenticator App" : "SMS Verification";

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
        <div style={{
          width: "36px", height: "36px",
          borderRadius: "var(--r-sm)",
          background: "var(--brand-tint)",
          border: "1px solid var(--brand-soft)",
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0,
        }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--brand-2)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
        </div>
        <div>
          <div style={{ fontSize: "var(--t-md)", fontWeight: "var(--w-semibold)", color: "var(--text)" }}>{title}</div>
          <div style={{ fontSize: "var(--t-xs)", color: "var(--text-muted)", marginTop: "2px" }}>{message}</div>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: "var(--space-4)" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
          <span style={{ fontSize: "var(--t-sm)" }}>{error}</span>
        </div>
      )}

      <div className="field-group" style={{ marginBottom: "var(--space-5)" }}>
        <label className="field-label" htmlFor="mfa-code">Verification Code</label>
        <input
          className="input"
          id="mfa-code"
          type="text"
          value={code}
          onChange={(e) => { setCode(e.target.value); setError(""); }}
          placeholder="000000"
          maxLength={6}
          autoFocus
          required
          style={{
            textAlign: "center",
            fontSize: "var(--t-2xl)",
            fontFamily: "var(--font-mono)",
            letterSpacing: "0.35em",
            fontWeight: "var(--w-semibold)",
          }}
        />
      </div>

      <div style={{ display: "flex", gap: "var(--space-3)" }}>
        <button
          type="button"
          className="btn btn-outline"
          onClick={onCancel}
          disabled={loading}
          style={{ flex: 1, justifyContent: "center" }}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={loading || !code.trim()}
          style={{ flex: 2, justifyContent: "center" }}
        >
          {loading ? "Verifying…" : "Verify"}
        </button>
      </div>

      <p style={{ fontSize: "var(--t-xs)", color: "var(--text-faint)", textAlign: "center", marginTop: "var(--space-4)" }}>
        Didn&apos;t receive a code? Check your spam folder.
      </p>
    </form>
  );
}

export default MFAChallenge;
