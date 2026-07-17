// ThoroTest — Settings view

const SETTING_TABS = [
  { id: "profile",       icon: "user" },
  { id: "password",      icon: "logout" },
  { id: "projects",      icon: "branch" },
  { id: "categories",    icon: "filter" },
  { id: "folders",       icon: "doc" },
  { id: "notifications", icon: "mail" },
  { id: "security",      icon: "user" },
];

function Settings({ currentUser, onProfileUpdate }) {
  const { t } = useI18n();
  const [tab, setTab] = useState("profile");

  return (
    <div className="page fade-in" style={{ padding: 0, display: "flex", gap: 0, maxWidth: 1000, height: "100%" }}>
      <div style={{
        width: 180, flexShrink: 0,
        borderRight: "1px solid var(--border)",
        padding: "20px 0",
        display: "flex", flexDirection: "column", gap: 2,
      }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", letterSpacing: "0.06em", textTransform: "uppercase", padding: "0 16px", marginBottom: 6 }}>{t("settings.title")}</div>
        {SETTING_TABS.map(tb => (
          <button
            key={tb.id}
            className={"nav-item" + (tab === tb.id ? " active" : "")}
            style={{ margin: "0 8px", borderRadius: 6, border: "none", background: tab === tb.id ? "var(--nav-active-bg, rgba(99,102,241,0.12))" : "transparent", color: tab === tb.id ? "var(--accent)" : "var(--text)", cursor: "pointer", textAlign: "left", display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", fontSize: 13 }}
            onClick={() => setTab(tb.id)}
            aria-current={tab === tb.id ? "page" : undefined}
          >
            <Icon name={tb.icon} className="nav-icon" />
            {t(`settings.${tb.id}`)}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, padding: "28px 36px", overflowY: "auto" }}>
        {tab === "profile"    && <ProfileTab currentUser={currentUser} onProfileUpdate={onProfileUpdate} />}
        {tab === "password"   && <PasswordTab />}
        {tab === "projects"   && <ProjectsTab />}
        {tab === "categories" && <CategoriesTab />}
        {tab === "folders"       && <FoldersTab />}
        {tab === "notifications" && <NotificationsTab currentUser={currentUser} />}
        {tab === "security"      && <SecurityTab currentUser={currentUser} />}
      </div>
    </div>
  );
}

/* ── shared helpers ──────────────────────────────────────── */

function SettingSection({ title, sub, children }) {
  return (
    <div style={{ marginBottom: 32 }}>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>{title}</div>
        {sub && <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{sub}</div>}
      </div>
      {children}
    </div>
  );
}

function Field({ label, children, hint }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--text-muted)", marginBottom: 6 }}>{label}</label>
      {children}
      {hint && <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

function TextInput({ value, onChange, type = "text", placeholder, disabled }) {
  return (
    <input
      className="login-input"
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder || ""}
      disabled={disabled}
      style={{ width: "100%", maxWidth: 380 }}
    />
  );
}

function SaveBar({ loading, success, error, onSave, label }) {
  const { t } = useI18n();
  const btnLabel = label || t("common.save");
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 20 }}>
      <button className="btn primary" onClick={onSave} disabled={loading} style={{ minWidth: 120 }}>
        {loading ? t("common.saving") : btnLabel}
      </button>
      {success && <span style={{ fontSize: 12, color: "var(--pass, #22c55e)" }}>{t("common.saved")}</span>}
      {error   && <span style={{ fontSize: 12, color: "var(--fail, #ef4444)" }}>{error}</span>}
    </div>
  );
}

/* ── Profile tab ─────────────────────────────────────────── */

function ProfileTab({ currentUser, onProfileUpdate }) {
  const { t, lang, setLanguage } = useI18n();
  const [displayName, setDisplayName] = useState(currentUser?.display_name || "");
  const [email, setEmail]             = useState(currentUser?.email || "");
  const [language, setLangLocal]      = useState(currentUser?.language || lang);
  const [loading, setLoading]         = useState(false);
  const [success, setSuccess]         = useState(false);
  const [error, setError]             = useState(null);

  const save = async () => {
    setLoading(true); setSuccess(false); setError(null);
    try {
      const updated = await window.TH_API.updateProfile({ display_name: displayName, email, language });
      onProfileUpdate(updated);
      setLanguage(language);
      setSuccess(true);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const supportedLangs = window.TH_I18N.getSupportedLanguages();

  return (
    <SettingSection title={t("settings.profileSection.title")} sub={t("settings.profileSection.sub")}>
      <Field label={t("settings.profileSection.displayName")}>
        <TextInput value={displayName} onChange={setDisplayName} placeholder={t("settings.profileSection.displayNamePlaceholder")} />
      </Field>
      <Field label={t("settings.profileSection.email")} hint={t("settings.profileSection.emailHint")}>
        <TextInput value={email} onChange={setEmail} type="email" placeholder={t("settings.profileSection.emailPlaceholder")} />
      </Field>
      <Field label={t("settings.profileSection.username")}>
        <TextInput value={currentUser?.username || ""} onChange={() => {}} disabled />
      </Field>
      <Field label={t("settings.profileSection.role")}>
        <TextInput value={currentUser?.role || ""} onChange={() => {}} disabled />
      </Field>
      <Field label={t("settings.profileSection.language")} hint={t("settings.profileSection.languageSub")}>
        <select
          className="login-input"
          value={language}
          onChange={e => setLangLocal(e.target.value)}
          style={{ width: "100%", maxWidth: 380 }}
        >
          {supportedLangs.map(code => (
            <option key={code} value={code}>{t(`languages.${code}`)}</option>
          ))}
        </select>
      </Field>
      <SaveBar loading={loading} success={success} error={error} onSave={save} label={t("settings.profileSection.saveChanges")} />
    </SettingSection>
  );
}

/* ── Password tab ────────────────────────────────────────── */

function PasswordTab() {
  const { t } = useI18n();
  const [current, setCurrent] = useState("");
  const [next, setNext]       = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError]     = useState(null);

  const save = async () => {
    setError(null); setSuccess(false);
    if (next !== confirm) { setError(t("settings.passwordSection.noMatch")); return; }
    if (next.length < 12) { setError(t("settings.passwordSection.tooShort")); return; }
    setLoading(true);
    try {
      await window.TH_API.changePassword(current, next);
      setSuccess(true);
      setCurrent(""); setNext(""); setConfirm("");
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <SettingSection title={t("settings.passwordSection.title")} sub={t("settings.passwordSection.sub")}>
      <Field label={t("settings.passwordSection.current")}>
        <TextInput value={current} onChange={setCurrent} type="password" placeholder="••••••••" />
      </Field>
      <Field label={t("settings.passwordSection.new")}>
        <TextInput value={next} onChange={setNext} type="password" placeholder="••••••••" />
      </Field>
      <Field label={t("settings.passwordSection.confirm")}>
        <TextInput value={confirm} onChange={setConfirm} type="password" placeholder="••••••••" />
      </Field>
      <SaveBar loading={loading} success={success} error={error} onSave={save} label={t("settings.passwordSection.updateBtn")} />
    </SettingSection>
  );
}

/* ── Projects tab ────────────────────────────────────────── */

function ProjectsTab() {
  const { t } = useI18n();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing]   = useState(null);
  const [form, setForm]         = useState({ name: "", description: "" });
  const [saving, setSaving]     = useState(false);
  const [saveErr, setSaveErr]   = useState(null);

  useEffect(() => {
    window.TH_API.getProjects()
      .then(setProjects)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const openCreate = () => { setForm({ name: "", description: "" }); setCreating(true); setEditing(null); setSaveErr(null); };
  const openEdit   = (p) => { setForm({ name: p.name, description: p.description || "" }); setEditing(p.id); setCreating(false); setSaveErr(null); };
  const closeForm  = () => { setCreating(false); setEditing(null); };

  const save = async () => {
    if (!form.name.trim()) { setSaveErr(t("common.nameRequired")); return; }
    setSaving(true); setSaveErr(null);
    try {
      if (creating) {
        const id = "proj-" + Date.now();
        const created = await window.TH_API.createProject({ id, name: form.name.trim(), description: form.description.trim() || null });
        setProjects(p => [...p, created]);
      } else {
        const updated = await window.TH_API.updateProject(editing, { name: form.name.trim(), description: form.description.trim() || null });
        setProjects(p => p.map(x => x.id === editing ? updated : x));
      }
      closeForm();
    } catch (e) { setSaveErr(e.message); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    if (!window.confirm(t("settings.projectsSection.deleteConfirm"))) return;
    try {
      await window.TH_API.deleteProject(id);
      setProjects(p => p.filter(x => x.id !== id));
    } catch (e) { alert(e.message); }
  };

  if (loading) return <div className="empty">{t("common.loading")}</div>;
  if (error)   return <div className="empty" style={{ color: "var(--fail)" }}>{error}</div>;

  return (
    <SettingSection title={t("settings.projectsSection.title")} sub={t("settings.projectsSection.sub")}>
      <div style={{ marginBottom: 12 }}>
        <button className="btn" onClick={openCreate}><Icon name="plus" /> {t("settings.projectsSection.newBtn")}</button>
      </div>

      {(creating || editing) && (
        <div className="card" style={{ padding: 16, marginBottom: 16, maxWidth: 480 }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 12 }}>{creating ? t("settings.projectsSection.newTitle") : t("settings.projectsSection.editTitle")}</div>
          <Field label={t("common.name")}>
            <TextInput value={form.name} onChange={v => setForm(f => ({ ...f, name: v }))} placeholder={t("settings.projectsSection.namePlaceholder")} />
          </Field>
          <Field label={t("common.description")}>
            <TextInput value={form.description} onChange={v => setForm(f => ({ ...f, description: v }))} placeholder={t("settings.projectsSection.descPlaceholder")} />
          </Field>
          {saveErr && <div style={{ fontSize: 12, color: "var(--fail)", marginBottom: 8 }}>{saveErr}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn primary" onClick={save} disabled={saving}>{saving ? t("common.saving") : t("common.save")}</button>
            <button className="btn" onClick={closeForm}>{t("common.cancel")}</button>
          </div>
        </div>
      )}

      {projects.length === 0 ? (
        <div className="empty" style={{ padding: "32px 0", textAlign: "left" }}>{t("settings.projectsSection.empty")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {projects.map(p => (
            <div key={p.id} className="card" style={{ padding: "12px 16px", display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</div>
                {p.description && <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>{p.description}</div>}
              </div>
              <button className="btn ghost" style={{ fontSize: 11 }} onClick={() => openEdit(p)}>{t("common.edit")}</button>
              <button className="btn ghost" style={{ fontSize: 11, color: "var(--fail)" }} onClick={() => remove(p.id)}>{t("common.delete")}</button>
            </div>
          ))}
        </div>
      )}
    </SettingSection>
  );
}

/* ── Categories tab ──────────────────────────────────────── */

const DEFAULT_COLORS = ["#6366f1", "#0ea5e9", "#22c55e", "#f59e0b", "#ef4444", "#ec4899", "#8b5cf6", "#14b8a6"];

function CategoriesTab() {
  const { t } = useI18n();
  const [categories, setCategories] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [creating, setCreating]     = useState(false);
  const [editing, setEditing]       = useState(null);
  const [form, setForm]             = useState({ name: "", color: "#6366f1" });
  const [saving, setSaving]         = useState(false);
  const [saveErr, setSaveErr]       = useState(null);

  useEffect(() => {
    window.TH_API.getCategories()
      .then(setCategories)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const openCreate = () => { setForm({ name: "", color: "#6366f1" }); setCreating(true); setEditing(null); setSaveErr(null); };
  const openEdit   = (c) => { setForm({ name: c.name, color: c.color }); setEditing(c.id); setCreating(false); setSaveErr(null); };
  const closeForm  = () => { setCreating(false); setEditing(null); };

  const save = async () => {
    if (!form.name.trim()) { setSaveErr(t("common.nameRequired")); return; }
    setSaving(true); setSaveErr(null);
    try {
      if (creating) {
        const id = "cat-" + Date.now();
        const created = await window.TH_API.createCategory({ id, name: form.name.trim(), color: form.color });
        setCategories(c => [...c, created]);
      } else {
        const updated = await window.TH_API.updateCategory(editing, { name: form.name.trim(), color: form.color });
        setCategories(c => c.map(x => x.id === editing ? updated : x));
      }
      closeForm();
    } catch (e) { setSaveErr(e.message); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    if (!window.confirm(t("settings.categoriesSection.deleteConfirm"))) return;
    try {
      await window.TH_API.deleteCategory(id);
      setCategories(c => c.filter(x => x.id !== id));
    } catch (e) { alert(e.message); }
  };

  if (loading) return <div className="empty">{t("common.loading")}</div>;
  if (error)   return <div className="empty" style={{ color: "var(--fail)" }}>{error}</div>;

  return (
    <SettingSection title={t("settings.categoriesSection.title")} sub={t("settings.categoriesSection.sub")}>
      <div style={{ marginBottom: 12 }}>
        <button className="btn" onClick={openCreate}><Icon name="plus" /> {t("settings.categoriesSection.newBtn")}</button>
      </div>

      {(creating || editing) && (
        <div className="card" style={{ padding: 16, marginBottom: 16, maxWidth: 480 }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 12 }}>{creating ? t("settings.categoriesSection.newTitle") : t("settings.categoriesSection.editTitle")}</div>
          <Field label={t("common.name")}>
            <TextInput value={form.name} onChange={v => setForm(f => ({ ...f, name: v }))} placeholder={t("settings.categoriesSection.namePlaceholder")} />
          </Field>
          <Field label={t("settings.categoriesSection.colorLabel")}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
              {DEFAULT_COLORS.map(c => (
                <button
                  key={c}
                  onClick={() => setForm(f => ({ ...f, color: c }))}
                  style={{
                    width: 24, height: 24, borderRadius: "50%", background: c, border: "none", cursor: "pointer",
                    outline: form.color === c ? "2px solid var(--text)" : "2px solid transparent",
                    outlineOffset: 2,
                  }}
                />
              ))}
            </div>
            <input
              type="color"
              value={form.color}
              onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
              style={{ width: 36, height: 28, padding: 2, borderRadius: 4, border: "1px solid var(--border)", cursor: "pointer" }}
            />
          </Field>
          {saveErr && <div style={{ fontSize: 12, color: "var(--fail)", marginBottom: 8 }}>{saveErr}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn primary" onClick={save} disabled={saving}>{saving ? t("common.saving") : t("common.save")}</button>
            <button className="btn" onClick={closeForm}>{t("common.cancel")}</button>
          </div>
        </div>
      )}

      {categories.length === 0 ? (
        <div className="empty" style={{ padding: "32px 0", textAlign: "left" }}>{t("settings.categoriesSection.empty")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {categories.map(c => (
            <div key={c.id} className="card" style={{ padding: "10px 16px", display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ width: 12, height: 12, borderRadius: "50%", background: c.color, flexShrink: 0, display: "inline-block" }} />
              <div style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>{c.name}</div>
              <span className="mono dim" style={{ fontSize: 11 }}>{c.color}</span>
              <button className="btn ghost" style={{ fontSize: 11 }} onClick={() => openEdit(c)}>{t("common.edit")}</button>
              <button className="btn ghost" style={{ fontSize: 11, color: "var(--fail)" }} onClick={() => remove(c.id)}>{t("common.delete")}</button>
            </div>
          ))}
        </div>
      )}
    </SettingSection>
  );
}

/* ── Folders tab ─────────────────────────────────────────── */

function FolderInlineForm({ formName, setFormName, onSubmit, onCancel, saving, saveErr, placeholder }) {
  const { t } = useI18n();
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 6, marginBottom: 6 }}>
      <input
        className="login-input"
        value={formName}
        onChange={e => setFormName(e.target.value)}
        placeholder={placeholder || t("settings.foldersSection.namePlaceholder")}
        style={{ width: 220, padding: "4px 8px", fontSize: 12 }}
        onKeyDown={e => { if (e.key === "Enter") onSubmit(); if (e.key === "Escape") onCancel(); }}
        autoFocus
      />
      <button className="btn primary" style={{ padding: "3px 10px", fontSize: 12 }} onClick={onSubmit} disabled={saving}>{saving ? "…" : t("common.save")}</button>
      <button className="btn" style={{ padding: "3px 8px", fontSize: 12 }} onClick={onCancel}>{t("common.cancel")}</button>
      {saveErr && <span style={{ fontSize: 11, color: "var(--fail)" }}>{saveErr}</span>}
    </div>
  );
}

function FolderRow({ folder, depth = 0, cb }) {
  const { t } = useI18n();
  const hasChildren = folder.children && folder.children.length > 0;
  const [collapsed, setCollapsed] = useState(false);
  const { startCreate, startRename, cancelForm, submitCreate, submitRename, remove, saving, saveErr, formName, setFormName, creating, renaming } = cb;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", borderRadius: 6, marginLeft: depth * 16 }}>
        <button
          onClick={() => hasChildren && setCollapsed(c => !c)}
          style={{ background: "none", border: "none", padding: 0, cursor: hasChildren ? "pointer" : "default", color: "var(--text-muted)", display: "inline-flex", flexShrink: 0, transition: "transform 0.15s", transform: collapsed ? "rotate(-90deg)" : "rotate(0deg)" }}
        >
          <Icon name={hasChildren ? "chevD" : "doc"} />
        </button>

        {renaming === folder.id ? (
          <div style={{ flex: 1 }}>
            <FolderInlineForm formName={formName} setFormName={setFormName} onSubmit={submitRename} onCancel={cancelForm} saving={saving} saveErr={saveErr} />
          </div>
        ) : (
          <>
            <span style={{ flex: 1, fontSize: 13 }}>{folder.name}</span>
            <span className="mono dim" style={{ fontSize: 10.5 }}>{t("settings.foldersSection.tests", { count: folder.count })}</span>
            <button className="btn ghost icon" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => startRename(folder)} title="Rename">✎</button>
            <button className="btn ghost icon" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => startCreate(folder.id)} title="Add sub-folder"><Icon name="plus" /></button>
            <button className="btn ghost icon" style={{ fontSize: 11, padding: "2px 8px", color: "var(--fail)" }} onClick={() => remove(folder.id)} title="Delete">✕</button>
          </>
        )}
      </div>

      {!collapsed && creating === folder.id && (
        <div style={{ marginLeft: (depth + 1) * 16 + 8, marginTop: 2 }}>
          <FolderInlineForm formName={formName} setFormName={setFormName} onSubmit={submitCreate} onCancel={cancelForm} saving={saving} saveErr={saveErr} />
        </div>
      )}

      {!collapsed && hasChildren && folder.children.map(child => (
        <FolderRow key={child.id} folder={child} depth={depth + 1} cb={cb} />
      ))}
    </div>
  );
}

function FoldersTab() {
  const { t } = useI18n();
  const [folders, setFolders]     = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [creating, setCreating]   = useState(null);
  const [renaming, setRenaming]   = useState(null);
  const [formName, setFormName]   = useState("");
  const [saving, setSaving]       = useState(false);
  const [saveErr, setSaveErr]     = useState(null);

  const reload = () => {
    setLoading(true);
    window.TH_API.getFolders()
      .then(setFolders)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { reload(); }, []);

  const startCreate = (parentId) => { setCreating(parentId); setRenaming(null); setFormName(""); setSaveErr(null); };
  const startRename = (f)        => { setRenaming(f.id); setCreating(null); setFormName(f.name); setSaveErr(null); };
  const cancelForm  = ()         => { setCreating(null); setRenaming(null); };

  const submitCreate = async () => {
    if (!formName.trim()) { setSaveErr(t("common.nameRequired")); return; }
    setSaving(true); setSaveErr(null);
    try {
      const id = "f-" + Date.now();
      await window.TH_API.createFolder({
        id, name: formName.trim(),
        parent_id: creating === "root" ? null : creating,
      });
      reload();
      cancelForm();
    } catch (e) { setSaveErr(e.message); }
    finally { setSaving(false); }
  };

  const submitRename = async () => {
    if (!formName.trim()) { setSaveErr(t("common.nameRequired")); return; }
    setSaving(true); setSaveErr(null);
    try {
      await window.TH_API.updateFolder(renaming, { name: formName.trim() });
      reload();
      cancelForm();
    } catch (e) { setSaveErr(e.message); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    if (!window.confirm(t("settings.foldersSection.deleteConfirm"))) return;
    try {
      await window.TH_API.deleteFolder(id);
      reload();
    } catch (e) { alert(e.message); }
  };

  if (loading) return <div className="empty">{t("common.loading")}</div>;
  if (error)   return <div className="empty" style={{ color: "var(--fail)" }}>{error}</div>;

  const callbacks = { startCreate, startRename, cancelForm, submitCreate, submitRename, remove, saving, saveErr, formName, setFormName, creating, renaming };

  return (
    <SettingSection title={t("settings.foldersSection.title")} sub={t("settings.foldersSection.sub")}>
      <div style={{ marginBottom: 12 }}>
        <button className="btn" onClick={() => startCreate("root")}><Icon name="plus" /> {t("settings.foldersSection.newRootBtn")}</button>
      </div>
      {creating === "root" && (
        <div style={{ marginBottom: 8 }}>
          <FolderInlineForm formName={formName} setFormName={setFormName} onSubmit={submitCreate} onCancel={cancelForm} saving={saving} saveErr={saveErr} />
        </div>
      )}
      {folders.length === 0 ? (
        <div className="empty" style={{ padding: "32px 0", textAlign: "left" }}>{t("settings.foldersSection.empty")}</div>
      ) : (
        <div className="card" style={{ padding: "8px 0" }}>
          {folders.map(f => <FolderRow key={f.id} folder={f} cb={callbacks} />)}
        </div>
      )}
    </SettingSection>
  );
}

/* ── Notifications tab ───────────────────────────────────── */

function NotificationsTab({ currentUser }) {
  const { t } = useI18n();
  const [cfg, setCfg] = React.useState({
    email_enabled: false, smtp_host: "", smtp_port: 587,
    smtp_user: "", smtp_pass: "", smtp_from: "",
    slack_enabled: false, slack_webhook_url: "",
    notify_run_complete: true, notify_consecutive_fail: true,
    consecutive_fail_threshold: 3, notify_comment: true,
    notify_mention: true, notify_assigned: true,
  });
  const [saving, setSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    window.TH_API.getNotificationConfig().then(data => {
      if (data && typeof data === "object") {
        setCfg(prev => ({
          ...prev,
          email_enabled: !!data.email_enabled,
          smtp_host: data.smtp_host || "",
          smtp_port: data.smtp_port || 587,
          smtp_user: data.smtp_user || "",
          smtp_pass: data.smtp_pass || "",
          smtp_from: data.smtp_from || "",
          slack_enabled: !!data.slack_enabled,
          slack_webhook_url: data.slack_webhook_url || "",
          notify_run_complete: data.notify_run_complete !== false,
          notify_consecutive_fail: data.notify_consecutive_fail !== false,
          consecutive_fail_threshold: data.consecutive_fail_threshold || 3,
          notify_comment: data.notify_comment !== false,
          notify_mention: data.notify_mention !== false,
          notify_assigned: data.notify_assigned !== false,
        }));
      }
    }).catch(() => {});
  }, []);

  function handleSave() {
    setSaving(true);
    window.TH_API.putNotificationConfig({
      ...cfg,
      smtp_port: parseInt(cfg.smtp_port, 10) || 587,
      consecutive_fail_threshold: parseInt(cfg.consecutive_fail_threshold, 10) || 3,
      smtp_host: cfg.smtp_host || null,
      smtp_user: cfg.smtp_user || null,
      smtp_pass: cfg.smtp_pass || null,
      smtp_from: cfg.smtp_from || null,
      slack_webhook_url: cfg.slack_webhook_url || null,
    }).then(() => {
      setSaving(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }).catch(() => setSaving(false));
  }

  function field(label, key, type = "text", placeholder = "") {
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={{ display: "block", fontSize: 12, marginBottom: 4, color: "var(--text)" }}>
          {label}
        </label>
        <input
          type={type}
          className="input"
          value={cfg[key] || ""}
          placeholder={placeholder}
          onChange={e => setCfg(p => ({ ...p, [key]: e.target.value }))}
          style={{ width: "100%" }}
        />
      </div>
    );
  }

  function toggle(label, key) {
    return (
      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: 10 }}>
        <input type="checkbox" checked={!!cfg[key]}
               onChange={e => setCfg(p => ({ ...p, [key]: e.target.checked }))} />
        <span style={{ fontSize: 13 }}>{label}</span>
      </label>
    );
  }

  return (
    <div style={{ padding: "0 4px" }}>
      <h3 style={{ marginBottom: 4 }}>Notifications</h3>
      <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 20 }}>
        Configure delivery channels and event triggers.
      </p>

      {/* Event toggles */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>Events</div>
        {toggle("Notify on run complete", "notify_run_complete")}
        {toggle("Notify on consecutive test failures", "notify_consecutive_fail")}
        {cfg.notify_consecutive_fail && (
          <div style={{ paddingLeft: 20, marginBottom: 10 }}>
            {field("Failure threshold", "consecutive_fail_threshold", "number", "3")}
          </div>
        )}
        {toggle("Notify on new comments", "notify_comment")}
        {toggle("Notify when @mentioned in a comment", "notify_mention")}
        {toggle("Notify when a record is assigned to me", "notify_assigned")}
      </div>

      {/* Email section */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>Email (SMTP)</div>
        {toggle("Enable email notifications", "email_enabled")}
        {cfg.email_enabled && (
          <div style={{ paddingLeft: 4 }}>
            {field("SMTP host", "smtp_host", "text", "smtp.gmail.com")}
            {field("SMTP port", "smtp_port", "number", "587")}
            {field("Username", "smtp_user", "text", "you@gmail.com")}
            {field("Password", "smtp_pass", "password", "app password")}
            {field("From address", "smtp_from", "email", "you@gmail.com")}
            <p style={{ fontSize: 11, color: "var(--muted)", marginTop: -6 }}>
              Credentials are stored as-is. Use an app password for Gmail.
            </p>
          </div>
        )}
      </div>

      {/* Slack section */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>Slack</div>
        {toggle("Enable Slack notifications", "slack_enabled")}
        {cfg.slack_enabled && (
          <div style={{ paddingLeft: 4 }}>
            {field("Webhook URL", "slack_webhook_url", "url", "https://hooks.slack.com/...")}
          </div>
        )}
      </div>

      <button className="btn primary" onClick={handleSave} disabled={saving}>
        {saving ? "Saving…" : saved ? "Saved." : "Save changes"}
      </button>
    </div>
  );
}

/* ── Security tab ────────────────────────────────────────── */

function SecurityTab({ currentUser }) {
  const [status, setStatus] = React.useState(null); // {remaining, enabled}
  const [loadErr, setLoadErr] = React.useState(null);
  const [dialog, setDialog] = React.useState(null); // 'enroll' | 'disable' | 'regen'

  const reload = () => {
    window.TH_API.get2FACount()
      .then(setStatus)
      .catch(e => setLoadErr(e.message));
  };

  React.useEffect(() => { reload(); }, []);

  if (loadErr) return <div className="empty" style={{ color: "var(--fail)" }}>{loadErr}</div>;
  if (!status) return <div className="empty">Loading…</div>;

  return (
    <SettingSection title="Two-factor authentication" sub="Add a second factor to protect your account.">
      {!status.enabled ? (
        <div>
          <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
            Two-factor authentication is not enabled on your account.
          </p>
          <button className="btn primary" onClick={() => setDialog("enroll")}>
            Enable two-factor authentication
          </button>
        </div>
      ) : (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--pass, #22c55e)", background: "rgba(34,197,94,0.12)", borderRadius: 4, padding: "2px 8px" }}>2FA active</span>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 4 }}>
            {status.remaining} recovery code{status.remaining !== 1 ? "s" : ""} remaining
          </p>
          {status.remaining <= 2 && (
            <p style={{ fontSize: 12, color: "var(--warn, #f59e0b)", marginBottom: 12 }}>
              You are running low on recovery codes. Consider regenerating them.
            </p>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="btn" onClick={() => setDialog("regen")}>Regenerate recovery codes</button>
            <button className="btn" style={{ color: "var(--fail)" }} onClick={() => setDialog("disable")}>Disable 2FA</button>
          </div>
        </div>
      )}

      {dialog === "enroll" && (
        <EnrollDialog onClose={() => { setDialog(null); reload(); }} />
      )}
      {dialog === "disable" && (
        <DisableDialog onClose={() => { setDialog(null); reload(); }} />
      )}
      {dialog === "regen" && (
        <RegenDialog onClose={() => { setDialog(null); reload(); }} />
      )}
    </SettingSection>
  );
}

function EnrollDialog({ onClose }) {
  const [step, setStep] = React.useState(1);
  const [setup, setSetup] = React.useState(null); // {secret, qr_data_uri}
  const [pendingSecret, setPendingSecret] = React.useState(null);
  const [code, setCode] = React.useState("");
  const [recoveryCodes, setRecoveryCodes] = React.useState([]);
  const [acked, setAcked] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    window.TH_API.get2FASetup()
      .then(data => { setSetup(data); setPendingSecret(data.secret); })
      .catch(e => setError(e.message));
  }, []);

  async function submitCode(e) {
    e.preventDefault();
    setLoading(true); setError(null);
    try {
      const result = await window.TH_API.enable2FA(pendingSecret, code.trim());
      setRecoveryCodes(result.recovery_codes);
      setStep(3);
    } catch (err) {
      setError(err.message || "Invalid code");
    } finally {
      setLoading(false);
    }
  }

  function copyAll() {
    navigator.clipboard.writeText(recoveryCodes.join("\n")).catch(() => {});
  }

  function download() {
    const blob = new Blob([recoveryCodes.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "recovery-codes.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div className="card" style={{ width: 420, maxWidth: "90vw", padding: 28, maxHeight: "90vh", overflowY: "auto" }}>
        {step === 1 && (
          <>
            <h3 style={{ marginBottom: 12, fontSize: 15, fontWeight: 600 }}>Set up authenticator app</h3>
            {error && <div className="login-error" style={{ marginBottom: 12 }}>{error}</div>}
            {setup ? (
              <>
                <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
                  Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.), or enter the secret manually.
                </p>
                <div style={{ textAlign: "center", marginBottom: 16 }}>
                  <img src={setup.qr_data_uri} alt="TOTP QR code" style={{ display: "block", margin: "0 auto", background: "#fff", borderRadius: 4, padding: 8 }} />
                </div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Manual secret</label>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input className="login-input" readOnly value={setup.secret} style={{ flex: 1, fontFamily: "monospace", fontSize: 12 }} data-testid="totp-secret" />
                    <button className="btn" onClick={() => navigator.clipboard.writeText(setup.secret).catch(() => {})}>Copy</button>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn primary" onClick={() => setStep(2)}>Next</button>
                  <button className="btn" onClick={onClose}>Cancel</button>
                </div>
              </>
            ) : (
              <p style={{ fontSize: 13, color: "var(--text-muted)" }}>Loading…</p>
            )}
          </>
        )}

        {step === 2 && (
          <>
            <h3 style={{ marginBottom: 12, fontSize: 15, fontWeight: 600 }}>Verify your authenticator</h3>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
              Enter the 6-digit code shown in your authenticator app to confirm it is set up correctly.
            </p>
            <form onSubmit={submitCode}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>TOTP code</label>
                <input
                  className="login-input"
                  type="text"
                  value={code}
                  onChange={e => setCode(e.target.value)}
                  placeholder="000000"
                  required
                  autoFocus
                  style={{ maxWidth: 200 }}
                />
              </div>
              {error && <div className="login-error" style={{ marginBottom: 12 }}>{error}</div>}
              <div style={{ display: "flex", gap: 8 }}>
                <button type="submit" className="btn primary" disabled={loading}>{loading ? "Verifying…" : "Verify"}</button>
                <button type="button" className="btn" onClick={onClose}>Cancel</button>
              </div>
            </form>
          </>
        )}

        {step === 3 && (
          <>
            <h3 style={{ marginBottom: 12, fontSize: 15, fontWeight: 600 }}>Save your recovery codes</h3>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
              Store these 10 recovery codes somewhere safe. Each code can be used once to access your account if you lose your authenticator.
            </p>
            <div style={{ fontFamily: "monospace", fontSize: 13, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: 12, marginBottom: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
              {recoveryCodes.map((c, i) => <span key={i}>{c}</span>)}
            </div>
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              <button className="btn" onClick={copyAll}>Copy all</button>
              <button className="btn" onClick={download}>Download .txt</button>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: 16, fontSize: 13 }}>
              <input type="checkbox" checked={acked} onChange={e => setAcked(e.target.checked)} data-testid="ack-checkbox" />
              I have saved my codes
            </label>
            <button className="btn primary" disabled={!acked} onClick={onClose} data-testid="finish-btn">Finish</button>
          </>
        )}
      </div>
    </div>
  );
}

function DisableDialog({ onClose }) {
  const [code, setCode] = React.useState("");
  const [error, setError] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  async function confirm(e) {
    e.preventDefault();
    setLoading(true); setError(null);
    try {
      await window.TH_API.disable2FA(code.trim());
      onClose();
    } catch (err) {
      setError(err.message || "Invalid code");
      setLoading(false);
    }
  }

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div className="card" style={{ width: 380, maxWidth: "90vw", padding: 28 }}>
        <h3 style={{ marginBottom: 12, fontSize: 15, fontWeight: 600, color: "var(--fail)" }}>Disable two-factor authentication</h3>
        <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
          Disabling 2FA reduces account security. Enter your current TOTP code to confirm.
        </p>
        <form onSubmit={confirm}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>TOTP code</label>
            <input
              className="login-input"
              type="text"
              value={code}
              onChange={e => setCode(e.target.value)}
              placeholder="000000"
              required
              autoFocus
              style={{ maxWidth: 200 }}
            />
          </div>
          {error && <div className="login-error" style={{ marginBottom: 12 }}>{error}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn primary" disabled={loading} style={{ background: "var(--fail)" }}>{loading ? "Disabling…" : "Confirm disable"}</button>
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function RegenDialog({ onClose }) {
  const [code, setCode] = React.useState("");
  const [error, setError] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [codes, setCodes] = React.useState(null);

  async function submit(e) {
    e.preventDefault();
    setLoading(true); setError(null);
    try {
      const result = await window.TH_API.regenerate2FACodes(code.trim());
      setCodes(result.recovery_codes);
    } catch (err) {
      setError(err.message || "Invalid code");
      setLoading(false);
    }
  }

  function copyAll() {
    navigator.clipboard.writeText(codes.join("\n")).catch(() => {});
  }

  function download() {
    const blob = new Blob([codes.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "recovery-codes.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div className="card" style={{ width: 400, maxWidth: "90vw", padding: 28, maxHeight: "90vh", overflowY: "auto" }}>
        {!codes ? (
          <>
            <h3 style={{ marginBottom: 12, fontSize: 15, fontWeight: 600 }}>Regenerate recovery codes</h3>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
              Enter your current TOTP code to generate 10 new recovery codes. Your old codes will be invalidated.
            </p>
            <form onSubmit={submit}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>TOTP code</label>
                <input
                  className="login-input"
                  type="text"
                  value={code}
                  onChange={e => setCode(e.target.value)}
                  placeholder="000000"
                  required
                  autoFocus
                  style={{ maxWidth: 200 }}
                />
              </div>
              {error && <div className="login-error" style={{ marginBottom: 12 }}>{error}</div>}
              <div style={{ display: "flex", gap: 8 }}>
                <button type="submit" className="btn primary" disabled={loading}>{loading ? "Regenerating…" : "Regenerate"}</button>
                <button type="button" className="btn" onClick={onClose}>Cancel</button>
              </div>
            </form>
          </>
        ) : (
          <>
            <h3 style={{ marginBottom: 12, fontSize: 15, fontWeight: 600 }}>New recovery codes</h3>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
              Your old recovery codes have been invalidated. Store these 10 new codes somewhere safe.
            </p>
            <div style={{ fontFamily: "monospace", fontSize: 13, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: 12, marginBottom: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
              {codes.map((c, i) => <span key={i}>{c}</span>)}
            </div>
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              <button className="btn" onClick={copyAll}>Copy all</button>
              <button className="btn" onClick={download}>Download .txt</button>
            </div>
            <button className="btn primary" onClick={onClose}>Done</button>
          </>
        )}
      </div>
    </div>
  );
}

window.Settings = Settings;
