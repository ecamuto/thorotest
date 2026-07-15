// ThoroTest — NotificationBell component

function NotificationBell({ currentUser }) {
  const { t } = useI18n();
  const [notifications, setNotifications] = React.useState([]);
  const [open, setOpen] = React.useState(false);
  const wrapRef = React.useRef(null);
  const wsRef = React.useRef(null);

  // Unread count — capped at display
  const unreadCount = notifications.filter(n => !n.read).length;
  const badgeLabel = unreadCount > 9 ? "9+" : String(unreadCount);

  // Load initial notifications
  React.useEffect(() => {
    if (!currentUser) return;
    window.TH_API.getNotifications(20).then(data => {
      setNotifications(Array.isArray(data) ? data : []);
    }).catch(() => {});
  }, [currentUser]);

  // WebSocket connection for real-time push
  React.useEffect(() => {
    if (!currentUser) return;
    const token = localStorage.getItem("th_token");
    if (!token) return;
    const ws = window.TH_API.connectNotifWS(token);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      try {
        const notif = JSON.parse(e.data);
        setNotifications(prev => {
          const updated = [notif, ...prev];
          return updated.slice(0, 20); // cap at 20
        });
      } catch {}
    };
    ws.onerror = () => {};
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [currentUser]);

  // Click-outside closes dropdown (same pattern as SidebarSearch)
  React.useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function handleBellClick() {
    setOpen(o => !o);
  }

  function handleMarkAllRead() {
    window.TH_API.markAllNotificationsRead().catch(() => {});
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  }

  function handleNotifClick(notif) {
    if (!notif.read) {
      window.TH_API.markNotificationRead(notif.id).catch(() => {});
      setNotifications(prev => prev.map(n => n.id === notif.id ? { ...n, read: true } : n));
    }
    if (notif.link) {
      location.hash = notif.link.replace(/^#/, "");
    }
    setOpen(false);
  }

  // Relative time helper
  function relativeTime(isoStr) {
    try {
      const diff = Date.now() - new Date(isoStr).getTime();
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return "just now";
      if (mins < 60) return `${mins}m ago`;
      const hrs = Math.floor(mins / 60);
      if (hrs < 24) return `${hrs}h ago`;
      return `${Math.floor(hrs / 24)}d ago`;
    } catch { return ""; }
  }

  // Event type icon (text-based, no SVG dependency)
  function eventIcon(type) {
    if (type === "run_complete") return "✓";
    if (type === "consecutive_fail") return "✗";
    if (type === "comment") return "\u{1F4AC}";
    if (type === "mention") return "@";
    if (type === "assigned") return "\u{1F464}";  // bust in silhouette
    return "•";
  }

  return (
    <div ref={wrapRef} style={{ position: "relative", display: "inline-block" }}>
      {/* Bell button */}
      <button
        className="btn ghost icon"
        title="Notifications"
        onClick={handleBellClick}
        style={{ position: "relative" }}
        aria-label="Notifications"
      >
        {/* Bell icon — inline SVG matching existing Icon component style */}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
        {/* Badge */}
        {unreadCount > 0 && (
          <span style={{
            position: "absolute", top: 2, right: 2,
            background: "var(--accent, #6366f1)", color: "#fff",
            borderRadius: "999px", fontSize: 9, fontWeight: 700,
            minWidth: 14, height: 14, display: "flex",
            alignItems: "center", justifyContent: "center",
            padding: "0 3px", lineHeight: 1,
          }}>
            {badgeLabel}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 6px)", left: 0,
          width: 300, background: "var(--card-bg, #fff)",
          border: "1px solid var(--border, #e5e7eb)",
          borderRadius: 8, boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
          zIndex: 1000, overflow: "hidden",
        }}>
          {/* Header */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 12px", borderBottom: "1px solid var(--border, #e5e7eb)",
          }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>Notifications</span>
            {unreadCount > 0 && (
              <button
                className="btn ghost"
                style={{ fontSize: 11, padding: "2px 6px" }}
                onClick={handleMarkAllRead}
              >
                Mark all read
              </button>
            )}
          </div>

          {/* Notification list */}
          <div style={{ maxHeight: 320, overflowY: "auto" }}>
            {notifications.length === 0 ? (
              <div style={{
                padding: "20px 12px", textAlign: "center",
                color: "var(--muted, #9ca3af)", fontSize: 13,
              }}>
                No notifications
              </div>
            ) : (
              notifications.map(notif => (
                <div
                  key={notif.id}
                  onClick={() => handleNotifClick(notif)}
                  style={{
                    display: "flex", alignItems: "flex-start", gap: 8,
                    padding: "10px 12px", cursor: "pointer",
                    borderBottom: "1px solid var(--border, #f3f4f6)",
                    background: notif.read ? "transparent" : "var(--accent-faint, rgba(99,102,241,0.04))",
                    transition: "background 0.15s",
                  }}
                >
                  {/* Event icon */}
                  <span style={{
                    fontSize: 14, flexShrink: 0, marginTop: 1,
                    color: notif.event_type === "consecutive_fail" ? "var(--fail, #ef4444)" : "var(--accent, #6366f1)",
                  }}>
                    {eventIcon(notif.event_type)}
                  </span>
                  {/* Content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: 13, lineHeight: 1.4,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    }}>
                      {notif.title}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--muted, #9ca3af)", marginTop: 2 }}>
                      {relativeTime(notif.created_at)}
                    </div>
                  </div>
                  {/* Unread dot */}
                  {!notif.read && (
                    <span style={{
                      width: 7, height: 7, borderRadius: "50%",
                      background: "var(--accent, #6366f1)", flexShrink: 0, marginTop: 5,
                    }} />
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

window.NotificationBell = NotificationBell;
