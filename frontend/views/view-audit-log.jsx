// ThoroTest — Audit Log tab (rendered inside AdminPage)
// Exposed as window.AuditLogTab for use by view-admin.jsx

function AuditLogTab({ currentUser }) {
  const PAGE_SIZE = 50;

  // Filter state
  const today = new Date().toISOString().slice(0, 10);
  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

  const [startDate, setStartDate] = React.useState(sevenDaysAgo);
  const [endDate, setEndDate]     = React.useState(today);
  const [page, setPage]           = React.useState(1);
  const [data, setData]           = React.useState(null);   // { entries, total, page, page_size }
  const [loading, setLoading]     = React.useState(true);
  const [error, setError]         = React.useState(null);

  const load = React.useCallback(async (p = 1) => {
    setLoading(true);
    setError(null);
    try {
      const result = await window.TH_API.getAuditLog({
        start_date: startDate,
        end_date: endDate,
        page: p,
        page_size: PAGE_SIZE,
      });
      setData(result);
      setPage(p);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate]);

  // Load on mount and whenever filter changes
  React.useEffect(() => { load(1); }, [load]);

  const applyPreset = (preset) => {
    const now = new Date();
    const end = now.toISOString().slice(0, 10);
    if (preset === "24h") {
      setStartDate(new Date(now - 24 * 60 * 60 * 1000).toISOString().slice(0, 10));
    } else if (preset === "7d") {
      setStartDate(new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10));
    } else if (preset === "30d") {
      setStartDate(new Date(now - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10));
    }
    setEndDate(end);
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  const formatTs = (iso) => {
    if (!iso) return "—";
    // Display as absolute UTC: 2026-06-11 14:23:01 UTC
    return iso.replace("T", " ").replace(/\.\d+Z?$/, "").replace("Z", "") + " UTC";
  };

  const outcomeStyle = (outcome) => ({
    color: outcome === "fail" ? "var(--danger, #e06c75)" : "inherit",
    fontWeight: outcome === "fail" ? 600 : 400,
  });

  return (
    <div>
      {/* Filter bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <button className="btn ghost sm" onClick={() => applyPreset("24h")}>Last 24h</button>
        <button className="btn ghost sm" onClick={() => applyPreset("7d")}>Last 7 days</button>
        <button className="btn ghost sm" onClick={() => applyPreset("30d")}>Last 30 days</button>
        <span style={{ color: "var(--text-muted)", fontSize: 12, margin: "0 4px" }}>or</span>
        <input
          type="date"
          value={startDate}
          max={endDate}
          onChange={e => setStartDate(e.target.value)}
          style={{ fontSize: 13, padding: "3px 6px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)" }}
        />
        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>to</span>
        <input
          type="date"
          value={endDate}
          min={startDate}
          max={today}
          onChange={e => setEndDate(e.target.value)}
          style={{ fontSize: 13, padding: "3px 6px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)" }}
        />
      </div>

      {/* Status */}
      {loading && <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading...</div>}
      {error && <div style={{ color: "var(--danger, #e06c75)", fontSize: 13 }}>Error: {error}</div>}

      {/* Table */}
      {!loading && !error && data && (
        <>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
            {data.total} {data.total === 1 ? "entry" : "entries"}
            {totalPages > 1 && ` — page ${page} of ${totalPages}`}
          </div>

          {data.entries.length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "20px 0" }}>No audit entries for this period.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Timestamp", "Actor", "Description", "Target"].map(h => (
                      <th key={h} style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.entries.map(e => (
                    <tr key={e.id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "5px 10px", whiteSpace: "nowrap", color: "var(--text-muted)" }}>{formatTs(e.occurred_at)}</td>
                      <td style={{ padding: "5px 10px", whiteSpace: "nowrap" }}>{e.actor_email}</td>
                      <td style={{ padding: "5px 10px", ...outcomeStyle(e.outcome) }}>{e.description}</td>
                      <td style={{ padding: "5px 10px", color: "var(--text-muted)" }}>
                        {e.target_type && e.target_id ? `${e.target_type}:${e.target_id}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: "flex", gap: 6, marginTop: 12, alignItems: "center" }}>
              <button
                className="btn ghost sm"
                onClick={() => load(page - 1)}
                disabled={page <= 1}
              >← Prev</button>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{page} / {totalPages}</span>
              <button
                className="btn ghost sm"
                onClick={() => load(page + 1)}
                disabled={page >= totalPages}
              >Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

window.AuditLogTab = AuditLogTab;
