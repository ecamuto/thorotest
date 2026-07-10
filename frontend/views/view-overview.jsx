// Overview screen — dashboard

// "2026-07-04T10:00:00+00:00" → "12m", "8h", "3d"
function timeAgo(iso) {
  if (!iso) return "";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d`;
  return `${Math.floor(s / 86400 / 7)}w`;
}

function Overview({ onNav, currentUser }) {
  const { data: D, loading, error } = useInitialData();
  const [insights, setInsights] = React.useState(null);
  const [health, setHealth] = React.useState(null);

  React.useEffect(() => {
    fetch('/api/insights', { headers: window.authHeaders() })
      .then(r => r.json())
      .then(setInsights)
      .catch(() => {});
    fetch('/api/insights/test-health?days=14', { headers: window.authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(setHealth)
      .catch(() => {});
  }, []);

  if (loading) return (
    <div className="page fade-in">
      <div className="empty">Loading…</div>
    </div>
  );

  if (!D) return (
    <div className="page fade-in">
      <div className="empty">Failed to load data{error ? `: ${error}` : ""}.</div>
    </div>
  );

  const passRate = insights ? `${insights.pass_rate}%` : "—";
  const openDefects = insights ? String(insights.open_defects) : "—";
  const defectDelta = insights
    ? `${insights.open_critical} critical · ${insights.open_high} high`
    : "—";
  const totalTests = insights ? String(insights.total_tests) : "—";
  const automationRate = insights ? `${insights.automation_rate}%` : "—";

  const activeRuns = D.runs.filter(r => r.status === "running").length;
  const failingMain = D.runs.filter(r => r.status === "fail" && r.branch === "main").length;

  const hour = new Date().getHours();
  const daypart = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  const firstName = (currentUser?.display_name || currentUser?.username || "").split(" ")[0];

  const subParts = [];
  subParts.push(activeRuns === 1 ? "1 run is active" : `${activeRuns} runs are active`);
  if (failingMain > 0) subParts.push(<span key="f">{failingMain === 1 ? "1 build is failing" : `${failingMain} builds are failing`} on <span className="mono">main</span></span>);
  if (insights && insights.open_defects > 0) subParts.push(`${insights.open_defects} defects are open`);

  return (
    <div className="page fade-in">
      <div className="page-h">
        <div>
          <div className="eyebrow"><span className="dot" /> Workspace</div>
          <h1 className="page-title" style={{marginTop:8}}>Good {daypart}{firstName ? `, ${firstName}` : ""}.</h1>
          <div className="page-sub">
            {subParts.map((p, i) => <React.Fragment key={i}>{i > 0 && (i === subParts.length - 1 ? " and " : ", ")}{p}</React.Fragment>)}.
          </div>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => TH_API.exportTestsCSV()}><Icon name="download" /> Export report</button>
          <button className="btn accent" onClick={() => onNav("runs")}><Icon name="play" /> Start a run</button>
        </div>
      </div>

      {/* Metrics row */}
      <div className="grid grid-4" style={{marginBottom:14}}>
        <Metric label="Pass rate" value={passRate} delta="of all tests in library" />
        <Metric label="Open defects" value={openDefects} delta={defectDelta} />
        <Metric label="Total tests" value={totalTests} delta={automationRate + " automated"} up sub="in library" />
        <Metric label="Active runs" value={String(activeRuns)} delta={`${D.runs.length} runs total`} />
      </div>

      <RequirementCoverageCard requirements={D.requirements || []} onNav={onNav} />

      <div className="grid grid-main" style={{marginBottom:14}}>
        {/* Test health */}
        <div className="card">
          <div className="card-h">
            <div>
              <div className="card-title">Test health</div>
              <div className="card-sub">
                {health ? `Last 14 days · ${health.total_runs} run${health.total_runs === 1 ? "" : "s"}` : "Last 14 days"}
              </div>
            </div>
            <div className="spacer" />
          </div>
          <div className="card-b">
            <HealthChart health={health} />
            {health && (
              <div style={{display:"flex", gap:18, marginTop:12, fontSize:11.5}}>
                <Legend color="var(--pass)" label="passed" value={health.totals.passed.toLocaleString()} />
                <Legend color="var(--fail)" label="failed" value={health.totals.failed.toLocaleString()} />
                <Legend color="var(--warn)" label="blocked" value={health.totals.blocked.toLocaleString()} />
                <Legend color="var(--skip)" label="skipped" value={health.totals.skipped.toLocaleString()} />
              </div>
            )}
          </div>
        </div>

        {/* AI suggestions */}
        <AiSuggestBox D={D} />
      </div>

      <div className="grid grid-main">
        {/* Active runs */}
        <div className="card">
          <div className="card-h">
            <div className="card-title">Active & recent runs</div>
            <div className="spacer" />
            <button className="btn sm ghost" onClick={() => onNav("runs")}>View all <Icon name="chev" /></button>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th style={{width:90}}>Run</th>
                <th>Plan</th>
                <th style={{width:200}}>Progress</th>
                <th style={{width:90}}>Status</th>
                <th style={{width:80}}>Owner</th>
                <th style={{width:80}}>Started</th>
              </tr>
            </thead>
            <tbody>
              {D.runs.slice(0, 5).map(r => (
                <tr key={r.id} style={{cursor:"pointer"}} onClick={() => onNav("run-detail")}>
                  <td className="mono">{r.id}</td>
                  <td>
                    <div>{r.name}</div>
                    <div className="mono dim" style={{fontSize:10.5}}>{r.branch} · {r.env}</div>
                  </td>
                  <td>
                    <ProgressBar run={r} />
                    <div className="mono dim" style={{fontSize:10.5, marginTop:3}}>{r.passed}/{r.total} passed</div>
                  </td>
                  <td><StatusBadge s={r.status} /></td>
                  <td className="mono dim">{r.owner}</td>
                  <td className="mono dim">{r.created_at ? timeAgo(r.created_at) : r.started}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Activity */}
        <div className="card">
          <div className="card-h">
            <div className="card-title">Activity</div>
            <div className="spacer" />
          </div>
          <div style={{padding:"4px 0"}}>
            {D.activity.length === 0 && <div className="empty" style={{padding:"20px 14px"}}>No activity yet.</div>}
            {D.activity.map((a, i) => (
              <div key={i} style={{display:"flex", gap:10, padding:"10px 14px", borderBottom: i < D.activity.length-1 ? "1px solid var(--border)" : "none"}}>
                <div className="avatar" style={{
                  background: a.who.includes("AI") ? "var(--purple)" : a.who.includes("bot") ? "var(--surface-3)" : undefined,
                  color: a.who.includes("bot") ? "var(--text-muted)" : undefined,
                }}>{a.who.split(" ").map(x=>x[0]).join("").slice(0,2)}</div>
                <div style={{flex:1, minWidth:0, lineHeight:1.4}}>
                  <div style={{fontSize:12}}><b>{a.who}</b> <span className="muted">{a.what}</span> <span className="mono" style={{color:"var(--accent)"}}>{a.target}</span></div>
                  <div style={{fontSize:11.5, color:"var(--text-dim)", marginTop:2}}>{a.detail}</div>
                </div>
                <div className="mono dim" style={{fontSize:10.5, flexShrink:0}}>{a.created_at ? timeAgo(a.created_at) : a.when}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// Compact AI coverage widget — analyzes a folder's tests via /api/ai/suggest-edge-cases
// and can create pending draft tests from the suggestions.
function AiSuggestBox({ D }) {
  // Map every folder id → leaf name and → full ancestor path across the whole
  // tree (any depth). Imported folders nest several levels deep and reuse leaf
  // names (many "extra.spec.ts"), so the picker shows the full path to
  // disambiguate.
  const folderNames = {};
  const folderPaths = {};
  const walkFolders = (list, prefix) => (list || []).forEach(f => {
    const path = prefix ? `${prefix} ‹ ${f.name}` : f.name;
    folderNames[f.id] = f.name;
    folderPaths[f.id] = path;
    walkFolders(f.children, path);
  });
  walkFolders(D.folders, "");

  // Direct test count per folder — matches what the analysis reads (exact
  // folder, no subfolders), so the number reflects what will be sent.
  const folderCounts = {};
  D.tests.forEach(t => { if (t.folder) folderCounts[t.folder] = (folderCounts[t.folder] || 0) + 1; });

  // Only folders that actually have tests, sorted alphabetically by path.
  const folderIds = [...new Set(D.tests.map(t => t.folder).filter(Boolean))]
    .sort((a, b) => (folderPaths[a] || a).localeCompare(folderPaths[b] || b));

  const [folderId, setFolderId] = React.useState(folderIds[0] || "");
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState(null);
  const [result, setResult] = React.useState(null);
  const [creating, setCreating] = React.useState(false);
  const [createdCount, setCreatedCount] = React.useState(0);
  const [selected, setSelected] = React.useState(new Set());

  const analyze = () => {
    setLoading(true); setErr(null); setResult(null); setCreatedCount(0); setSelected(new Set());
    TH_API.suggestEdgeCases({ folder_id: folderId })
      .then(data => {
        setResult(data);
        // pre-select every suggestion; user unticks the ones they don't want
        setSelected(new Set((data?.suggestions || []).map((_, i) => i)));
        setLoading(false);
      })
      .catch(e => { setErr(e.message); setLoading(false); });
  };

  const toggle = (i) => setSelected(s => {
    const n = new Set(s);
    n.has(i) ? n.delete(i) : n.add(i);
    return n;
  });

  const generateDrafts = async () => {
    const picks = (result?.suggestions || []).filter((_, i) => selected.has(i));
    if (!picks.length) return;
    setCreating(true); setErr(null);
    let n = 0;
    try {
      for (const s of picks) {
        await TH_API.createTest({ title: s.title, folder_id: folderId, status: "pending", tags: ["ai-draft"] });
        n++;
      }
      setCreatedCount(n);
    } catch (e) {
      setErr(n > 0 ? `Created ${n} draft${n === 1 ? "" : "s"}, then failed: ${e.message}` : e.message);
      setCreatedCount(n);
    } finally {
      setCreating(false);
    }
  };

  const suggestions = result?.suggestions || [];

  return (
    <div className="ai-box">
      <div style={{display:"flex", alignItems:"center", gap:8, marginBottom:10}}>
        <span style={{fontSize:11, fontFamily:"var(--font-mono)", textTransform:"uppercase", letterSpacing:"0.08em", color:"var(--purple)"}}>AI assistant</span>
      </div>

      {!result && (
        <>
          <div style={{fontSize:13, fontWeight:500, marginBottom:6}}>Find missing edge cases</div>
          <div style={{fontSize:12, color:"var(--text-muted)", lineHeight:1.5, marginBottom:10}}>
            Pick a folder — AI compares its existing tests and suggests uncovered edge cases.
          </div>
          <div style={{display:"flex", gap:6, alignItems:"center"}}>
            <select className="input" style={{flex:1, minWidth:0}} value={folderId} onChange={e => setFolderId(e.target.value)} disabled={loading}>
              {folderIds.map(id => <option key={id} value={id}>{(folderPaths[id] || folderNames[id] || id) + ` (${folderCounts[id] || 0})`}</option>)}
            </select>
            <button className="btn sm" style={{background:"var(--purple)", borderColor:"var(--purple)", color:"oklch(0.16 0 0)"}}
              onClick={analyze} disabled={loading || !folderId}>
              {loading ? "Analyzing…" : "Analyze"}
            </button>
          </div>
        </>
      )}

      {result && (
        <>
          <div style={{fontSize:13, fontWeight:500, marginBottom:6}}>
            {suggestions.length} missing edge case{suggestions.length === 1 ? "" : "s"} in {folderNames[folderId] || folderId}
          </div>
          {suggestions.length === 0 && (
            <div style={{fontSize:12, color:"var(--text-muted)", lineHeight:1.5}}>No gaps found — coverage looks solid.</div>
          )}
          <div style={{margin:"10px 0 12px", display:"flex", flexDirection:"column", gap:6}}>
            {suggestions.map((s, i) => {
              const on = selected.has(i);
              return (
                <label key={i} style={{display:"flex", gap:8, alignItems:"flex-start", padding:"8px 10px", cursor:"pointer",
                  border:"1px solid var(--border)", borderRadius:"var(--radius)",
                  background: on ? "var(--accent-soft)" : "transparent", opacity: createdCount > 0 ? 0.6 : 1}}>
                  <input type="checkbox" checked={on} disabled={createdCount > 0} onChange={() => toggle(i)} style={{marginTop:2}} />
                  <div style={{minWidth:0, flex:1}}>
                    <div style={{display:"flex", gap:6, alignItems:"center", flexWrap:"wrap"}}>
                      <span style={{fontSize:12.5, fontWeight:500, color:"var(--text)"}}>{s.title}</span>
                      {s.category && <span className="tag" style={{fontSize:10, textTransform:"uppercase", letterSpacing:"0.04em"}}>{s.category}</span>}
                    </div>
                    {s.rationale && <div style={{fontSize:11.5, color:"var(--text-muted)", lineHeight:1.5, marginTop:2}}>{s.rationale}</div>}
                  </div>
                </label>
              );
            })}
          </div>
          <div style={{display:"flex", gap:6}}>
            {suggestions.length > 0 && createdCount === 0 && (
              <button className="btn sm" style={{background:"var(--purple)", borderColor:"var(--purple)", color:"oklch(0.16 0 0)"}}
                onClick={generateDrafts} disabled={creating || selected.size === 0}>
                {creating ? "Creating…" : `Create ${selected.size} selected`}
              </button>
            )}
            {createdCount > 0 && (
              <span style={{fontSize:12, color:"var(--pass)", alignSelf:"center"}}>✓ Created {createdCount} draft{createdCount === 1 ? "" : "s"}</span>
            )}
            <button className="btn sm" onClick={() => { setResult(null); setErr(null); setCreatedCount(0); }}>Dismiss</button>
          </div>
        </>
      )}

      {err && <div style={{fontSize:12, color:"var(--fail)", marginTop:10}}>{err}</div>}
    </div>
  );
}

function RequirementCoverageCard({ requirements, onNav }) {
  if (!requirements || requirements.length === 0) return null;
  const total = requirements.length;
  const covered = requirements.filter(r => r.coverage && r.coverage.linked > 0).length;
  const atRisk = requirements.filter(r => r.coverage && r.coverage.failed > 0).length;
  const uncovered = total - covered;
  const coveredPct = Math.round((covered / total) * 100);

  return (
    <div className="card" style={{marginBottom:14, cursor:"pointer"}} onClick={() => onNav && onNav("requirements")}>
      <div className="card-h">
        <div>
          <div className="card-title">Requirement coverage</div>
          <div className="card-sub">{covered} of {total} requirements have at least one test</div>
        </div>
        <div className="card-title" style={{fontSize:22, color: coveredPct === 100 ? "var(--pass)" : coveredPct >= 60 ? "var(--warn)" : "var(--fail)"}}>{coveredPct}%</div>
      </div>
      <div className="card-b">
        <div style={{height:10, borderRadius:5, overflow:"hidden", display:"flex", background:"var(--bg-3)", marginBottom:10}}>
          {covered > 0 && <div style={{width:`${(covered/total)*100}%`, background:"var(--pass)"}} />}
          {uncovered > 0 && <div style={{width:`${(uncovered/total)*100}%`, background:"var(--text-dim)"}} />}
        </div>
        <div style={{display:"flex", gap:18}}>
          <Legend color="var(--pass)" label="Covered" value={covered} />
          <Legend color="var(--text-dim)" label="Uncovered" value={uncovered} />
          <Legend color="var(--fail)" label="At risk (failing)" value={atRisk} />
        </div>
      </div>
    </div>
  );
}

function Metric({label, value, delta, up, down, sub}) {
  return (
    <div className="card metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className={"metric-delta" + (up ? " up" : down ? " down" : "")}>
        {up && "▲ "}{down && "▼ "}{delta}
      </div>
      {sub && <div className="dim mono" style={{fontSize:10.5, marginTop:2}}>{sub}</div>}
    </div>
  );
}

function Legend({color, label, value}) {
  return (
    <div style={{display:"flex", alignItems:"center", gap:6}}>
      <span style={{width:8, height:8, background:color, borderRadius:2, display:"inline-block"}} />
      <span className="muted">{label}</span>
      <span className="mono">{value}</span>
    </div>
  );
}

function StatusBadge({s}) {
  if (s === "running") return <span className="status info">RUNNING</span>;
  if (s === "pass") return <span className="status pass">PASS</span>;
  if (s === "fail") return <span className="status fail">FAIL</span>;
  if (s === "warn" || s === "blocked") return <span className="status warn">BLOCKED</span>;
  if (s === "skip") return <span className="status skip">SKIP</span>;
  if (s === "pending") return <span className="status skip">PENDING</span>;
  return <span className="status">{s}</span>;
}

function ProgressBar({run}) {
  const total = run.total;
  const segs = [
    { cls: "seg-pass", v: run.passed },
    { cls: "seg-fail", v: run.failed },
    { cls: "seg-warn", v: run.blocked },
  ];
  const used = segs.reduce((a,b)=>a+b.v,0);
  const rem = total - used;
  return (
    <div className="bar">
      {segs.map((s, i) => s.v > 0 && <span key={i} className={s.cls} style={{width: `${(s.v/total)*100}%`}} />)}
      {rem > 0 && <span style={{width: `${(rem/total)*100}%`, background:"var(--surface-3)"}} />}
    </div>
  );
}

function HealthChart({ health }) {
  if (!health) return <div className="empty" style={{height:140, display:"flex", alignItems:"center", justifyContent:"center"}}>Loading…</div>;
  const days = health.days || [];
  if (health.total_runs === 0) {
    return <div className="empty" style={{height:140, display:"flex", alignItems:"center", justifyContent:"center"}}>No runs in the last 14 days.</div>;
  }
  const max = Math.max(...days.map(d => d.passed + d.failed + d.blocked + d.skipped), 1);
  return (
    <div style={{display:"flex", gap:4, alignItems:"flex-end", height:140, padding:"6px 0"}}>
      {days.map((d, i) => {
        const sum = d.passed + d.failed + d.blocked + d.skipped;
        const h = (sum/max)*100;
        return (
          <div key={d.date} title={`${d.date} — ${d.passed} passed, ${d.failed} failed, ${d.blocked} blocked, ${d.skipped} skipped`}
            style={{flex:1, display:"flex", flexDirection:"column-reverse", height:`${Math.max(h, sum > 0 ? 3 : 0)}%`, minWidth:0, gap:1}}>
            {d.passed > 0 && <div style={{background:"var(--pass)", flex: d.passed, borderRadius:"2px 2px 0 0"}} />}
            {d.failed > 0 && <div style={{background:"var(--fail)", flex: d.failed}} />}
            {d.blocked > 0 && <div style={{background:"var(--warn)", flex: d.blocked}} />}
            {d.skipped > 0 && <div style={{background:"var(--skip)", flex: d.skipped}} />}
          </div>
        );
      })}
    </div>
  );
}

const STATUS_OPTIONS = ["pass", "fail", "warn", "skip", "pending"];

function StatusSelect({ s, testId, onChanged }) {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState(s);

  React.useEffect(() => { setCurrent(s); }, [s]);

  const handleSelect = async (st) => {
    setOpen(false);
    if (st === current) return;
    const prev = current;
    setCurrent(st);
    try {
      // Route through TH_API so the Authorization header is attached — a raw
      // fetch here omits the Bearer token and the PATCH is rejected with 401.
      await window.TH_API.updateTestStatus(testId, st);
      onChanged && onChanged(st);
    } catch (e) {
      setCurrent(prev);
    }
  };

  return (
    <div style={{ position: "relative", display: "inline-flex" }}>
      <div style={{ cursor: "pointer" }} onClick={(e) => { e.stopPropagation(); setOpen(o => !o); }}>
        <StatusBadge s={current} />
      </div>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 99 }} onClick={(e) => { e.stopPropagation(); setOpen(false); }} />
          <div style={{ position: "absolute", top: "100%", left: 0, zIndex: 100, background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", minWidth: 110, marginTop: 4, boxShadow: "0 4px 12px rgba(0,0,0,0.3)", overflow: "hidden" }}>
            {STATUS_OPTIONS.map(st => (
              <div key={st} style={{ padding: "7px 12px", cursor: "pointer", background: st === current ? "var(--accent-soft)" : "transparent" }}
                onClick={(e) => { e.stopPropagation(); handleSelect(st); }}>
                <StatusBadge s={st} />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

window.Overview = Overview;
window.StatusBadge = StatusBadge;
window.StatusSelect = StatusSelect;
window.ProgressBar = ProgressBar;
window.Metric = Metric;
window.timeAgo = timeAgo;
