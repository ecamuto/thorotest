// Integrations (config-as-code), AI, Defects

const PROVIDERS = [
  { id: "github",     name: "GitHub",      icon: "github",  type: "vcs_ci",        configuredBy: "" },
  { id: "gitlab",     name: "GitLab",      icon: "gitlab",  type: "vcs_ci",        configuredBy: "" },
  { id: "jenkins",    name: "Jenkins",     icon: "jenkins", type: "ci",            configuredBy: "" },
  { id: "playwright", name: "Playwright",  icon: "plug",    type: "runner",        configuredBy: "playwright.config.ts" },
  { id: "cypress",    name: "Cypress",     icon: "plug",    type: "runner",        configuredBy: "cypress.config.js" },
  { id: "jest",       name: "Jest",        icon: "plug",    type: "runner",        configuredBy: "jest.config.js" },
  { id: "jira",       name: "Jira",        icon: "plug",    type: "issue_tracker", configuredBy: "" },
  { id: "linear",     name: "Linear",      icon: "plug",    type: "defects",       configuredBy: "" },
  { id: "slack",      name: "Slack",       icon: "plug",    type: "notifications", configuredBy: "#qa-alerts" },
  { id: "webhook",    name: "Webhook",     icon: "plug",    type: "outbound",      configuredBy: "" },
];

const TYPE_LABELS = {
  vcs_ci: "VCS + CI", ci: "CI", runner: "Runner",
  defects: "Defects", issue_tracker: "Issue tracker",
  notifications: "Notifications", outbound: "Outbound",
};

const WEBHOOK_EVENTS = ["run.completed", "run.failed", "defect.created", "defect.updated"];

const MODAL_OVERLAY = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 200,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const MODAL_BOX = {
  background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10,
  padding: "24px 28px", minWidth: 420, maxWidth: 560, width: "100%",
  maxHeight: "90vh", overflowY: "auto",
};

function VcsConfigFields({ form, setForm, tokenSet, provider = "github" }) {
  const fld = { marginBottom:12 };
  const lbl = { display:"block", fontSize:12, fontWeight:500, color:"var(--text-muted)", marginBottom:6 };
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));
  const isGitlab = provider === "gitlab";
  const repoPlaceholder = isGitlab ? "https://gitlab.com/group/repo" : "https://github.com/org/repo";
  const tokenHint = tokenSet ? "(leave blank to keep current)"
    : isGitlab ? "(private repos + Run CI need the api scope)"
               : "(private repos + Run CI need the actions scope)";
  const tokenPlaceholder = tokenSet ? "••••••••" : isGitlab ? "glpat-…" : "ghp_…";
  return (
    <>
      <div style={fld}>
        <label style={lbl}>Repository URL</label>
        <input className="login-input" value={form.repo_url} onChange={set("repo_url")} placeholder={repoPlaceholder} style={{width:"100%"}} />
      </div>
      <div style={{display:"flex", gap:8}}>
        <div style={{...fld, flex:1}}>
          <label style={lbl}>Branch</label>
          <input className="login-input" value={form.branch} onChange={set("branch")} placeholder="main" style={{width:"100%"}} />
        </div>
        <div style={{...fld, flex:2}}>
          <label style={lbl}>Path (folder of YAML tests)</label>
          <input className="login-input" value={form.path} onChange={set("path")} placeholder="tests/" style={{width:"100%"}} />
        </div>
      </div>
      <div style={fld}>
        <label style={lbl}>Personal access token {tokenHint}</label>
        <input className="login-input" type="password" value={form.token} onChange={set("token")} placeholder={tokenPlaceholder} autoComplete="off" style={{width:"100%"}} />
      </div>
      {isGitlab ? (
        <div style={fld}>
          <label style={lbl}>API base URL (self-hosted only — leave blank for gitlab.com)</label>
          <input className="login-input" value={form.api_base || ""} onChange={set("api_base")} placeholder="http://localhost:8929/api/v4" style={{width:"100%"}} />
        </div>
      ) : (
        <div style={{display:"flex", gap:8}}>
          <div style={{...fld, flex:1}}>
            <label style={lbl}>Workflow (for Run CI)</label>
            <input className="login-input" value={form.workflow || ""} onChange={set("workflow")} placeholder="ci.yml" style={{width:"100%"}} />
          </div>
          <div style={{...fld, flex:1}}>
            <label style={lbl}>JUnit artifact name</label>
            <input className="login-input" value={form.junit_artifact || ""} onChange={set("junit_artifact")} placeholder="junit" style={{width:"100%"}} />
          </div>
        </div>
      )}
    </>
  );
}

function JiraConfigFields({ form, setForm, tokenSet }) {
  const fld = { marginBottom:12 };
  const lbl = { display:"block", fontSize:12, fontWeight:500, color:"var(--text-muted)", marginBottom:6 };
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));
  return (
    <>
      <div style={fld}>
        <label style={lbl}>Jira base URL</label>
        <input className="login-input" value={form.base_url} onChange={set("base_url")} placeholder="https://your-org.atlassian.net" style={{width:"100%"}} />
      </div>
      <div style={{display:"flex", gap:8}}>
        <div style={{...fld, flex:2}}>
          <label style={lbl}>Account email</label>
          <input className="login-input" value={form.email} onChange={set("email")} placeholder="you@example.com" style={{width:"100%"}} />
        </div>
        <div style={{...fld, flex:1}}>
          <label style={lbl}>Project key</label>
          <input className="login-input" value={form.project_key} onChange={set("project_key")} placeholder="PAY" style={{width:"100%"}} />
        </div>
      </div>
      <div style={fld}>
        <label style={lbl}>API token {tokenSet ? "(leave blank to keep current)" : ""}</label>
        <input className="login-input" type="password" value={form.api_token} onChange={set("api_token")} placeholder={tokenSet ? "••••••••" : "Atlassian API token"} autoComplete="off" style={{width:"100%"}} />
      </div>
      <div style={fld}>
        <label style={lbl}>Bug issue type</label>
        <input className="login-input" value={form.issue_type_bug} onChange={set("issue_type_bug")} placeholder="Bug" style={{width:"100%"}} />
      </div>
    </>
  );
}

function IntRow({ intg, onEdit, onDelete, onSync }) {
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [syncing, setSyncing] = React.useState(false);
  const [syncMsg, setSyncMsg] = React.useState(null);
  const [ciBusy, setCiBusy] = React.useState(false);
  const [ciMsg, setCiMsg] = React.useState(null);
  const menuRef = React.useRef(null);
  const canSync = !!(intg.config && (intg.config.repo_url || (intg.type === "jira" && intg.config.base_url)));
  const isVcs = !!(intg.config && intg.config.repo_url) && intg.type !== "jira";

  const doSync = async () => {
    setSyncing(true); setSyncMsg(null);
    try {
      const r = await onSync(intg);
      setSyncMsg({ ok: true, text: `${r.created} new · ${r.updated} updated` + (r.skipped ? ` · ${r.skipped} skipped` : "") });
    } catch (e) {
      setSyncMsg({ ok: false, text: e.message });
    } finally { setSyncing(false); }
  };

  const doCI = async () => {
    setCiBusy(true); setCiMsg({ ok: true, text: "dispatching…" });
    try {
      const { job_id } = await window.TH_API.ciRun(intg.id, {});
      // Poll the background job until it finishes.
      const started = Date.now();
      while (Date.now() - started < 35 * 60 * 1000) {
        await new Promise(r => setTimeout(r, 5000));
        const job = await window.TH_API.ciJobStatus(intg.id, job_id);
        if (job.status === "done") {
          const s = job.imported || {};
          setCiMsg({ ok: true, text: `imported ${s.tests || 0} tests · ${s.runs || 0} run` });
          break;
        }
        if (job.status === "error") { setCiMsg({ ok: false, text: job.error || "CI run failed" }); break; }
        setCiMsg({ ok: true, text: job.status.replace("_", " ") + "…" });
      }
    } catch (e) {
      setCiMsg({ ok: false, text: e.message });
    } finally { setCiBusy(false); }
  };

  React.useEffect(() => {
    if (!menuOpen) return;
    const h = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [menuOpen]);

  return (
    <tr>
      <td>
        <div style={{display:"flex", alignItems:"center", gap:8}}>
          <span style={{display:"inline-flex", width:16, height:16, color:"var(--text-muted)"}}>{I[intg.icon] || I.plug}</span>
          {intg.name}
        </div>
      </td>
      <td className="mono dim">{TYPE_LABELS[intg.type] || intg.type}</td>
      <td>
        {intg.status === "active" ? <StatusBadge s="pass" /> :
         intg.status === "error"  ? <StatusBadge s="fail" /> :
         <StatusBadge s="skip" />}
      </td>
      <td className="mono dim">{intg.configured_by || "—"}</td>
      <td className="mono dim">
        {intg.last_sync || "—"}
        {syncMsg && <div style={{fontSize:10.5, color: syncMsg.ok ? "var(--pass)" : "var(--fail)"}}>{syncMsg.text}</div>}
        {ciMsg && <div style={{fontSize:10.5, color: ciMsg.ok ? "var(--accent)" : "var(--fail)"}}>CI: {ciMsg.text}</div>}
      </td>
      <td style={{position:"relative", textAlign:"right", whiteSpace:"nowrap"}} ref={menuRef}>
        {isVcs && (
          <button className="btn sm" style={{marginRight:6}} disabled={ciBusy} onClick={doCI} title="Trigger the CI pipeline and import its results">
            {ciBusy ? "Running…" : "Run CI"}
          </button>
        )}
        {canSync && (
          <button className="btn sm" style={{marginRight:6}} disabled={syncing} onClick={doSync}>
            {syncing ? "Syncing…" : "Sync"}
          </button>
        )}
        <button className="btn ghost icon sm" onClick={() => setMenuOpen(o => !o)}><Icon name="more" /></button>
        {menuOpen && (
          <div style={{
            position:"absolute", right:0, top:"100%", zIndex:10, minWidth:130,
            background:"var(--surface)", border:"1px solid var(--border)", borderRadius:6,
            boxShadow:"0 4px 16px rgba(0,0,0,0.2)", overflow:"hidden",
          }}>
            <button
              style={{display:"block", width:"100%", textAlign:"left", padding:"8px 14px", fontSize:12, border:"none", background:"none", cursor:"pointer", color:"var(--text)"}}
              onClick={() => { setMenuOpen(false); onEdit(intg); }}
            >Edit</button>
            <button
              style={{display:"block", width:"100%", textAlign:"left", padding:"8px 14px", fontSize:12, border:"none", background:"none", cursor:"pointer", color:"var(--fail)"}}
              onClick={() => { setMenuOpen(false); onDelete(intg); }}
            >Disconnect</button>
          </div>
        )}
      </td>
    </tr>
  );
}

function useEscapeClose(onClose) {
  React.useEffect(() => {
    const h = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);
}

function AddIntegrationModal({ onClose, onSaved, existingIds }) {
  const [step, setStep] = React.useState("pick");
  const [provider, setProvider] = React.useState(null);
  const [form, setForm] = React.useState({ configured_by: "" });
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState(null);
  useEscapeClose(onClose);

  const isVcs = provider?.id === "github" || provider?.id === "gitlab";
  const isJira = provider?.id === "jira";

  const pick = (p) => {
    setProvider(p);
    setForm({
      configured_by: p.configuredBy, repo_url: "", branch: "main", path: "", token: "",
      workflow: "ci.yml", junit_artifact: "junit", api_base: "",
      base_url: "", email: "", api_token: "", project_key: "", issue_type_bug: "Bug",
    });
    setStep("configure");
  };

  const save = async () => {
    setSaving(true); setErr(null);
    try {
      const id = `int-${provider.id}-${Date.now()}`;
      const payload = {
        id, name: provider.name, type: provider.type, icon: provider.icon,
        configured_by: form.configured_by || null, last_sync: null,
      };
      if (isVcs) {
        payload.config = {
          provider: provider.id,
          repo_url: form.repo_url.trim(),
          branch: form.branch.trim() || "main",
          path: form.path.trim(),
          token: form.token.trim(),
        };
        if (provider.id === "gitlab") {
          const apiBase = (form.api_base || "").trim();
          if (apiBase) payload.config.api_base = apiBase;
        } else {
          payload.config.workflow = (form.workflow || "").trim() || "ci.yml";
          payload.config.junit_artifact = (form.junit_artifact || "").trim() || "junit";
        }
      } else if (isJira) {
        payload.config = {
          base_url: form.base_url.trim(),
          email: form.email.trim(),
          api_token: form.api_token.trim(),
          project_key: form.project_key.trim(),
          issue_type_bug: form.issue_type_bug.trim() || "Bug",
        };
      }
      const created = await TH_API.createIntegration(payload);
      onSaved(created);
    } catch(e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div style={MODAL_OVERLAY} onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={MODAL_BOX}>
        {step === "pick" ? (
          <>
            <div style={{fontWeight:600, fontSize:14, marginBottom:4}}>Add integration</div>
            <div style={{fontSize:12, color:"var(--text-muted)", marginBottom:16}}>Choose a provider to connect.</div>
            <div style={{display:"grid", gridTemplateColumns:"repeat(3, 1fr)", gap:8, marginBottom:16}}>
              {PROVIDERS.filter(p => !existingIds.includes(`int-${p.id}`)).map(p => (
                <button
                  key={p.id}
                  onClick={() => pick(p)}
                  style={{
                    display:"flex", flexDirection:"column", alignItems:"center", gap:6,
                    padding:"14px 10px", border:"1px solid var(--border)", borderRadius:8,
                    background:"var(--bg-2)", cursor:"pointer", color:"var(--text)",
                  }}
                  onMouseOver={e => e.currentTarget.style.borderColor = "var(--accent)"}
                  onMouseOut={e => e.currentTarget.style.borderColor = "var(--border)"}
                >
                  <span style={{display:"inline-flex", width:20, height:20, color:"var(--text-muted)"}}>{I[p.icon] || I.plug}</span>
                  <span style={{fontSize:12, fontWeight:500}}>{p.name}</span>
                  <span style={{fontSize:10, color:"var(--text-dim)"}}>{TYPE_LABELS[p.type]}</span>
                </button>
              ))}
            </div>
            <button className="btn" onClick={onClose}>Cancel</button>
          </>
        ) : (
          <>
            <div style={{fontWeight:600, fontSize:14, marginBottom:4}}>Configure {provider.name}</div>
            <div style={{fontSize:12, color:"var(--text-muted)", marginBottom:16}}>Type: {TYPE_LABELS[provider.type]}</div>
            <div style={{marginBottom:14}}>
              <label style={{display:"block", fontSize:12, fontWeight:500, color:"var(--text-muted)", marginBottom:6}}>Configured by</label>
              <input
                className="login-input"
                value={form.configured_by}
                onChange={e => setForm(f => ({...f, configured_by: e.target.value}))}
                placeholder="e.g. org/repo · main"
                style={{width:"100%"}}
              />
            </div>
            {isVcs && <VcsConfigFields form={form} setForm={setForm} tokenSet={false} provider={provider.id} />}
            {isJira && <JiraConfigFields form={form} setForm={setForm} tokenSet={false} />}
            {err && <div style={{fontSize:12, color:"var(--fail)", marginBottom:8}}>{err}</div>}
            <div style={{display:"flex", gap:8}}>
              <button className="btn primary" onClick={save} disabled={saving}>{saving ? "Connecting…" : "Connect"}</button>
              <button className="btn" onClick={() => setStep("pick")}>Back</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function EditIntegrationModal({ intg, onClose, onSaved }) {
  useEscapeClose(onClose);
  const cfg = intg.config || {};
  const isJira = intg.type === "jira";
  const providerId = cfg.provider || (intg.icon === "gitlab" ? "gitlab" : "github");
  const isVcs = !isJira && (!!cfg.repo_url || intg.icon === "github" || intg.icon === "gitlab");
  const tokenSet = !!cfg.token_set;
  const apiTokenSet = !!cfg.api_token_set;
  const [form, setForm] = React.useState({
    name: intg.name, configured_by: intg.configured_by || "", status: intg.status,
    repo_url: cfg.repo_url || "", branch: cfg.branch || "main", path: cfg.path || "", token: "",
    workflow: cfg.workflow || "ci.yml", junit_artifact: cfg.junit_artifact || "junit",
    api_base: cfg.api_base || "",
    base_url: cfg.base_url || "", email: cfg.email || "", api_token: "",
    project_key: cfg.project_key || "", issue_type_bug: cfg.issue_type_bug || "Bug",
  });
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState(null);

  const save = async () => {
    setSaving(true); setErr(null);
    try {
      const payload = {
        name: form.name, configured_by: form.configured_by || null, status: form.status,
      };
      if (isVcs) {
        // Empty token is preserved server-side (token is never wiped by a blank field).
        payload.config = {
          provider: providerId,
          repo_url: form.repo_url.trim(),
          branch: form.branch.trim() || "main",
          path: form.path.trim(),
          token: form.token.trim(),
        };
        if (providerId === "gitlab") {
          payload.config.api_base = (form.api_base || "").trim();
        } else {
          payload.config.workflow = (form.workflow || "").trim() || "ci.yml";
          payload.config.junit_artifact = (form.junit_artifact || "").trim() || "junit";
        }
      } else if (isJira) {
        // Empty api_token is preserved server-side (never wiped by a blank field).
        payload.config = {
          base_url: form.base_url.trim(),
          email: form.email.trim(),
          api_token: form.api_token.trim(),
          project_key: form.project_key.trim(),
          issue_type_bug: form.issue_type_bug.trim() || "Bug",
        };
      }
      const updated = await TH_API.updateIntegration(intg.id, payload);
      onSaved(updated);
    } catch(e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div style={MODAL_OVERLAY} onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={MODAL_BOX}>
        <div style={{fontWeight:600, fontSize:14, marginBottom:16}}>Edit integration</div>
        <div style={{marginBottom:12}}>
          <label style={{display:"block", fontSize:12, fontWeight:500, color:"var(--text-muted)", marginBottom:6}}>Name</label>
          <input className="login-input" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} style={{width:"100%"}} />
        </div>
        <div style={{marginBottom:12}}>
          <label style={{display:"block", fontSize:12, fontWeight:500, color:"var(--text-muted)", marginBottom:6}}>Configured by</label>
          <input className="login-input" value={form.configured_by} onChange={e => setForm(f => ({...f, configured_by: e.target.value}))} style={{width:"100%"}} placeholder="e.g. org/repo · main" />
        </div>
        <div style={{marginBottom:16}}>
          <label style={{display:"block", fontSize:12, fontWeight:500, color:"var(--text-muted)", marginBottom:6}}>Status</label>
          <select className="select" value={form.status} onChange={e => setForm(f => ({...f, status: e.target.value}))}>
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
            <option value="error">Error</option>
          </select>
        </div>
        {isVcs && <VcsConfigFields form={form} setForm={setForm} tokenSet={tokenSet} provider={providerId} />}
        {isJira && <JiraConfigFields form={form} setForm={setForm} tokenSet={apiTokenSet} />}
        {err && <div style={{fontSize:12, color:"var(--fail)", marginBottom:8}}>{err}</div>}
        <div style={{display:"flex", gap:8}}>
          <button className="btn primary" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
          <button className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

function CreateTokenModal({ onClose, onCreated }) {
  useEscapeClose(onClose);
  const [form, setForm] = React.useState({ name: "", scope: "" });
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState(null);

  const save = async () => {
    if (!form.name.trim()) { setErr("Name is required"); return; }
    setSaving(true); setErr(null);
    try {
      const created = await TH_API.createToken({ name: form.name.trim(), scope: form.scope.trim() });
      onCreated(created);
    } catch(e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div style={MODAL_OVERLAY} onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={MODAL_BOX}>
        <div style={{fontWeight:600, fontSize:14, marginBottom:16}}>Generate API token</div>
        <div style={{marginBottom:12}}>
          <label style={{display:"block", fontSize:12, fontWeight:500, color:"var(--text-muted)", marginBottom:6}}>Token name</label>
          <input className="login-input" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} placeholder="e.g. ci-runner" style={{width:"100%"}} />
        </div>
        <div style={{marginBottom:16}}>
          <label style={{display:"block", fontSize:12, fontWeight:500, color:"var(--text-muted)", marginBottom:6}}>Scopes</label>
          <input className="login-input" value={form.scope} onChange={e => setForm(f => ({...f, scope: e.target.value}))} placeholder="report:write, runs:read" style={{width:"100%"}} />
          <div style={{fontSize:11, color:"var(--text-dim)", marginTop:4}}>Comma-separated. Leave empty for read-only.</div>
        </div>
        {err && <div style={{fontSize:12, color:"var(--fail)", marginBottom:8}}>{err}</div>}
        <div style={{display:"flex", gap:8}}>
          <button className="btn primary" onClick={save} disabled={saving}>{saving ? "Generating…" : "Generate"}</button>
          <button className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

function TokenRevealModal({ token, onClose }) {
  const [copied, setCopied] = React.useState(false);
  const copy = () => {
    navigator.clipboard.writeText(token.token).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div style={MODAL_OVERLAY}>
      <div style={MODAL_BOX}>
        <div style={{fontWeight:600, fontSize:14, marginBottom:4}}>Token created</div>
        <div style={{fontSize:12, color:"var(--warn)", marginBottom:16, padding:"8px 12px", background:"rgba(245,158,11,0.08)", borderRadius:6, border:"1px solid rgba(245,158,11,0.2)"}}>
          Copy this token now — it won't be shown again.
        </div>
        <div style={{display:"flex", gap:8, alignItems:"center", marginBottom:16}}>
          <code style={{flex:1, fontSize:11.5, fontFamily:"var(--font-mono)", padding:"8px 12px", background:"var(--bg-2)", borderRadius:6, border:"1px solid var(--border)", wordBreak:"break-all"}}>{token.token}</code>
          <button className="btn sm" style={{flexShrink:0}} onClick={copy}>{copied ? "Copied!" : "Copy"}</button>
        </div>
        <div style={{fontSize:12, color:"var(--text-muted)", marginBottom:16}}>
          <b>{token.name}</b> · scopes: <span className="mono">{token.scope || "read-only"}</span>
        </div>
        <button className="btn primary" onClick={onClose}>Done</button>
      </div>
    </div>
  );
}

function AddWebhookModal({ onClose, onSaved, existing }) {
  useEscapeClose(onClose);
  const [form, setForm] = React.useState(
    existing ? { url: existing.url, events: existing.events || [] }
             : { url: "", events: [] }
  );
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState(null);

  const toggleEvent = (ev) => {
    setForm(f => ({
      ...f,
      events: f.events.includes(ev) ? f.events.filter(e => e !== ev) : [...f.events, ev],
    }));
  };

  const save = async () => {
    if (!form.url.trim()) { setErr("URL is required"); return; }
    setSaving(true); setErr(null);
    try {
      let saved;
      if (existing) {
        saved = await TH_API.updateWebhook(existing.id, { url: form.url.trim(), events: form.events });
      } else {
        saved = await TH_API.createWebhook({ url: form.url.trim(), events: form.events });
      }
      onSaved(saved);
    } catch(e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div style={MODAL_OVERLAY} onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={MODAL_BOX}>
        <div style={{fontWeight:600, fontSize:14, marginBottom:16}}>{existing ? "Edit webhook" : "Add webhook"}</div>
        <div style={{marginBottom:12}}>
          <label style={{display:"block", fontSize:12, fontWeight:500, color:"var(--text-muted)", marginBottom:6}}>Endpoint URL</label>
          <input className="login-input" value={form.url} onChange={e => setForm(f => ({...f, url: e.target.value}))} placeholder="https://your-endpoint.example.com/hook" style={{width:"100%"}} />
        </div>
        <div style={{marginBottom:16}}>
          <label style={{display:"block", fontSize:12, fontWeight:500, color:"var(--text-muted)", marginBottom:8}}>Events</label>
          <div style={{display:"flex", flexDirection:"column", gap:6}}>
            {WEBHOOK_EVENTS.map(ev => (
              <label key={ev} style={{display:"flex", alignItems:"center", gap:8, cursor:"pointer", fontSize:12}}>
                <input
                  type="checkbox"
                  checked={form.events.includes(ev)}
                  onChange={() => toggleEvent(ev)}
                  style={{accentColor:"var(--accent)"}}
                />
                <span className="mono">{ev}</span>
              </label>
            ))}
          </div>
        </div>
        {err && <div style={{fontSize:12, color:"var(--fail)", marginBottom:8}}>{err}</div>}
        <div style={{display:"flex", gap:8}}>
          <button className="btn primary" onClick={save} disabled={saving}>{saving ? "Saving…" : (existing ? "Save" : "Add webhook")}</button>
          <button className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

function Integrations() {
  const [integrations, setIntegrations] = React.useState([]);
  const [tokens, setTokens]             = React.useState([]);
  const [webhooks, setWebhooks]         = React.useState([]);
  const [loading, setLoading]           = React.useState(true);
  const [error, setError]               = React.useState(null);

  const [addIntOpen, setAddIntOpen]     = React.useState(false);
  const [editingInt, setEditingInt]     = React.useState(null);
  const [addTokenOpen, setAddTokenOpen] = React.useState(false);
  const [revealToken, setRevealToken]   = React.useState(null);
  const [addWebhookOpen, setAddWebhookOpen]   = React.useState(false);
  const [editingWebhook, setEditingWebhook]   = React.useState(null);
  const [testingWh, setTestingWh]       = React.useState(null);
  const [testResults, setTestResults]   = React.useState({});

  React.useEffect(() => {
    Promise.all([
      TH_API.getIntegrations(),
      TH_API.getTokens(),
      TH_API.getWebhooks(),
    ]).then(([ints, toks, whs]) => {
      setIntegrations(ints);
      setTokens(toks);
      setWebhooks(whs);
    }).catch(e => setError(e.message))
    .finally(() => setLoading(false));
  }, []);

  const handleDeleteInt = async (intg) => {
    if (!window.confirm(`Disconnect ${intg.name}?`)) return;
    try {
      await TH_API.deleteIntegration(intg.id);
      setIntegrations(prev => prev.filter(i => i.id !== intg.id));
    } catch(e) { alert(e.message); }
  };

  const handleSyncInt = async (intg) => {
    const r = await TH_API.syncIntegration(intg.id);
    setIntegrations(prev => prev.map(i => i.id === intg.id ? { ...i, last_sync: r.last_sync, status: "active" } : i));
    return r;
  };

  const handleRevokeToken = async (tok) => {
    if (!window.confirm(`Revoke token "${tok.name}"?`)) return;
    try {
      await TH_API.revokeToken(tok.id);
      setTokens(prev => prev.filter(t => t.id !== tok.id));
    } catch(e) { alert(e.message); }
  };

  const handleDeleteWebhook = async (wh) => {
    if (!window.confirm("Delete this webhook?")) return;
    try {
      await TH_API.deleteWebhook(wh.id);
      setWebhooks(prev => prev.filter(w => w.id !== wh.id));
    } catch(e) { alert(e.message); }
  };

  const handleTestWebhook = async (wh) => {
    setTestingWh(wh.id);
    try {
      const res = await TH_API.testWebhook(wh.id);
      setTestResults(prev => ({...prev, [wh.id]: res}));
      setWebhooks(prev => prev.map(w => w.id === wh.id ? {...w, last_status_code: res.status_code, last_delivery_at: "just now"} : w));
    } catch(e) {
      setTestResults(prev => ({...prev, [wh.id]: {ok: false, status_code: 0}}));
    } finally { setTestingWh(null); }
  };

  const activeCount = integrations.filter(i => i.status === "active").length;

  if (loading) return <div className="page fade-in"><div className="empty">Loading…</div></div>;
  if (error)   return <div className="page fade-in"><div className="empty" style={{color:"var(--fail)"}}>{error}</div></div>;

  return (
    <div className="page fade-in">
      <div className="page-h">
        <div>
          <h1 className="page-title">Integrations</h1>
          <div className="page-sub">ThoroTest is configured as code — your <span className="mono">.thorotest/</span> directory is the source of truth.</div>
        </div>
        <div className="actions">
          <button className="btn accent" onClick={() => setAddIntOpen(true)}><Icon name="plus" /> Add integration</button>
        </div>
      </div>

      <div className="grid grid-2" style={{marginBottom:14}}>
        <div className="card">
          <div className="card-h">
            <div className="card-title">.thorotest/config.yml</div>
            <div className="spacer" />
            <span className="status pass" style={{padding:"1px 6px"}}>SYNCED</span>
          </div>
          <div style={{padding:14}}>
            <pre className="code">
{`# `}<span className="c">ThoroTest workspace config — checked into git</span>{`
`}<span className="k">workspace</span>{`: `}<span className="s">"org/repo"</span>{`
`}<span className="k">version</span>{`: `}<span className="n">1</span>{`

`}<span className="k">tests</span>{`:
  `}<span className="k">path</span>{`: `}<span className="s">"./tests/**/*.yml"</span>{`
  `}<span className="k">id_prefix</span>{`: `}<span className="s">"TC-"</span>{`

`}<span className="k">environments</span>{`:
  - `}<span className="k">id</span>{`: `}<span className="s">"staging"</span>{`
    `}<span className="k">url</span>{`: `}<span className="s">"https://staging.example.test"</span>{`

`}<span className="k">runners</span>{`:
  - `}<span className="k">name</span>{`: `}<span className="s">"playwright"</span>{`
    `}<span className="k">cmd</span>{`: `}<span className="s">"pnpm test:e2e"</span>{`
  - `}<span className="k">name</span>{`: `}<span className="s">"cypress"</span>{`
    `}<span className="k">cmd</span>{`: `}<span className="s">"pnpm cypress:run"</span>
            </pre>
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <div className="card-title">.github/workflows/thorotest.yml</div>
            <div className="spacer" />
            <span className="status pass" style={{padding:"1px 6px"}}>ACTIVE</span>
          </div>
          <div style={{padding:14}}>
            <pre className="code">
{`# `}<span className="c">Report results back to ThoroTest</span>{`
`}<span className="k">name</span>{`: `}<span className="s">"E2E + ThoroTest report"</span>{`
`}<span className="k">on</span>{`: [`}<span className="t">pull_request</span>{`, `}<span className="t">push</span>{`]

`}<span className="k">jobs</span>{`:
  `}<span className="k">e2e</span>{`:
    `}<span className="k">runs-on</span>{`: `}<span className="t">ubuntu-latest</span>{`
    `}<span className="k">steps</span>{`:
      - `}<span className="k">uses</span>{`: `}<span className="s">"thorotest/setup-action@v1"</span>{`
        `}<span className="k">with</span>{`:
          `}<span className="k">token</span>{`: `}<span className="t">{`{`}{`{ secrets.TESTHUB_TOKEN }`}{`}`}</span>{`
      - `}<span className="k">uses</span>{`: `}<span className="s">"thorotest/report-action@v1"</span>
            </pre>
          </div>
        </div>
      </div>

      <div className="card" style={{marginBottom:14}}>
        <div className="card-h">
          <div className="card-title">Connected integrations</div>
          <div className="card-sub">{activeCount} active</div>
        </div>
        {integrations.length === 0 ? (
          <div className="empty" style={{padding:"24px 0"}}>No integrations yet. Add one above.</div>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Integration</th><th>Type</th><th>Status</th><th>Configured by</th><th>Last sync</th><th style={{width:40}}></th></tr>
            </thead>
            <tbody>
              {integrations.map(intg => (
                <IntRow
                  key={intg.id}
                  intg={intg}
                  onEdit={setEditingInt}
                  onDelete={handleDeleteInt}
                  onSync={handleSyncInt}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-h">
            <div className="card-title">API tokens</div>
            <div className="spacer" />
            <button className="btn sm" onClick={() => setAddTokenOpen(true)}><Icon name="plus" /> Generate</button>
          </div>
          <div className="card-b">
            {tokens.length === 0 ? (
              <div className="empty" style={{padding:"16px 0"}}>No tokens yet.</div>
            ) : (
              <div style={{display:"flex", flexDirection:"column", gap:8}}>
                {tokens.map(t => (
                  <div key={t.id} style={{display:"flex", alignItems:"center", gap:10, padding:"10px 12px", border:"1px solid var(--border)", borderRadius:"var(--radius)", background:"var(--bg-2)"}}>
                    <div style={{flex:1, minWidth:0}}>
                      <div style={{fontSize:12, fontWeight:500}}>{t.name}</div>
                      <div className="mono dim" style={{fontSize:10.5}}>{t.token_prefix}… · {t.scope || "read-only"}</div>
                    </div>
                    {t.last_used_at && <span className="mono dim" style={{fontSize:10.5, flexShrink:0}}>used {t.last_used_at}</span>}
                    <button className="btn ghost icon sm" title="Revoke" onClick={() => handleRevokeToken(t)} style={{color:"var(--fail)"}}>✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <div className="card-title">Webhooks & outbound</div>
            <div className="spacer" />
            <button className="btn sm" onClick={() => setAddWebhookOpen(true)}><Icon name="plus" /> Add</button>
          </div>
          <div className="card-b">
            {webhooks.length === 0 ? (
              <div className="empty" style={{padding:"16px 0"}}>No webhooks yet.</div>
            ) : (
              <div style={{display:"flex", flexDirection:"column", gap:8}}>
                {webhooks.map(wh => {
                  const tr = testResults[wh.id];
                  const sc = wh.last_status_code;
                  const scOk = sc && sc >= 200 && sc < 300;
                  return (
                    <div key={wh.id} style={{padding:"10px 12px", border:"1px solid var(--border)", borderRadius:"var(--radius)", background:"var(--bg-2)"}}>
                      <div style={{display:"flex", alignItems:"center", gap:8, marginBottom:4}}>
                        {sc ? <span className={`status ${scOk ? "pass" : "fail"}`} style={{padding:"1px 6px"}}>{sc}</span> : null}
                        <span className="mono" style={{fontSize:11, flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{wh.url}</span>
                        <button
                          className="btn ghost icon sm"
                          title="Edit"
                          onClick={() => setEditingWebhook(wh)}
                          style={{flexShrink:0}}
                        >✎</button>
                        <button
                          className="btn sm"
                          style={{flexShrink:0, fontSize:11}}
                          disabled={testingWh === wh.id}
                          onClick={() => handleTestWebhook(wh)}
                        >{testingWh === wh.id ? "…" : "Test"}</button>
                        <button
                          className="btn ghost icon sm"
                          title="Delete"
                          style={{flexShrink:0, color:"var(--fail)"}}
                          onClick={() => handleDeleteWebhook(wh)}
                        >✕</button>
                      </div>
                      <div className="mono dim" style={{fontSize:10.5}}>
                        fires on: {(wh.events || []).join(", ") || "—"}
                        {wh.last_delivery_at ? ` · last delivery ${wh.last_delivery_at}` : ""}
                        {tr && <span style={{color: tr.ok ? "var(--pass)" : "var(--fail)", marginLeft:6}}>
                          {tr.ok ? "✓ OK" : tr.status_code ? `✕ ${tr.status_code}` : "✕ unreachable"}
                        </span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {addIntOpen && (
        <AddIntegrationModal
          existingIds={integrations.map(i => i.id)}
          onClose={() => setAddIntOpen(false)}
          onSaved={(created) => { setIntegrations(prev => [...prev, created]); setAddIntOpen(false); }}
        />
      )}
      {editingInt && (
        <EditIntegrationModal
          intg={editingInt}
          onClose={() => setEditingInt(null)}
          onSaved={(updated) => { setIntegrations(prev => prev.map(i => i.id === updated.id ? updated : i)); setEditingInt(null); }}
        />
      )}
      {addTokenOpen && (
        <CreateTokenModal
          onClose={() => setAddTokenOpen(false)}
          onCreated={(tok) => { setTokens(prev => [...prev, tok]); setAddTokenOpen(false); setRevealToken(tok); }}
        />
      )}
      {revealToken && (
        <TokenRevealModal
          token={revealToken}
          onClose={() => setRevealToken(null)}
        />
      )}
      {(addWebhookOpen || editingWebhook) && (
        <AddWebhookModal
          existing={editingWebhook}
          onClose={() => { setAddWebhookOpen(false); setEditingWebhook(null); }}
          onSaved={(saved) => {
            if (editingWebhook) {
              setWebhooks(prev => prev.map(w => w.id === saved.id ? saved : w));
            } else {
              setWebhooks(prev => [...prev, saved]);
            }
            setAddWebhookOpen(false);
            setEditingWebhook(null);
          }}
        />
      )}
    </div>
  );
}

function AIAssistant({ currentUser, currentFolderId }) {
  // Active panel: "generate" | "edge-cases"
  const [panel, setPanel] = React.useState("generate");

  // --- Generate Tests state ---
  const [genDesc, setGenDesc] = React.useState("");
  const [genCount, setGenCount] = React.useState(3);
  const [genLoading, setGenLoading] = React.useState(false);
  const [genError, setGenError] = React.useState(null);
  const [genResults, setGenResults] = React.useState(null);   // array of {title, steps}
  const [genSelected, setGenSelected] = React.useState({});  // {index: bool}
  const [genSaving, setGenSaving] = React.useState(false);
  const [genSaveError, setGenSaveError] = React.useState(null);

  // --- Edge Cases state ---
  const [ecLoading, setEcLoading] = React.useState(false);
  const [ecError, setEcError] = React.useState(null);
  const [ecResults, setEcResults] = React.useState(null);    // {suggestions: [{title, rationale}]}

  const handleGenerate = () => {
    if (!genDesc.trim()) return;
    setGenLoading(true);
    setGenError(null);
    setGenResults(null);
    setGenSelected({});
    TH_API.generateTests({ description: genDesc.trim(), count: genCount })
      .then(data => {
        const tests = Array.isArray(data) ? data : (data.tests || []);
        setGenResults(tests);
        const sel = {};
        tests.forEach((_, i) => { sel[i] = true; });
        setGenSelected(sel);
        setGenLoading(false);
      })
      .catch(err => { setGenError(err.message); setGenLoading(false); });
  };

  const handleSaveSelected = async () => {
    if (!genResults) return;
    setGenSaving(true);
    setGenSaveError(null);
    try {
      for (let i = 0; i < genResults.length; i++) {
        if (!genSelected[i]) continue;
        const tc = genResults[i];
        const created = await TH_API.createTest({
          title: tc.title,
          folder_id: currentFolderId || null,
          status: "pending",
        });
        if (tc.steps && tc.steps.length > 0) {
          await TH_API.replaceTestSteps(created.id, tc.steps.map((s, idx) => ({
            action: s.action || s,
            expected_result: s.expected_result || null,
          })));
        }
      }
      setGenResults(null);
      setGenSelected({});
      setGenDesc("");
    } catch(err) {
      setGenSaveError(err.message);
    } finally {
      setGenSaving(false);
    }
  };

  const handleSuggest = () => {
    setEcLoading(true);
    setEcError(null);
    setEcResults(null);
    TH_API.suggestEdgeCases({ folder_id: currentFolderId || null })
      .then(data => { setEcResults(data); setEcLoading(false); })
      .catch(err => { setEcError(err.message); setEcLoading(false); });
  };

  const anySelected = genResults && Object.values(genSelected).some(Boolean);

  return (
    <div className="page fade-in" style={{maxWidth:1000}}>
      <div className="page-h">
        <div>
          <div className="eyebrow"><span className="dot" style={{background:"var(--purple)"}} /> AI assistant</div>
          <h1 className="page-title" style={{marginTop:8}}>Test ideas that don't exist yet.</h1>
          <div className="page-sub">Generate test cases and discover edge cases using AI. Flaky analysis is available on each test's Run history tab.</div>
        </div>
      </div>

      {/* Panel tabs */}
      <div style={{display:"flex", gap:6, marginBottom:16}}>
        <button
          className={"btn sm" + (panel === "generate" ? " primary" : "")}
          onClick={() => setPanel("generate")}
        >Generate tests</button>
        <button
          className={"btn sm" + (panel === "edge-cases" ? " primary" : "")}
          onClick={() => setPanel("edge-cases")}
        >Suggest edge cases</button>
      </div>

      {/* Generate Tests panel */}
      {panel === "generate" && (
        <div className="card">
          <div className="card-h">
            <div className="card-title">Generate test cases</div>
            <div className="card-sub">Describe what to test — AI returns structured test cases with steps.</div>
          </div>
          <div className="card-b">
            <div className="field" style={{marginBottom:12}}>
              <label className="field-label">Describe what to test</label>
              <textarea
                className="textarea"
                style={{minHeight:80, fontFamily:"var(--font-sans)", width:"100%"}}
                value={genDesc}
                onChange={e => setGenDesc(e.target.value)}
                placeholder="e.g. When a user applies an expired coupon at checkout, the cart should show a graceful error and recalculate totals."
                disabled={genLoading}
              />
            </div>
            <div className="field" style={{marginBottom:14}}>
              <label className="field-label">Number of tests</label>
              <select
                className="select"
                value={genCount}
                onChange={e => setGenCount(parseInt(e.target.value, 10))}
                disabled={genLoading}
                style={{width:100}}
              >
                {[1,2,3,4,5,6,7,8,9,10].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div style={{display:"flex", gap:6, alignItems:"center"}}>
              <button
                className="btn primary"
                onClick={handleGenerate}
                disabled={genLoading || !genDesc.trim()}
              >
                {genLoading ? "Generating…" : <><Icon name="sparkle" /> Generate</>}
              </button>
            </div>
            {genError && (
              <div style={{fontSize:12, color:"var(--fail)", marginTop:10}}>{genError}</div>
            )}
            {genResults && genResults.length > 0 && (
              <div style={{marginTop:16}}>
                <div style={{fontSize:12, fontWeight:500, marginBottom:10, color:"var(--text-muted)"}}>
                  {genResults.length} test case{genResults.length !== 1 ? "s" : ""} generated — select which to save
                  {currentFolderId ? null : <span style={{color:"var(--warn)", marginLeft:8}}>(no folder selected — tests saved without folder)</span>}
                </div>
                <div style={{display:"flex", flexDirection:"column", gap:8}}>
                  {genResults.map((tc, i) => (
                    <div key={i} style={{padding:"10px 12px", border:"1px solid var(--border)", borderRadius:6, background:"var(--bg-2)"}}>
                      <label style={{display:"flex", alignItems:"flex-start", gap:10, cursor:"pointer"}}>
                        <input
                          type="checkbox"
                          checked={!!genSelected[i]}
                          onChange={e => setGenSelected(s => ({...s, [i]: e.target.checked}))}
                          style={{marginTop:2, accentColor:"var(--purple)"}}
                        />
                        <div>
                          <div style={{fontSize:13, fontWeight:500}}>{tc.title}</div>
                          {tc.steps && tc.steps.length > 0 && (
                            <ul style={{margin:"6px 0 0", paddingLeft:18, fontSize:12, color:"var(--text-muted)", lineHeight:1.7}}>
                              {tc.steps.map((s, si) => (
                                <li key={si}>{typeof s === "string" ? s : (s.action || JSON.stringify(s))}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </label>
                    </div>
                  ))}
                </div>
                {genSaveError && (
                  <div style={{fontSize:12, color:"var(--fail)", marginTop:8}}>{genSaveError}</div>
                )}
                <div style={{display:"flex", gap:8, marginTop:12}}>
                  <button
                    className="btn"
                    style={{background:"var(--purple)", color:"oklch(0.16 0 0)", borderColor:"var(--purple)"}}
                    onClick={handleSaveSelected}
                    disabled={!anySelected || genSaving}
                  >
                    {genSaving ? "Saving…" : "Save selected"}
                  </button>
                  <button className="btn" onClick={() => { setGenResults(null); setGenSelected({}); }}>Discard</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Edge Cases panel */}
      {panel === "edge-cases" && (
        <div className="card">
          <div className="card-h">
            <div className="card-title">Suggest edge cases</div>
            <div className="card-sub">
              {currentFolderId
                ? `Analyzing tests in folder ${currentFolderId} for missing coverage.`
                : "Navigate to a folder to see edge case suggestions."}
            </div>
          </div>
          <div className="card-b">
            {!currentFolderId && (
              <div style={{fontSize:12, color:"var(--text-muted)", marginBottom:12}}>
                Navigate to a folder first to enable edge case suggestions.
              </div>
            )}
            <button
              className="btn primary"
              onClick={handleSuggest}
              disabled={ecLoading || !currentFolderId}
            >
              {ecLoading ? "Analyzing…" : <><Icon name="sparkle" /> Suggest edge cases</>}
            </button>
            {ecError && (
              <div style={{fontSize:12, color:"var(--fail)", marginTop:10}}>{ecError}</div>
            )}
            {ecResults && (
              <div style={{marginTop:16}}>
                {(() => {
                  const suggestions = Array.isArray(ecResults) ? ecResults : (ecResults.suggestions || []);
                  if (suggestions.length === 0) {
                    return <div style={{fontSize:12, color:"var(--text-muted)"}}>No edge cases found for this folder.</div>;
                  }
                  return suggestions.map((s, i) => (
                    <div key={i} style={{padding:"12px 14px", border:"1px solid var(--border)", borderRadius:6, background:"var(--bg-2)", marginBottom:8}}>
                      <div style={{fontSize:13, fontWeight:500, marginBottom:4}}>{s.title}</div>
                      {s.rationale && (
                        <div style={{fontSize:12, color:"var(--text-muted)", marginBottom:8}}>{s.rationale}</div>
                      )}
                      <button
                        className="btn sm"
                        style={{background:"var(--purple)", color:"oklch(0.16 0 0)", borderColor:"var(--purple)"}}
                        onClick={() => {
                          setGenDesc(s.title);
                          setPanel("generate");
                        }}
                      >Generate test</button>
                    </div>
                  ));
                })()}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

window.Integrations = Integrations;
window.AIAssistant = AIAssistant;
