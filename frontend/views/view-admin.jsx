// Admin page — user management + audit log tabs

function AdminPage({ currentUser, onNav }) {
  const { t } = useI18n();
  const [tab, setTab] = React.useState("users");
  const [users, setUsers] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [showNewForm, setShowNewForm] = React.useState(false);
  const [newUser, setNewUser] = React.useState({
    username: "", email: "", password: "", display_name: "", role: "tester"
  });
  const [creating, setCreating] = React.useState(false);

  const ROLES = ["admin", "manager", "tester", "viewer"];

  const ADMIN_TABS = [
    { id: "users",     label: t("admin.users") || "User Management" },
    { id: "custom-fields", label: "Custom Fields" },
    ...(window.can && window.can(currentUser, "manage") ? [{ id: "audit-log", label: "Audit Log" }] : []),
  ];

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await window.TH_API.listAdminUsers();
      setUsers(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const handleRoleChange = async (userId, newRole) => {
    try {
      const updated = await window.TH_API.updateUserRole(userId, newRole);
      setUsers(us => us.map(u => u.id === userId ? updated : u));
    } catch (e) {
      alert("Errore cambio ruolo: " + e.message);
    }
  };

  const handleDelete = async (user) => {
    if (!confirm(`Eliminare ${user.display_name || user.username}?`)) return;
    try {
      await window.TH_API.deleteAdminUser(user.id);
      setUsers(us => us.filter(u => u.id !== user.id));
    } catch (e) {
      alert("Errore: " + e.message);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      const created = await window.TH_API.createAdminUser(newUser);
      setUsers(us => [...us, created]);
      setNewUser({ username: "", email: "", password: "", display_name: "", role: "tester" });
      setShowNewForm(false);
    } catch (e) {
      alert("Errore creazione utente: " + e.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="page fade-in" style={{ padding: "20px 24px" }}>
      {/* Tab bar */}
      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)", marginBottom: 20 }}>
        {ADMIN_TABS.map(tb => (
          <button
            key={tb.id}
            onClick={() => setTab(tb.id)}
            className={"btn ghost sm"}
            style={{
              borderBottom: tab === tb.id ? "2px solid var(--accent)" : "2px solid transparent",
              borderRadius: 0,
              paddingBottom: 10,
              color: tab === tb.id ? "var(--accent)" : "var(--text)",
            }}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {tab === "users" && (
        <div>
          {loading && <div className="page-content"><p>{t("common.loading")}</p></div>}
          {error && <div className="page-content"><p style={{color:"var(--danger)"}}>Errore: {error}</p></div>}
          {!loading && !error && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>{t("admin.title")}</h2>
                <button className="btn accent sm" onClick={() => setShowNewForm(s => !s)}>
                  {showNewForm ? t("common.cancel") : t("admin.newUser")}
                </button>
              </div>

              {showNewForm && (
                <form onSubmit={handleCreate} style={{
                  background: "var(--card-bg)", border: "1px solid var(--border)",
                  borderRadius: 8, padding: 16, marginBottom: 20,
                  display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10
                }}>
                  <input className="input" placeholder="Username *" required
                    value={newUser.username} onChange={e => setNewUser(u => ({...u, username: e.target.value}))} />
                  <input className="input" placeholder={t("login.email") + " *"} type="email" required
                    value={newUser.email} onChange={e => setNewUser(u => ({...u, email: e.target.value}))} />
                  <input className="input" placeholder="Password *" type="password" required
                    value={newUser.password} onChange={e => setNewUser(u => ({...u, password: e.target.value}))} />
                  <input className="input" placeholder={t("admin.displayName")}
                    value={newUser.display_name} onChange={e => setNewUser(u => ({...u, display_name: e.target.value}))} />
                  <select className="input" value={newUser.role}
                    onChange={e => setNewUser(u => ({...u, role: e.target.value}))}>
                    {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <button type="submit" className="btn accent sm" disabled={creating}>
                    {creating ? "Creazione..." : "Crea utente"}
                  </button>
                </form>
              )}

              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                    <th style={{ padding: "8px 12px" }}>{t("common.name")}</th>
                    <th style={{ padding: "8px 12px" }}>{t("login.email")}</th>
                    <th style={{ padding: "8px 12px" }}>Username</th>
                    <th style={{ padding: "8px 12px" }}>{t("admin.role")}</th>
                    <th style={{ padding: "8px 12px" }}>Azioni</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(user => (
                    <tr key={user.id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 12px" }}>{user.display_name || "—"}</td>
                      <td style={{ padding: "8px 12px" }}>{user.email}</td>
                      <td style={{ padding: "8px 12px" }}>{user.username}</td>
                      <td style={{ padding: "8px 12px" }}>
                        <select
                          value={user.role}
                          onChange={e => handleRoleChange(user.id, e.target.value)}
                          disabled={user.id === currentUser?.id}
                          style={{ background: "var(--bg)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 4, padding: "2px 6px" }}
                        >
                          {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                        </select>
                      </td>
                      <td style={{ padding: "8px 12px" }}>
                        {user.id !== currentUser?.id && (
                          <button
                            onClick={() => handleDelete(user)}
                            style={{ color: "var(--danger, #e06c75)", background: "none", border: "none", cursor: "pointer", fontSize: 13 }}
                          >
                            {t("common.delete")}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
      {tab === "custom-fields" && <CustomFieldsAdmin />}
      {tab === "audit-log" && <AuditLogTab currentUser={currentUser} />}
    </div>
  );
}

window.AdminPage = AdminPage;
