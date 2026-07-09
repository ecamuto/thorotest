// ThoroTest — app shell (sidebar + topbar + router)

const { useState, useEffect, useMemo, useRef, useCallback } = React;

function SidebarSearch({ onOpenTest }) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const inputRef = useRef(null);
  const wrapRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    clearTimeout(timerRef.current);
    if (!query.trim()) { setResults([]); setOpen(false); return; }
    timerRef.current = setTimeout(async () => {
      try {
        const token = localStorage.getItem("th_token");
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await fetch(`/api/tests?search=${encodeURIComponent(query.trim())}`, { headers });
        if (!res.ok) return;
        const data = await res.json();
        const q = query.trim().toLowerCase();
        const idMatches = data.filter(t => t.id.toLowerCase().includes(q));
        const titleOnly = data.filter(t => !t.id.toLowerCase().includes(q));
        setResults([...idMatches, ...titleOnly].slice(0, 8));
        setOpen(true);
        setActiveIdx(-1);
      } catch {}
    }, 250);
    return () => clearTimeout(timerRef.current);
  }, [query]);

  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  function selectResult(item) {
    setQuery("");
    setResults([]);
    setOpen(false);
    onOpenTest(item.id);
  }

  function onKeyDown(e) {
    if (e.key === "Escape") { setOpen(false); setQuery(""); inputRef.current?.blur(); return; }
    if (!open || !results.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, results.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)); }
    else if (e.key === "Enter" && activeIdx >= 0) { selectResult(results[activeIdx]); }
  }

  const STATUS_COLOR = { pass: "var(--pass)", fail: "var(--fail)", skip: "var(--warn)", pending: "var(--text-dim)" };

  return (
    <div className="search-wrap" ref={wrapRef}>
      <input
        ref={inputRef}
        className="search-input"
        placeholder={t("nav.search")}
        value={query}
        onChange={e => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => { if (results.length) setOpen(true); }}
        autoComplete="off"
        spellCheck={false}
      />
      {!query && <span className="search-kbd">⌘K</span>}
      {open && results.length > 0 && (
        <div className="search-dropdown">
          {results.map((item, i) => (
            <div
              key={item.id}
              className={"search-result" + (i === activeIdx ? " active" : "")}
              onMouseDown={() => selectResult(item)}
              onMouseEnter={() => setActiveIdx(i)}
            >
              <span className="search-result-dot" style={{ background: STATUS_COLOR[item.status] || "var(--text-dim)" }} />
              <span className="search-result-title">{item.title.length > 22 ? item.title.slice(0, 20) + "…" : item.title}</span>
              <span className="search-result-id">{item.id}</span>
            </div>
          ))}
        </div>
      )}
      {open && query.trim() && results.length === 0 && (
        <div className="search-dropdown">
          <div className="search-no-results">{t("common.noTestsFound")}</div>
        </div>
      )}
    </div>
  );
}

const NAV_CONFIG = [
  { group: "workspace", items: [
    { id: "overview",     icon: "home" },
    { id: "library",      icon: "flask" },
    { id: "requirements", icon: "target" },
    { id: "runs",         icon: "play",    badge: true },
    { id: "pipelines",    icon: "branch" },
    { id: "defects",      icon: "bug" },
    { id: "insights",     icon: "chart" },
    { id: "my-work",      icon: "play" },
  ]},
  { group: "config", items: [
    { id: "settings",     icon: "settings" },
    { id: "admin",        icon: "users",    adminOnly: true },
    { id: "ai",           icon: "sparkle" },
    { id: "integrations", icon: "plug" },
    { id: "import",       icon: "upload" },
    { id: "docs",         icon: "doc" },
  ]},
];

function Sidebar({ current, onNav, onOpenTest, density, currentUser, onLogout }) {
  const { t } = useI18n();
  const [favorites, setFavorites] = useState([]);
  const NotifBell = window.NotificationBell;

  const loadFavorites = useCallback(async () => {
    try {
      const data = await window.TH_API.getFavorites();
      setFavorites(data);
    } catch {}
  }, []);

  useEffect(() => {
    loadFavorites();
    const handler = () => loadFavorites();
    window.addEventListener("favorites-changed", handler);
    return () => window.removeEventListener("favorites-changed", handler);
  }, [loadFavorites]);

  // Filter nav items based on current user role
  const visibleGroups = NAV_CONFIG.map(group => ({
    ...group,
    items: group.items.filter(it => {
      if (it.adminOnly) return currentUser?.role === "admin";
      return true;
    }),
  })).filter(group => group.items.length > 0);

  return (
    <aside className="sidebar">
      <div className="sidebar-brand" onClick={() => onNav("overview")}>
        <div className="brand-mark">T</div>
        <div className="brand-name">ThoroTest</div>
      </div>

      <div className="sidebar-search">
        <SidebarSearch onOpenTest={onOpenTest} />
      </div>

      <nav className="nav">
        {visibleGroups.map((g, gi) => (
          <div className="nav-group" key={gi}>
            <div className="nav-label">
              <span>{g.group === "workspace" ? t("nav.workspace") : t("nav.configure")}</span>
              {g.group === "workspace" && <Icon name="plus" />}
            </div>
            {g.items.map(it => (
              <a
                key={it.id}
                href={`#/${it.id}`}
                className="nav-item"
                aria-current={current === it.id ? "page" : undefined}
                onClick={(e) => { e.preventDefault(); onNav(it.id); }}
              >
                <Icon name={it.icon} className="nav-icon" />
                <span>{t(`nav.${it.id}`)}</span>
                {it.count && <span className="nav-count">{it.count}</span>}
                {it.badge && <span className="nav-dot" />}
              </a>
            ))}
          </div>
        ))}

        {favorites.length > 0 && (
          <div className="nav-group">
            <div className="nav-label"><span>{t("nav.favorites")}</span></div>
            {favorites.map(fav => (
              <div key={fav.folder_id} className="nav-item" onClick={() => onNav("library")}>
                <span style={{width:14, color:"var(--warn)"}}>★</span>
                <span>{fav.name}</span>
                <span className="nav-count">{fav.count}</span>
              </div>
            ))}
          </div>
        )}
      </nav>

      <div className="sidebar-footer">
        <div className="avatar">
          {currentUser ? (currentUser.display_name || currentUser.username).split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase() : "?"}
        </div>
        <div style={{lineHeight:1.15, minWidth:0, flex:1}}>
          <div className="user-name">{currentUser ? (currentUser.display_name || currentUser.username) : "—"}</div>
          <div className="user-org">{currentUser ? currentUser.role : ""}</div>
        </div>
        {NotifBell && <NotifBell currentUser={currentUser} />}
        <button className="btn ghost icon" style={{marginLeft:"auto", flexShrink:0}} title={t("common.signOut")} onClick={onLogout}>
          <Icon name="logout" />
        </button>
      </div>
    </aside>
  );
}

function Topbar({ crumbs, actions, theme, onToggleTheme }) {
  return (
    <div className="topbar">
      <div className="breadcrumb">
        {crumbs.map((c, i) => {
          const isLast = i === crumbs.length - 1;
          const label = typeof c === 'string' ? c : c.label;
          const href = typeof c === 'object' ? c.href : null;
          return (
            <React.Fragment key={i}>
              {i > 0 && <span className="sep">/</span>}
              {isLast ? <b>{label}</b> : href ? <a href={href} className="crumb-link">{label}</a> : <span>{label}</span>}
            </React.Fragment>
          );
        })}
      </div>
      <div className="topbar-right">
        {actions}
        {onToggleTheme && (
          <button className="btn ghost icon sm" onClick={onToggleTheme}
                  title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
                  aria-label="Toggle theme">
            <Icon name={theme === "dark" ? "sun" : "moon"} />
          </button>
        )}
      </div>
    </div>
  );
}

window.Sidebar = Sidebar;
window.Topbar = Topbar;
window.NAV = NAV_CONFIG;
