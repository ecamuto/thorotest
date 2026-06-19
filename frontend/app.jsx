// ThoroTest — main app

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "dark",
  "density": "compact"
}/*EDITMODE-END*/;

function can(user, action) {
  const r = user?.role || "viewer";
  if (action === "write")  return r === "admin" || r === "manager" || r === "tester";
  if (action === "delete") return r === "admin";
  if (action === "admin")  return r === "admin";
  if (action === "manage") return r === "admin" || r === "manager";
  return true; // "read" — all roles
}
window.can = can; // expose for views loaded as separate Babel scripts

function Toast({ msg, severity, onDone }) {
  React.useEffect(() => {
    if (!msg) return;
    const t = setTimeout(onDone, 3000);
    return () => clearTimeout(t);
  }, [msg]);
  if (!msg) return null;
  const isError = severity === "error";
  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, zIndex: 9999,
      background: "var(--card-bg, #1e1e2e)",
      border: `1px solid ${isError ? "var(--fail)" : "var(--border, #3f3f5a)"}`,
      borderLeft: isError ? "4px solid var(--fail)" : undefined,
      borderRadius: 8, padding: "10px 16px", fontSize: 13,
      boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
      color: isError ? "var(--fail)" : "var(--text, #e0e0f0)"
    }}>{msg}</div>
  );
}

function parseHash(hash) {
  const path = (hash || '').replace(/^#\/?/, '');
  const [seg0, seg1] = path.split('/');
  if (seg0 === 'tests' && seg1) return { view: 'test-detail', testId: seg1, runId: null };
  if (seg0 === 'runs' && seg1) return { view: 'run-detail', testId: null, runId: seg1 };
  return { view: seg0 || 'overview', testId: null, runId: null };
}

function buildHash(view, testId, runId) {
  if (view === 'test-detail' && testId) return `#/tests/${testId}`;
  if (view === 'run-detail' && runId) return `#/runs/${runId}`;
  return `#/${view}`;
}

function App({ currentUser: initialUser, onLogout, onProfileUpdate }) {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const initial = parseHash(window.location.hash);
  const safeInitialView = (initial.view === "admin" && initialUser?.role !== "admin") ? "overview" : initial.view;
  const [view, setView] = useState(safeInitialView);
  const [testId, setTestId] = useState(initial.testId);
  const [runId, setRunId] = useState(initial.runId);
  const currentUser = initialUser;
  const [toastMsg, setToastMsg] = React.useState(null);
  const [toastSeverity, setToastSeverity] = React.useState(null);

  // Show toast if initial hash was #/admin but user is not admin
  useEffect(() => {
    if (initial.view === "admin" && initialUser?.role !== "admin") {
      setToastMsg("Admin access required");
      setToastSeverity("error");
    }
  }, []);

  // Apply theme + density to <html>
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", tweaks.theme);
    document.documentElement.setAttribute("data-density", tweaks.density);
  }, [tweaks.theme, tweaks.density]);

  // Sync URL hash when view/id changes
  useEffect(() => {
    const hash = buildHash(view, testId, runId);
    if (window.location.hash !== hash) window.location.hash = hash;
  }, [view, testId, runId]);

  // Sync state from browser back/forward
  useEffect(() => {
    const onHashChange = () => {
      const { view: v, testId: t, runId: r } = parseHash(window.location.hash);
      if (v === "admin" && currentUser?.role !== "admin") {
        window.location.hash = "#/overview";
        setToastMsg("Admin access required");
        setToastSeverity("error");
        setView("overview");
        return;
      }
      setView(v);
      setTestId(t);
      setRunId(r);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, [currentUser]);

  const nav = (id) => {
    if (id === "admin" && currentUser?.role !== "admin") {
      setToastMsg("Admin access required");
      setToastSeverity("error");
      return;
    }
    if (id === "library" && testId) setTestId(null);
    if (id === "runs" && runId) setRunId(null);
    setView(id);
  };

  const openTest = (id) => { setTestId(id); setView("test-detail"); };
  const openRun = (id) => { setRunId(id); setView("run-detail"); };

  const W = { label: "acme/web", href: "#/overview" };
  let crumbs = [W, "Overview"];
  let actions = null;
  let body = null;
  let hideTopbar = false;

  switch (view) {
    case "overview":
      crumbs = [W, "Overview"];
      body = <Overview onNav={nav} currentUser={currentUser} />;
      break;
    case "library":
      crumbs = [W, "Test library"];
      body = <Library onNav={nav} onOpenTest={openTest} currentUser={currentUser} />;
      hideTopbar = true;
      break;
    case "test-detail":
      crumbs = [W, { label: "Test library", href: "#/library" }, testId || "TC-2301"];
      body = <TestDetail testId={testId} onBack={() => setView("library")} currentUser={currentUser} />;
      hideTopbar = true;
      break;
    case "runs":
      crumbs = [W, "Runs & plans"];
      body = <Runs onOpenRun={openRun} currentUser={currentUser} />;
      hideTopbar = true;
      break;
    case "run-detail":
      crumbs = [W, { label: "Runs", href: "#/runs" }, runId || "R-1287"];
      body = <RunDetail runId={runId} onBack={() => setView("runs")} currentUser={currentUser} />;
      hideTopbar = true;
      break;
    case "pipelines":
      crumbs = [W, "CI pipelines"];
      body = <Pipelines currentUser={currentUser} />;
      break;
    case "defects":
      crumbs = [W, "Defects"];
      body = <Defects currentUser={currentUser} />;
      break;
    case "insights":
      crumbs = [W, "Insights"];
      body = <Insights currentUser={currentUser} />;
      break;
    case "ai":
      crumbs = [W, "AI assistant"];
      body = <AIAssistant currentUser={currentUser} currentFolderId={window.__currentFolderId || null} />;
      break;
    case "integrations":
      crumbs = [W, "Integrations"];
      body = <Integrations currentUser={currentUser} />;
      break;
    case "docs":
      crumbs = [W, "Docs & API"];
      body = <Docs currentUser={currentUser} />;
      hideTopbar = true;
      break;
    case "import":
      crumbs = [W, "Import"];
      body = <Import currentUser={currentUser} />;
      break;
    case "settings":
      crumbs = [W, "Settings"];
      body = <Settings currentUser={currentUser} onProfileUpdate={onProfileUpdate} />;
      hideTopbar = true;
      break;
    case "admin":
      crumbs = [W, "User Management"];
      body = <AdminPage currentUser={currentUser} onNav={nav} />;
      hideTopbar = true;
      break;
    case "my-work":
      crumbs = [W, "My work"];
      body = <MyWork currentUser={currentUser} />;
      hideTopbar = true;
      break;
    default:
      body = <Overview onNav={nav} currentUser={currentUser} />;
  }

  return (
    <div className="app" data-screen-label={view}>
      <Sidebar current={view === "test-detail" ? "library" : view === "run-detail" ? "runs" : view} onNav={nav} onOpenTest={openTest} density={tweaks.density} currentUser={currentUser} onLogout={onLogout} />
      <div className="main">
        {!hideTopbar && <Topbar crumbs={crumbs} actions={actions} />}
        <div className="content" style={hideTopbar ? {} : {}}>
          {body}
        </div>
      </div>

      <Toast msg={toastMsg} severity={toastSeverity} onDone={() => { setToastMsg(null); setToastSeverity(null); }} />

      <TweaksPanel title="Tweaks">
        <TweakSection label="Appearance">
          <TweakRadio label="Theme" value={tweaks.theme} onChange={v => setTweak("theme", v)} options={[
            { value: "dark", label: "Dark" },
            { value: "light", label: "Light" },
          ]} />
          <TweakRadio label="Density" value={tweaks.density} onChange={v => setTweak("density", v)} options={[
            { value: "compact", label: "Compact" },
            { value: "comfortable", label: "Comfortable" },
          ]} />
        </TweakSection>
        <TweakSection label="Navigate">
          <TweakButton label="Back to app" onClick={() => setView("overview")} />
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}


const root = ReactDOM.createRoot(document.getElementById("root"));

function AuthRoot() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [pendingOAuth, setPendingOAuth] = useState(null);
  const [pending2FA, setPending2FA] = useState(null);
  const [oauthError, setOauthError] = useState(null);

  useEffect(() => {
    async function checkAuth() {
      // Parse OAuth hash params BEFORE checking auth — clean URL immediately
      const raw = window.location.hash || "";
      const params = new URLSearchParams(raw.replace(/^#\/?/, ""));
      const token = params.get("token");
      const confirm = params.get("oauth-confirm");
      const partialTok = params.get("oauth-2fa");
      const errKind = params.get("oauth-error");
      const errProvider = params.get("provider");

      if (token) {
        window.TH_API.setToken(token);
        window.location.hash = "#/overview";
        // fall through to checkAuth — token is now stored, /api/me will succeed
      } else if (confirm) {
        setPendingOAuth(confirm);
        window.location.hash = "";
        setAuthChecked(true);
        return; // skip checkAuth; show confirm screen
      } else if (partialTok) {
        setPending2FA(partialTok);
        window.location.hash = "";
        setAuthChecked(true);
        return;
      } else if (errKind) {
        setOauthError({ kind: errKind, provider: errProvider });
        window.location.hash = "";
      }

      const user = await window.TH_API.getCurrentUser();
      setCurrentUser(user);
      setAuthChecked(true);
      if (user) {
        window.TH_I18N.setLanguage(user.language || "en");
        if (window.TH_API) await window.TH_API.init();
      }
    }
    checkAuth();
  }, []);

  if (!authChecked) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "var(--bg)" }}>
        <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading…</div>
      </div>
    );
  }

  if (pendingOAuth && !currentUser) {
    return (
      <OAuthConfirmScreen
        pendingToken={pendingOAuth}
        onLinked={async (result) => {
          if (result && result.__2fa_required) {
            setPendingOAuth(null);
            setPending2FA(result.partialToken);
            return;
          }
          setPendingOAuth(null);
          window.TH_I18N.setLanguage(result.language || "en");
          setCurrentUser(result);
          if (window.TH_API) await window.TH_API.init();
        }}
        onCancel={() => {
          setPendingOAuth(null);
        }}
      />
    );
  }

  if (pending2FA && !currentUser) {
    return (
      <TwoFAStep
        partialToken={pending2FA}
        onVerified={async (user) => {
          setPending2FA(null);
          window.TH_I18N.setLanguage(user.language || "en");
          setCurrentUser(user);
          if (window.TH_API) await window.TH_API.init();
        }}
        onBack={() => setPending2FA(null)}
      />
    );
  }

  if (!currentUser) {
    return (
      <LoginPage
        onLogin={async (user) => {
          if (user && user.__2fa_required) {
            setPending2FA(user.partialToken);
            return;
          }
          window.TH_I18N.setLanguage(user.language || "en");
          setCurrentUser(user);
          if (window.TH_API) await window.TH_API.init();
        }}
        oauthError={oauthError}
        onDismissOAuthError={() => setOauthError(null)}
      />
    );
  }

  return (
    <App
      currentUser={currentUser}
      onLogout={() => {
        window.TH_API.logout();
        setCurrentUser(null);
      }}
      onProfileUpdate={(updated) => setCurrentUser(updated)}
    />
  );
}

async function boot() {
  root.render(
    <I18nProvider>
      <AuthRoot />
    </I18nProvider>
  );
}
boot();
