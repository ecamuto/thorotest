// ThoroTest — login page

function LoginPage({ onLogin, oauthError, onDismissOAuthError }) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(null);
  // mode: "login" | "forgot" | "forgot-sent" | "reset"
  const resetToken = (window.location.hash.match(/^#\/reset-password\/(.+)$/) || [])[1] || null;
  const [mode, setMode] = useState(resetToken ? "reset" : "login");
  const [newPassword, setNewPassword] = useState("");
  const [resetDone, setResetDone] = useState(false);
  // Demo instances (DEMO_MODE) advertise seeded throwaway logins so visitors
  // can sign in; empty on a normal deploy.
  const [demoAccounts, setDemoAccounts] = useState([]);

  useEffect(() => {
    fetch("/api/config")
      .then(r => (r.ok ? r.json() : {}))
      .then(c => setDemoAccounts(Array.isArray(c.demo_accounts) ? c.demo_accounts : []))
      .catch(() => {});
  }, []);

  const fillDemo = (acct) => {
    setEmail(acct.email);
    setPassword(acct.password);
    setError(null);
  };

  const handleForgot = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await window.TH_API.forgotPassword(email);
      setMode("forgot-sent");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await window.TH_API.resetPassword(resetToken, newPassword);
      window.location.hash = "";
      setMode("login");
      setResetDone(true);
      setPassword("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const user = await window.TH_API.login(email, password);
      onLogin(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark" style={{ width: 36, height: 36, fontSize: 18 }}>T</div>
          <div>
            <div className="brand-name" style={{ fontSize: 18, fontWeight: 700 }}>ThoroTest</div>
            <div className="brand-workspace" style={{ fontSize: 11 }}>Test management</div>
          </div>
        </div>

        <h2 className="login-title">{t("login.title")}</h2>

        {oauthError && (
          <div className="login-error" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <span>
              {oauthError.kind === "cancelled"
                ? `${oauthError.provider ? oauthError.provider.charAt(0).toUpperCase() + oauthError.provider.slice(1) : "OAuth"} sign-in was cancelled.`
                : "Sign-in failed, please try again."}
            </span>
            <button
              type="button"
              onClick={onDismissOAuthError}
              style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", padding: "0 0 0 8px", fontSize: 16, lineHeight: 1 }}
              aria-label="Dismiss"
            >&#x2715;</button>
          </div>
        )}

        {mode === "forgot" && (
          <form onSubmit={handleForgot} className="login-form">
            <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "0 0 12px" }}>
              Enter your account email and we'll send you a password reset link.
            </p>
            <div className="login-field">
              <label className="login-label">{t("login.email")}</label>
              <input className="login-input" type="email" value={email}
                     onChange={e => setEmail(e.target.value)} required autoFocus />
            </div>
            {error && <div className="login-error">{error}</div>}
            <button type="submit" className="btn primary login-btn" disabled={loading}>
              {loading ? "Sending…" : "Send reset link"}
            </button>
            <button type="button" className="btn login-btn" style={{ marginTop: 8, width: "100%" }}
                    onClick={() => { setMode("login"); setError(null); }}>
              Back to sign in
            </button>
          </form>
        )}

        {mode === "forgot-sent" && (
          <div className="login-form">
            <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
              If that email exists, a reset link has been sent. Check your inbox.
            </p>
            <button type="button" className="btn primary login-btn" style={{ width: "100%" }}
                    onClick={() => { setMode("login"); setError(null); }}>
              Back to sign in
            </button>
          </div>
        )}

        {mode === "reset" && (
          <form onSubmit={handleReset} className="login-form">
            <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "0 0 12px" }}>
              Choose a new password for your account.
            </p>
            <div className="login-field">
              <label className="login-label">New password</label>
              <input className="login-input" type="password" value={newPassword}
                     onChange={e => setNewPassword(e.target.value)} minLength={6} required autoFocus />
            </div>
            {error && <div className="login-error">{error}</div>}
            <button type="submit" className="btn primary login-btn" disabled={loading}>
              {loading ? "Saving…" : "Set new password"}
            </button>
          </form>
        )}

        {mode === "login" && (
        <form onSubmit={handleSubmit} className="login-form">
          {resetDone && (
            <div style={{ fontSize: 13, color: "var(--pass, #4ade80)", marginBottom: 12 }}>
              Password updated — sign in with your new password.
            </div>
          )}
          <div className="login-field">
            <label className="login-label">{t("login.email")}</label>
            <input
              className="login-input"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="login-field">
            <label className="login-label">{t("login.password")}</label>
            <input
              className="login-input"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>

          {error && <div className="login-error">{error}</div>}

          <button type="submit" className="btn primary login-btn" disabled={loading}>
            {loading ? t("login.signingIn") : t("login.signIn")}
          </button>
          <button type="button" className="login-forgot-link"
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 12, marginTop: 10, padding: 0 }}
                  onClick={() => { setMode("forgot"); setError(null); }}>
            Forgot password?
          </button>
        </form>
        )}

        {mode === "login" && demoAccounts.length > 0 && (
          <div className="demo-accounts" role="group" aria-label="Demo accounts" style={{
            marginTop: 16, padding: 12, borderRadius: 10,
            border: "1px solid var(--warn, #f59e0b)",
            background: "color-mix(in srgb, var(--warn, #f59e0b) 8%, transparent)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--warn, #f59e0b)" }}>
                Demo accounts
              </span>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>— click to sign in</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {demoAccounts.map(acct => (
                <button
                  key={acct.email}
                  type="button"
                  onClick={() => fillDemo(acct)}
                  title={`Fill ${acct.email}`}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10,
                    padding: "7px 10px", borderRadius: 8, cursor: "pointer",
                    border: "1px solid var(--border, #3f3f5a)", background: "var(--surface, #1e1e2e)",
                    textAlign: "left", width: "100%",
                  }}
                >
                  <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text, #e5e7eb)", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {acct.email}
                    </span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono, monospace)" }}>
                      {acct.password}
                    </span>
                  </span>
                  <span style={{
                    flexShrink: 0, fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
                    padding: "2px 8px", borderRadius: 999,
                    color: acct.role === "admin" ? "#1a1208" : "var(--text, #e5e7eb)",
                    background: acct.role === "admin" ? "var(--warn, #f59e0b)" : "var(--border, #3f3f5a)",
                  }}>
                    {acct.role}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {mode === "login" && (<React.Fragment>
        <div className="login-oauth-buttons">
          <div className="login-divider" style={{ display: "flex", alignItems: "center", gap: 8, margin: "16px 0 12px" }}>
            <div style={{ flex: 1, height: 1, background: "var(--border, #3f3f5a)" }} />
            <span style={{ fontSize: 12, color: "var(--text-muted)", whiteSpace: "nowrap" }}>or continue with</span>
            <div style={{ flex: 1, height: 1, background: "var(--border, #3f3f5a)" }} />
          </div>
          <button
            type="button"
            className="btn login-oauth-btn"
            disabled={oauthLoading === "github"}
            onClick={() => { setOauthLoading("github"); window.location.href = "/api/auth/oauth/github/redirect"; }}
            style={{ width: "100%", marginBottom: 8, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
          >
            {oauthLoading === "github" ? (
              <span style={{ display: "inline-block", width: 14, height: 14, border: "2px solid currentColor", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.6s linear infinite" }} />
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
              </svg>
            )}
            Continue with GitHub
          </button>
          <button
            type="button"
            className="btn login-oauth-btn"
            disabled={oauthLoading === "google"}
            onClick={() => { setOauthLoading("google"); window.location.href = "/api/auth/oauth/google/redirect"; }}
            style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
          >
            {oauthLoading === "google" ? (
              <span style={{ display: "inline-block", width: 14, height: 14, border: "2px solid currentColor", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.6s linear infinite" }} />
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                <path fill="#4285F4" d="M15.68 8.18c0-.57-.05-1.11-.14-1.64H8v3.1h4.3a3.67 3.67 0 01-1.59 2.41v2h2.57c1.51-1.39 2.4-3.44 2.4-5.87z"/>
                <path fill="#34A853" d="M8 16c2.16 0 3.97-.71 5.29-1.94l-2.57-2a4.8 4.8 0 01-7.15-2.52H.96v2.06A8 8 0 008 16z"/>
                <path fill="#FBBC05" d="M3.57 9.54A4.8 4.8 0 013.32 8c0-.54.09-1.06.25-1.54V4.4H.96A8 8 0 000 8c0 1.29.31 2.5.96 3.6l2.61-2.06z"/>
                <path fill="#EA4335" d="M8 3.2a4.34 4.34 0 013.07 1.2l2.3-2.3A7.7 7.7 0 008 0 8 8 0 00.96 4.4l2.61 2.06A4.77 4.77 0 018 3.2z"/>
              </svg>
            )}
            Continue with Google
          </button>
        </div>

        </React.Fragment>)}
      </div>
    </div>
  );
}

window.LoginPage = LoginPage;

function OAuthConfirmScreen({ pendingToken, onLinked, onCancel }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const user = await window.TH_API.confirmOAuthLink(pendingToken, password);
      onLinked(user);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark" style={{ width: 36, height: 36, fontSize: 18 }}>T</div>
          <div>
            <div className="brand-name" style={{ fontSize: 18, fontWeight: 700 }}>ThoroTest</div>
            <div className="brand-workspace" style={{ fontSize: 11 }}>Test management</div>
          </div>
        </div>

        <h2 className="login-title">An account with this email exists.</h2>
        <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
          Enter your existing account password to link this sign-in.
        </p>

        <form onSubmit={submit} className="login-form">
          <div className="login-field">
            <label className="login-label">Password</label>
            <input
              className="login-input"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              autoFocus
            />
          </div>

          {error && <div className="login-error">{error}</div>}

          <button type="submit" className="btn primary login-btn" disabled={loading}>
            {loading ? "Linking…" : "Link account"}
          </button>
        </form>

        <button
          type="button"
          className="btn login-btn"
          style={{ width: "100%", marginTop: 8 }}
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

window.OAuthConfirmScreen = OAuthConfirmScreen;

function TwoFAStep({ partialToken, onVerified, onBack }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const user = await window.TH_API.verify2FA(partialToken, code.trim());
      onVerified(user);
    } catch (err) {
      if (err.httpStatus === 429) {
        const m = err.message.match(/(\d+)s/);
        const secs = m ? parseInt(m[1], 10) : 30;
        setRetryAfter(secs);
        setError(null);
        const iv = setInterval(() => {
          setRetryAfter(prev => {
            if (prev <= 1) { clearInterval(iv); return 0; }
            return prev - 1;
          });
        }, 1000);
      } else {
        setError(err.message || "Invalid code");
      }
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark" style={{ width: 36, height: 36, fontSize: 18 }}>T</div>
          <div>
            <div className="brand-name" style={{ fontSize: 18, fontWeight: 700 }}>ThoroTest</div>
            <div className="brand-workspace" style={{ fontSize: 11 }}>Test management</div>
          </div>
        </div>

        <h2 className="login-title">Two-factor authentication</h2>
        <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
          Enter the 6-digit code from your authenticator app, or a recovery code.
        </p>

        <form onSubmit={submit} className="login-form">
          <div className="login-field">
            <label className="login-label">Code</label>
            <input
              className="login-input"
              type="text"
              value={code}
              onChange={e => setCode(e.target.value)}
              required
              autoFocus
              autoComplete="one-time-code"
              placeholder="000000 or xxxx-xxxx"
            />
          </div>

          {error && <div className="login-error">{error}</div>}
          {retryAfter > 0 && (
            <div className="login-error">Try again in {retryAfter}s</div>
          )}

          <button type="submit" className="btn primary login-btn" disabled={loading || retryAfter > 0}>
            {loading ? "Verifying…" : "Verify"}
          </button>
        </form>

        <button
          type="button"
          className="btn login-btn"
          style={{ width: "100%", marginTop: 8 }}
          onClick={onBack}
        >
          Back
        </button>
      </div>
    </div>
  );
}

window.TwoFAStep = TwoFAStep;
