// Overview screen — dashboard

function Overview({ onNav }) {
  const { data: D, loading, error } = useInitialData();
  const [insights, setInsights] = React.useState(null);

  React.useEffect(() => {
    fetch('/api/insights', { headers: window.authHeaders() })
      .then(r => r.json())
      .then(setInsights)
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

  return (
    <div className="page fade-in">
      <div className="page-h">
        <div>
          <div className="eyebrow"><span className="dot" /> Workspace · acme/web</div>
          <h1 className="page-title" style={{marginTop:8}}>Good afternoon, Marco.</h1>
          <div className="page-sub">2 runs are active, 1 build is failing on <span className="mono">main</span>, and AI suggested 3 new test cases since yesterday.</div>
        </div>
        <div className="actions">
          <button className="btn"><Icon name="download" /> Export report</button>
          <button className="btn accent"><Icon name="play" /> Start a run</button>
        </div>
      </div>

      {/* Metrics row */}
      <div className="grid grid-4" style={{marginBottom:14}}>
        <Metric label="Pass rate (7d)" value={passRate} delta="+1.8 vs prev 7d" up />
        <Metric label="Open defects" value={openDefects} delta={defectDelta} />
        <Metric label="Total tests" value={totalTests} delta={automationRate + " automated"} up sub="in library" />
        <Metric label="Avg run time" value="12m04" delta="−1m12 vs prev 7d" up />
      </div>

      <div className="grid grid-main" style={{marginBottom:14}}>
        {/* Test health */}
        <div className="card">
          <div className="card-h">
            <div>
              <div className="card-title">Test health</div>
              <div className="card-sub">Last 14 days · 1,284 runs</div>
            </div>
            <div className="spacer" />
            <div className="chip active">All</div>
            <div className="chip">Smoke</div>
            <div className="chip">Regression</div>
            <div className="chip">E2E</div>
          </div>
          <div className="card-b">
            <HealthChart />
            <div style={{display:"flex", gap:18, marginTop:12, fontSize:11.5}}>
              <Legend color="var(--pass)" label="passed" value="1,184" />
              <Legend color="var(--fail)" label="failed" value="62" />
              <Legend color="var(--warn)" label="blocked" value="14" />
              <Legend color="var(--skip)" label="skipped" value="24" />
            </div>
          </div>
        </div>

        {/* AI suggestions */}
        <div className="ai-box">
          <div style={{display:"flex", alignItems:"center", gap:8, marginBottom:10}}>
            <span style={{fontSize:11, fontFamily:"var(--font-mono)", textTransform:"uppercase", letterSpacing:"0.08em", color:"var(--purple)"}}>AI assistant</span>
          </div>
          <div style={{fontSize:13, fontWeight:500, marginBottom:6}}>3 missing edge cases in coupon stacking</div>
          <div style={{fontSize:12, color:"var(--text-muted)", lineHeight:1.5}}>
            I analyzed <span className="mono" style={{color:"var(--text)"}}>src/checkout/coupon.ts</span> against your 11 existing tests in <b>co-coupon</b>. Found 3 branches with no coverage:
          </div>
          <ul style={{margin:"10px 0 12px", padding:"0 0 0 18px", fontSize:12, color:"var(--text-muted)", lineHeight:1.7}}>
            <li>Two percentage coupons applied at once (only one is tested)</li>
            <li>Fixed-amount coupon when subtotal &lt; coupon value</li>
            <li>Coupon expiry race condition during checkout</li>
          </ul>
          <div style={{display:"flex", gap:6}}>
            <button className="btn sm" style={{background:"var(--purple)", borderColor:"var(--purple)", color:"oklch(0.16 0 0)"}}>Generate drafts</button>
            <button className="btn sm">Dismiss</button>
          </div>
        </div>
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
                  <td className="mono dim">{r.started}</td>
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
            <button className="btn sm ghost">Filter</button>
          </div>
          <div style={{padding:"4px 0"}}>
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
                <div className="mono dim" style={{fontSize:10.5, flexShrink:0}}>{a.when}</div>
              </div>
            ))}
          </div>
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

function HealthChart() {
  const days = [
    [82, 4, 0], [88, 2, 1], [91, 1, 0], [76, 6, 2], [89, 3, 0], [94, 1, 0], [86, 5, 1],
    [92, 2, 0], [78, 8, 1], [90, 2, 1], [93, 1, 0], [85, 4, 1], [91, 2, 0], [88, 3, 1],
  ];
  const max = Math.max(...days.map(d => d.reduce((a,b)=>a+b,0)));
  return (
    <div style={{display:"flex", gap:4, alignItems:"flex-end", height:140, padding:"6px 0"}}>
      {days.map((d, i) => {
        const sum = d.reduce((a,b)=>a+b,0);
        const h = (sum/max)*100;
        return (
          <div key={i} style={{flex:1, display:"flex", flexDirection:"column-reverse", height:`${h}%`, minWidth:0, gap:1}}>
            <div style={{background:"var(--pass)", flex: d[0], borderRadius:"2px 2px 0 0"}} />
            {d[1] > 0 && <div style={{background:"var(--fail)", flex: d[1]}} />}
            {d[2] > 0 && <div style={{background:"var(--warn)", flex: d[2]}} />}
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
