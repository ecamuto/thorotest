// Runs & plans view, plus Run detail (live execution)

function Runs({ onOpenRun, currentUser }) {
  const { data: D, loading, error } = useInitialData();
  const [tab, setTab] = useState("active");
  const [showNewRun, setShowNewRun] = React.useState(false);
  const [showNewPlan, setShowNewPlan] = React.useState(false);
  const [plans, setPlans] = React.useState([]);

  const loadPlans = React.useCallback(() => {
    window.TH_API.listPlans().then(setPlans).catch(() => setPlans([]));
  }, []);
  React.useEffect(() => { loadPlans(); }, [loadPlans]);

  if (loading) return (
    <div style={{display:"flex", height:"100%", alignItems:"center", justifyContent:"center"}}>
      <span className="mono dim">Loading…</span>
    </div>
  );

  if (!D) return (
    <div style={{display:"flex", height:"100%", alignItems:"center", justifyContent:"center"}}>
      <span className="mono dim">Error loading data{error ? `: ${error}` : ""}.</span>
    </div>
  );

  const activeCount = D.runs.filter(r => r.status === "running").length;

  return (
    <div style={{display:"flex", flexDirection:"column", height:"100%"}}>
      <div className="page-h" style={{padding:"18px 22px 0", marginBottom:14}}>
        <div>
          <h1 className="page-title">Runs & plans</h1>
          <div className="page-sub">Execute test plans manually or trigger from CI — one timeline for both.</div>
        </div>
        <div className="actions">
          {window.can && window.can(currentUser, "write") && (
            <button className="btn" onClick={() => setShowNewPlan(true)}><Icon name="plus" /> New plan</button>
          )}
          {window.can && window.can(currentUser, "write") && (
            <button className="btn accent" onClick={() => setShowNewRun(true)}><Icon name="play" /> Start run</button>
          )}
        </div>
      </div>

      <div className="tabs" style={{paddingLeft:22}}>
        <div className={"tab" + (tab === "active" ? " active" : "")} onClick={() => setTab("active")}>Active <span className="count">{activeCount}</span></div>
        <div className={"tab" + (tab === "history" ? " active" : "")} onClick={() => setTab("history")}>History <span className="count">{D.runs.length}</span></div>
        <div className={"tab" + (tab === "plans" ? " active" : "")} onClick={() => setTab("plans")}>Test plans <span className="count">{plans.length}</span></div>
      </div>

      <div style={{overflowY:"auto", flex:1, padding:"14px 22px 32px"}}>
        {tab === "plans"
          ? <PlansList plans={plans} onReload={loadPlans} onOpenRun={onOpenRun} currentUser={currentUser} onNewPlan={() => setShowNewPlan(true)} />
          : <RunsList runs={D.runs} onOpenRun={onOpenRun} active={tab === "active"} />}
      </div>

      {showNewRun && window.can && window.can(currentUser, "write") && (
        <NewRunModal
          onClose={() => setShowNewRun(false)}
          onCreated={(id) => { setShowNewRun(false); onOpenRun(id); }}
        />
      )}

      {showNewPlan && window.can && window.can(currentUser, "write") && (
        <NewPlanModal
          onClose={() => setShowNewPlan(false)}
          onCreated={() => { setShowNewPlan(false); setTab("plans"); loadPlans(); }}
        />
      )}
    </div>
  );
}

function RunsList({runs, onOpenRun, active}) {
  const rows = active ? runs.filter(r => r.status === "running") : runs;

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th style={{width:90}}>Run</th>
            <th>Plan</th>
            <th style={{width:220}}>Progress</th>
            <th style={{width:120}}>Result</th>
            <th style={{width:90}}>Env</th>
            <th style={{width:140}}>Branch</th>
            <th style={{width:80}}>Owner</th>
            <th style={{width:90}}>Started</th>
            <th style={{width:40}}></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id} style={{cursor:"pointer"}} onClick={() => onOpenRun(r.id)}>
              <td className="mono">{r.id}</td>
              <td>
                <div>{r.name}</div>
                {r.owner && <div className="mono dim" style={{fontSize:10.5}}>{r.owner}</div>}
              </td>
              <td>
                <ProgressBar run={r} />
                <div className="mono dim" style={{fontSize:10.5, marginTop:3}}>
                  {r.passed}/{r.total} · {r.failed} fail · {r.blocked} blocked
                </div>
              </td>
              <td><StatusBadge s={r.status} /></td>
              <td><span className="tag">{r.env}</span></td>
              <td className="mono dim">{r.branch}</td>
              <td className="mono dim">{r.owner}</td>
              <td className="mono dim">{r.started}</td>
              <td><button className="btn ghost icon sm"><Icon name="more" /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PlansList({ plans, onReload, onOpenRun, currentUser, onNewPlan }) {
  const [busy, setBusy] = React.useState(null);   // plan id currently running/deleting
  const canWrite = window.can && window.can(currentUser, "write");

  const runPlan = async (p) => {
    setBusy(p.id);
    try {
      const run = await window.TH_API.runPlan(p.id);
      onOpenRun(run.id);
    } catch (e) {
      alert(e.message);
      setBusy(null);
    }
  };

  const deletePlan = async (p) => {
    if (!window.confirm(`Delete plan "${p.name}"?`)) return;
    setBusy(p.id);
    try {
      await window.TH_API.deletePlan(p.id);
      onReload();
    } catch (e) {
      alert(e.message);
    }
    setBusy(null);
  };

  if (!plans.length) {
    return (
      <div className="empty" style={{padding:"48px 18px", textAlign:"center"}}>
        <div style={{fontSize:13, marginBottom:6}}>No test plans yet.</div>
        <div className="mono dim" style={{fontSize:11, marginBottom:16}}>
          A plan is a reusable set of tests you run on demand.
        </div>
        {canWrite && <button className="btn accent" onClick={onNewPlan}><Icon name="plus" /> New plan</button>}
      </div>
    );
  }

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th style={{width:110}}>ID</th>
            <th>Name</th>
            <th style={{width:70}}>Tests</th>
            <th style={{width:100}}>Env</th>
            <th style={{width:90}}>Owner</th>
            <th>Schedule</th>
            <th style={{width:150}}></th>
          </tr>
        </thead>
        <tbody>
          {plans.map(p => (
            <tr key={p.id}>
              <td className="mono">{p.id}</td>
              <td>{p.name}</td>
              <td className="mono">{(p.test_ids || []).length}</td>
              <td>{p.env ? <span className="tag">{p.env}</span> : <span className="mono dim">—</span>}</td>
              <td className="mono dim">{p.owner || "—"}</td>
              <td className="mono dim">{p.schedule || "Manual"}</td>
              <td style={{textAlign:"right", whiteSpace:"nowrap"}}>
                {canWrite && (
                  <>
                    <button
                      className="btn sm accent"
                      disabled={busy === p.id || !(p.test_ids || []).length}
                      onClick={() => runPlan(p)}
                    >
                      <Icon name="play" /> {busy === p.id ? "…" : "Run"}
                    </button>
                    <button
                      className="btn sm ghost icon"
                      style={{marginLeft:6}}
                      disabled={busy === p.id}
                      onClick={() => deletePlan(p)}
                      title="Delete plan"
                    >
                      <Icon name="x" />
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunDetail({ runId, onBack, currentUser }) {
  const [liveRun, setLiveRun] = React.useState(null);
  const [cases, setCases] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [activeIdx, setActiveIdx] = useState(0);
  const [stepResult, setStepResult] = useState({});
  const [runDefects, setRunDefects] = useState([]);
  const [showFileDefect, setShowFileDefect] = useState(false);
  const [stepData, setStepData] = React.useState([]);   // [{test_step: {action, expected_result}, ...StepResultOut}]
  const [stepResults, setStepResults] = React.useState([]);   // StepResultOut[] from API
  const [testSteps, setTestSteps] = React.useState([]);       // TestStepOut[] for action text
  const [attachments, setAttachments] = React.useState([]);
  const [markingStep, setMarkingStep] = React.useState(false);
  const [users, setUsers] = React.useState([]);
  const [retesting, setRetesting] = React.useState(false);
  const [exportOpen, setExportOpen] = React.useState(false);
  const [exporting, setExporting] = React.useState(false);

  // Load users list for assignment dropdown
  React.useEffect(() => {
    if (!window.can || !window.can(currentUser, "manage")) return;
    fetch("/api/users", { headers: { Authorization: `Bearer ${localStorage.getItem("th_token")}` } })
      .then(r => r.json())
      .then(setUsers)
      .catch(() => {});
  }, [currentUser]);

  // Load run + cases from API
  React.useEffect(() => {
    const id = runId || "R-1287";
    setLoading(true);
    fetch(`/api/runs/${id}`, { headers: window.authHeaders() })
      .then(r => { if (!r.ok) throw new Error("not found"); return r.json(); })
      .then(data => {
        setLiveRun(data);
        const apiCases = data.cases || [];
        setCases(apiCases);
        const firstActive = apiCases.findIndex(c => c.status === "running" || c.status === "pending");
        setActiveIdx(firstActive >= 0 ? firstActive : 0);
        setLoading(false);
      })
      .catch(() => {
        const D = window.TH_DATA;
        const fallback = D?.runs.find(r => r.id === id) || D?.runs[0];
        if (fallback) {
          setLiveRun(fallback);
          setCases([]);
        }
        setLoading(false);
      });
  }, [runId]);

  // Load defects for this run
  React.useEffect(() => {
    if (!runId) return;
    TH_API.getRunDefects(runId)
      .then(setRunDefects)
      .catch(() => {});
  }, [runId]);

  // Load step definitions and step results for active case
  React.useEffect(() => {
    const c = cases[activeIdx];
    if (!c || !c.test_id) return;
    setStepResults([]);
    setTestSteps([]);
    // Load test step definitions (action text)
    TH_API.getTestSteps(c.test_id)
      .then(setTestSteps)
      .catch(() => {});
    // Load step results for this run case
    if (c.id && liveRun?.id) {
      TH_API.getStepResults(liveRun.id, c.id)
        .then(setStepResults)
        .catch(() => {});
      // Load attachments for run case
      TH_API.getAttachments("run_case", String(c.id))
        .then(setAttachments)
        .catch(() => {});
    }
  }, [activeIdx, cases, liveRun?.id]);

  // WebSocket — live run updates
  React.useEffect(() => {
    if (!liveRun || liveRun.status !== "running" || !window.TH_API) return;
    let ws;
    try {
      ws = window.TH_API.connectRunWS(liveRun.id);
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.event === "step") {
          setLiveRun(prev => ({
            ...prev,
            progress: msg.progress,
            passed: msg.passed,
            failed: msg.failed,
            blocked: msg.blocked,
          }));
          setCases(prev => prev.map(c =>
            c.test_id === msg.testId ? { ...c, status: msg.status } : c
          ));
        } else if (msg.event === "complete") {
          setLiveRun(prev => ({ ...prev, status: msg.status, progress: 100,
            passed: msg.passed, failed: msg.failed, blocked: msg.blocked }));
        } else if (msg.event === "state") {
          setLiveRun(prev => ({ ...prev, ...msg }));
        }
      };
    } catch (_) {}
    return () => { if (ws) ws.close(); };
  }, [liveRun?.id, liveRun?.status]);

  const handlePause = async () => {
    try {
      await window.TH_API.updateRunStatus(liveRun.id, "paused");
      setLiveRun(prev => ({ ...prev, status: "paused" }));
    } catch (_) {}
  };

  const handleAbort = async () => {
    if (!confirm("Abort this run?")) return;
    try {
      await window.TH_API.updateRunStatus(liveRun.id, "aborted");
      setLiveRun(prev => ({ ...prev, status: "aborted" }));
    } catch (_) {}
  };

  const handleRetest = async () => {
    if (retesting) return;
    setRetesting(true);
    try {
      const newRun = await window.TH_API.retestRun(liveRun.id);
      window.location.hash = `#/runs/${newRun.id}`;
    } catch(e) {
      setRetesting(false);
    }
  };

  const handleExport = async (fmt) => {
    setExportOpen(false);
    setExporting(true);
    try {
      if (fmt === "csv") await window.TH_API.exportRunCSV(liveRun.id);
      else await window.TH_API.exportRunPDF(liveRun.id);
    } catch (_) {}
    setExporting(false);
  };

  const markStep = async (stepResult, newStatus) => {
    const c = cases[activeIdx];
    if (!c || !liveRun) return;
    setMarkingStep(true);
    try {
      const updated = await TH_API.updateStepResult(
        liveRun.id, c.id, stepResult.test_step_id,
        { status: newStatus, actual_result: stepResult.actual_result || null }
      );
      setStepResults(prev => prev.map(sr =>
        sr.test_step_id === updated.test_step_id ? updated : sr
      ));
      // Auto-advance to next pending step after marking
      if (newStatus === "pass" || newStatus === "fail") {
        const currentStepIdx = stepResults.findIndex(sr => sr.test_step_id === stepResult.test_step_id);
        const nextPending = stepResults.findIndex((sr, i) => i > currentStepIdx && sr.status === "pending");
        // (No UI advance needed — tester sees all steps highlighted by status)
      }
    } catch (e) {}
    setMarkingStep(false);
  };

  React.useEffect(() => {
    function onKey(e) {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (!stepResults.length) return;
      const firstPending = stepResults.find(sr => sr.status === "pending");
      if (!firstPending) return;
      if (e.key === "p" || e.key === "P") markStep(firstPending, "pass");
      if (e.key === "f" || e.key === "F") markStep(firstPending, "fail");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stepResults, activeIdx]);

  if (loading) return (
    <div style={{display:"flex", height:"100%", alignItems:"center", justifyContent:"center"}}>
      <span className="mono dim">Loading run…</span>
    </div>
  );

  if (!liveRun) return (
    <div style={{display:"flex", height:"100%", alignItems:"center", justifyContent:"center"}}>
      <span className="mono dim">Run not found.</span>
    </div>
  );

  const run = liveRun;
  const current = cases[activeIdx] || cases[0];
  const passCount = cases.filter(c => c.status === "pass").length;
  const failCount = cases.filter(c => c.status === "fail" || c.status === "blocked").length;

  return (
    <div style={{display:"grid", gridTemplateColumns:"320px 1fr 360px", height:"100%", overflow:"hidden"}}>
      {/* Left — queue */}
      <div style={{borderRight:"1px solid var(--border)", background:"var(--bg-2)", display:"flex", flexDirection:"column", overflow:"hidden"}}>
        <div style={{padding:"14px 14px 10px", borderBottom:"1px solid var(--border)"}}>
          <div style={{display:"flex", alignItems:"center", gap:8, fontSize:11.5, color:"var(--text-dim)", marginBottom:6}}>
            <button className="btn ghost sm" onClick={onBack} style={{padding:"2px 6px"}}>← Runs</button>
            <span className="mono">{run.id}</span>
            <StatusBadge s={run.status} />
          </div>
          <div style={{fontSize:14, fontWeight:600, lineHeight:1.3}}>{run.name}</div>
          {run.source_run_id && (
            <div style={{fontSize:11, color:"var(--text-dim)", marginTop:2}}>
              Retest of: <a href={`#/runs/${run.source_run_id}`}
                style={{color:"var(--accent)", textDecoration:"none"}}
                onClick={e => { e.preventDefault(); e.stopPropagation(); window.location.hash = `#/runs/${run.source_run_id}`; }}>
                {run.source_run_id}
              </a>
            </div>
          )}
          <div className="mono dim" style={{fontSize:11, marginTop:4}}>{run.branch} · {run.env}</div>
          <ProgressBar run={run} />
          <div style={{display:"flex", justifyContent:"space-between", marginTop:6, fontSize:10.5}} className="mono">
            <span style={{color:"var(--pass)"}}>✓ {passCount}</span>
            <span style={{color:"var(--fail)"}}>× {failCount}</span>
            <span className="dim">○ {cases.length - passCount - failCount}</span>
          </div>
          {window.can && window.can(currentUser, "write") && (run.status === "fail" || run.status === "completed") && failCount > 0 && (
            <button
              className="btn sm accent"
              style={{marginTop:6, width:"100%"}}
              onClick={handleRetest}
              disabled={retesting}
            >
              {retesting ? "Creating retest…" : `Retest failed (${failCount})`}
            </button>
          )}
          <div style={{position:"relative", marginTop:6}}>
            <button
              className="btn sm"
              onClick={() => setExportOpen(o => !o)}
              disabled={exporting}
              style={{width:"100%"}}
            >
              {exporting ? "Exporting…" : "Export ▾"}
            </button>
            {exportOpen && (
              <>
                <div
                  style={{position:"fixed", inset:0, zIndex:99}}
                  onClick={() => setExportOpen(false)}
                />
                <div style={{
                  position:"absolute", top:"100%", left:0, zIndex:100,
                  background:"var(--bg-2)", border:"1px solid var(--border)",
                  borderRadius:"var(--radius)", minWidth:120, marginTop:4,
                  boxShadow:"0 4px 12px rgba(0,0,0,0.3)", overflow:"hidden"
                }}>
                  <div
                    style={{padding:"8px 12px", cursor:"pointer", fontSize:12}}
                    onClick={() => handleExport("csv")}
                  >CSV</div>
                  <div
                    style={{padding:"8px 12px", cursor:"pointer", fontSize:12}}
                    onClick={() => handleExport("pdf")}
                  >PDF</div>
                </div>
              </>
            )}
          </div>
        </div>
        <div style={{overflowY:"auto", flex:1, padding:"6px 0"}}>
          {cases.length === 0 && (
            <div className="empty" style={{padding:"20px 14px", fontSize:12}}>No cases in this run.</div>
          )}
          {cases.map((c, i) => (
            <div
              key={c.id}
              onClick={() => setActiveIdx(i)}
              style={{
                display:"grid",
                gridTemplateColumns: (window.can && window.can(currentUser, "manage"))
                  ? "20px 1fr 50px 90px" : "20px 1fr 50px",
                gap:8,
                alignItems:"center",
                padding:"7px 14px",
                cursor:"pointer",
                background: i === activeIdx ? "var(--surface-2)" : "transparent",
                borderLeft: i === activeIdx ? "2px solid var(--accent)" : "2px solid transparent",
                fontSize:12,
              }}
            >
              <div style={{
                width:16, height:16, borderRadius:"50%",
                display:"grid", placeItems:"center",
                background:
                  c.status === "pass" ? "var(--pass-soft)" :
                  c.status === "fail" ? "var(--fail-soft)" :
                  c.status === "running" ? "var(--accent-soft)" : "var(--surface-2)",
                color:
                  c.status === "pass" ? "var(--pass)" :
                  c.status === "fail" ? "var(--fail)" :
                  c.status === "running" ? "var(--accent)" : "var(--text-dim)",
                fontSize:9,
                fontFamily:"var(--font-mono)"
              }}>
                {c.status === "pass" ? "✓" : c.status === "fail" ? "✕" : c.status === "running" ? "▶" : i+1}
              </div>
              <div style={{minWidth:0}}>
                <div style={{fontSize:12, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{c.title || c.test_id}</div>
                <div className="mono dim" style={{fontSize:10}}>{c.test_id}</div>
              </div>
              <div className="mono dim" style={{fontSize:10, textAlign:"right"}}>{c.duration || "—"}</div>
              {window.can && window.can(currentUser, "manage") && (
                <select
                  className="input"
                  style={{fontSize:10.5, padding:"1px 4px", width:90}}
                  value={c.assigned_to || ""}
                  onChange={e => {
                    e.stopPropagation();
                    const val = e.target.value || null;
                    window.TH_API.assignCase(liveRun.id, c.id, val)
                      .then(updated => {
                        setCases(prev => prev.map(x => x.id === c.id ? {...x, assigned_to: updated.assigned_to} : x));
                      })
                      .catch(() => {});
                  }}
                  onClick={e => e.stopPropagation()}
                >
                  <option value="">Unassigned</option>
                  {users.map(u => (
                    <option key={u.id} value={u.username}>{u.display_name || u.username}</option>
                  ))}
                </select>
              )}
            </div>
          ))}
        </div>
        {window.can && window.can(currentUser, "write") && (
          <div style={{padding:"10px 14px", borderTop:"1px solid var(--border)", display:"flex", gap:6}}>
            <button className="btn sm" style={{flex:1}} onClick={handlePause} disabled={run.status !== "running"}>Pause</button>
            <button className="btn sm" style={{flex:1, color:"var(--fail)"}} onClick={handleAbort} disabled={run.status === "aborted"}>Abort</button>
          </div>
        )}
      </div>

      {/* Middle — current test */}
      <div style={{display:"flex", flexDirection:"column", overflow:"hidden"}}>
        {current ? (
          <>
            <div style={{padding:"18px 22px 12px", borderBottom:"1px solid var(--border)"}}>
              <div style={{display:"flex", alignItems:"center", gap:10, marginBottom:6}}>
                <span className="mono dim" style={{fontSize:11}}>Case {activeIdx + 1} of {cases.length}</span>
                <StatusBadge s={current.status} />
                <div className="spacer" />
                {window.can && window.can(currentUser, "write") && (
                  <>
                    <button className="btn sm">Skip</button>
                    <button className="btn sm" style={{color:"var(--warn)"}}>Block</button>
                  </>
                )}
              </div>
              <h2 style={{fontSize:18, fontWeight:600, margin:"0 0 4px", letterSpacing:"-0.01em"}}>{current.title || current.test_id}</h2>
              <div style={{fontSize:11.5, color:"var(--text-muted)"}}>
                <span className="mono">{current.test_id}</span>
              </div>
            </div>

            <div style={{flex:1, overflowY:"auto"}}>
              <div className="card" style={{margin:"14px 22px", borderRadius:"var(--radius-lg)"}}>
                <div className="card-h">
                  <div className="card-title">Steps</div>
                  <div className="spacer" />
                  {testSteps.length > 0 && (
                    <div className="mono dim" style={{fontSize:11}}>
                      {stepResults.filter(sr => sr.status !== "pending").length} / {testSteps.length} done
                    </div>
                  )}
                </div>
                {testSteps.length === 0 ? (
                  <div className="mono dim" style={{padding:"14px", fontSize:12}}>
                    No steps defined for this test case.
                  </div>
                ) : (
                  <div>
                    {testSteps.map((ts, idx) => {
                      const sr = stepResults.find(r => r.test_step_id === ts.id);
                      const status = sr ? sr.status : "pending";
                      const isPass = status === "pass";
                      const isFail = status === "fail";
                      const isPending = status === "pending";
                      return (
                        <div key={ts.id} className={"step" + (isPending && idx === stepResults.filter(r => r.status !== "pending").length ? " active" : isPass ? " pass" : isFail ? " fail" : "")}>
                          <div className="step-num">
                            {isPass ? "✓" : isFail ? "✕" : idx + 1}
                          </div>
                          <div className="step-text">
                            <div>{ts.action}</div>
                            {ts.expected_result && (
                              <div className="expected">→ {ts.expected_result}</div>
                            )}
                            {sr && sr.actual_result && (
                              <div style={{fontSize:11, color:"var(--text-muted)", marginTop:4}}>
                                Actual: {sr.actual_result}
                              </div>
                            )}
                          </div>
                          <div className="step-actions" style={{display:"flex", gap:4}}>
                            {isPending && window.can && window.can(currentUser, "write") && (
                              <>
                                <button
                                  className="btn ghost sm"
                                  style={{color:"var(--pass)", fontSize:11}}
                                  disabled={markingStep}
                                  onClick={() => markStep(sr || { test_step_id: ts.id, actual_result: null }, "pass")}
                                  title="Pass (P)"
                                >P</button>
                                <button
                                  className="btn ghost sm"
                                  style={{color:"var(--fail)", fontSize:11}}
                                  disabled={markingStep}
                                  onClick={() => markStep(sr || { test_step_id: ts.id, actual_result: null }, "fail")}
                                  title="Fail (F)"
                                >F</button>
                              </>
                            )}
                            {!isPending && (
                              <span className={"status " + (isPass ? "pass" : "fail")} style={{fontSize:10}}>
                                {status.toUpperCase()}
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div style={{padding:"0 22px 22px"}}>
                <div className="card">
                  <div className="card-h">
                    <div className="card-title">Evidence</div>
                    <div className="card-sub">attach screenshots, logs, recordings</div>
                  </div>
                  <div style={{padding:14}}>
                    <FileDropZone
                      entityType="run_case"
                      entityId={current?.id ? String(current.id) : ""}
                      onUploaded={(att) => setAttachments(prev => [...prev, att])}
                    />
                    {attachments.length > 0 && (
                      <div style={{display:"grid", gridTemplateColumns:"repeat(3, 1fr)", gap:10, marginTop:12}}>
                        {attachments.map(att => (
                          <AttachmentCard
                            key={att.id}
                            att={att}
                            onDelete={(id) => setAttachments(prev => prev.filter(a => a.id !== id))}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {window.can && window.can(currentUser, "write") && (
              <div style={{padding:"12px 22px", borderTop:"1px solid var(--border)", display:"flex", gap:8, background:"var(--bg-2)"}}>
                <textarea className="textarea" placeholder="Note for this step / case..." style={{flex:1, minHeight:38, padding:"8px 10px"}}></textarea>
                <div style={{display:"flex", flexDirection:"column", gap:6}}>
                  <button className="btn sm" style={{background:"var(--fail-soft)", color:"var(--fail)", borderColor:"oklch(from var(--fail) l c h / 0.3)"}}>Mark fail <span className="kbd">F</span></button>
                  <button className="btn sm" style={{background:"var(--pass-soft)", color:"var(--pass)", borderColor:"oklch(from var(--pass) l c h / 0.3)"}}>Mark pass <span className="kbd">P</span></button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div style={{display:"flex", height:"100%", alignItems:"center", justifyContent:"center"}}>
            <span className="mono dim">Select a case from the queue.</span>
          </div>
        )}
      </div>

      {/* Right — context */}
      <div style={{borderLeft:"1px solid var(--border)", background:"var(--bg-2)", overflowY:"auto"}}>
        <div style={{padding:14, borderBottom:"1px solid var(--border)"}}>
          <div className="card-title" style={{marginBottom:8}}>Environment</div>
          <div style={{display:"flex", flexDirection:"column", gap:6, fontSize:11.5}}>
            <Detail label="Env" value={run.env ? <span className="tag">{run.env}</span> : <span className="mono dim">—</span>} />
            <Detail label="Branch" value={<span className="mono">{run.branch || "—"}</span>} />
            <Detail label="Owner" value={<span className="mono">{run.owner || "—"}</span>} />
          </div>
        </div>

        <div style={{padding:14, borderBottom:"1px solid var(--border)"}}>
          <div style={{display:"flex", alignItems:"center", marginBottom:8}}>
            <div className="card-title">Linked defects</div>
            {runDefects.length > 0 && <span className="count" style={{marginLeft:6}}>{runDefects.length}</span>}
            <div className="spacer" />
            {window.can && window.can(currentUser, "write") && (
              <button className="btn ghost sm" style={{fontSize:10.5}} onClick={() => setShowFileDefect(true)}><Icon name="plus" /></button>
            )}
          </div>
          {runDefects.length === 0 ? (
            <div className="empty" style={{padding:"8px 0", textAlign:"left", fontSize:11.5}}>No defects filed for this run.</div>
          ) : (
            <div style={{display:"flex", flexDirection:"column", gap:4}}>
              {runDefects.map(d => {
                const color = d.status === "open" ? "var(--fail)" : d.status === "in_progress" ? "var(--warn)" : "var(--pass)";
                const sevClass = d.severity === "critical" || d.severity === "high" ? "priority-high" : d.severity === "med" ? "priority-med" : "priority-low";
                return (
                  <div key={d.id} style={{display:"flex", alignItems:"center", gap:6, fontSize:11.5}}>
                    <span className="mono" style={{color, minWidth:72}}>{d.id}</span>
                    <span style={{flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{d.title}</span>
                    <span className={"tag " + sevClass} style={{fontSize:10}}>{d.severity}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {showFileDefect && (
          <RunDefectModal
            runId={liveRun?.id}
            onClose={() => setShowFileDefect(false)}
            onCreated={(d) => { setRunDefects(prev => [...prev, d]); setShowFileDefect(false); }}
          />
        )}

        <div style={{padding:14}}>
          <div className="card-title" style={{marginBottom:8}}>Run timeline</div>
          <div style={{display:"flex", flexDirection:"column", gap:6, fontSize:11.5}}>
            <TimelineItem time="" text={`Case ${current?.test_id || "—"} started`} />
          </div>
        </div>
      </div>
    </div>
  );
}

function StepRunner({num, text, active, pass, fail}) {
  return (
    <div className={"step" + (active ? " active" : pass ? " pass" : fail ? " fail" : "")}>
      <div className="step-num">{pass ? "✓" : fail ? "✕" : num}</div>
      <div className="step-text">{text}</div>
      <div className="step-actions">
        {active && <span className="status info">RUNNING</span>}
      </div>
    </div>
  );
}

function Evidence({label, sub}) {
  return (
    <div style={{border:"1px solid var(--border)", borderRadius:"var(--radius)", overflow:"hidden", background:"var(--bg-2)"}}>
      <div style={{height:80, background:"repeating-linear-gradient(45deg, var(--surface-2) 0 8px, var(--surface-3) 8px 16px)", display:"grid", placeItems:"center"}}>
        <span className="mono dim" style={{fontSize:10}}>screenshot</span>
      </div>
      <div style={{padding:"6px 8px"}}>
        <div className="mono" style={{fontSize:11}}>{label}</div>
        <div className="mono dim" style={{fontSize:10}}>{sub}</div>
      </div>
    </div>
  );
}

function TimelineItem({time, text, warn}) {
  return (
    <div style={{display:"flex", gap:8, alignItems:"baseline"}}>
      <span className="mono dim" style={{fontSize:10, width:54, flexShrink:0}}>{time}</span>
      <span style={{color: warn ? "var(--fail)" : "var(--text-muted)"}}>{text}</span>
    </div>
  );
}

function NewPlanModal({ onClose, onCreated }) {
  const [tests, setTests] = React.useState([]);
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState(new Set());
  const [name, setName] = React.useState("");
  const [env, setEnv] = React.useState("staging");
  const [schedule, setSchedule] = React.useState("Manual");
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    fetch("/api/tests", { headers: window.authHeaders() })
      .then(r => r.json())
      .then(data => setTests(data))
      .catch(() => { if (window.TH_DATA) setTests(window.TH_DATA.tests || []); });
  }, []);

  const filtered = tests.filter(t =>
    !search ||
    t.title.toLowerCase().includes(search.toLowerCase()) ||
    t.id.toLowerCase().includes(search.toLowerCase())
  );

  const toggleSel = (id) => {
    setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const handleSave = async () => {
    if (!name.trim()) { setError("Plan name is required."); return; }
    setSaving(true);
    setError(null);
    try {
      await window.TH_API.createPlan({
        name: name.trim(),
        env,
        schedule: schedule.trim() || "Manual",
        test_ids: [...selected],
      });
      onCreated();
    } catch (e) {
      setError(e.message);
      setSaving(false);
    }
  };

  const overlayStyle = {
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000,
    display: "flex", alignItems: "center", justifyContent: "center",
  };
  const panelStyle = {
    background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: 8,
    width: 560, maxHeight: "80vh", display: "flex", flexDirection: "column", overflow: "hidden",
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={panelStyle} onClick={e => e.stopPropagation()}>
        <div style={{display:"flex", alignItems:"center", padding:"16px 18px 14px", borderBottom:"1px solid var(--border)"}}>
          <div>
            <div style={{fontSize:14, fontWeight:600}}>New test plan</div>
            <div style={{fontSize:11, color:"var(--text-dim)", marginTop:2}}>{selected.size} test{selected.size !== 1 ? "s" : ""} selected</div>
          </div>
          <button className="btn ghost icon sm" style={{marginLeft:"auto"}} onClick={onClose}><Icon name="x" /></button>
        </div>

        <div style={{padding:"14px 18px", display:"flex", flexDirection:"column", gap:12, borderBottom:"1px solid var(--border)"}}>
          <div>
            <div style={{fontSize:11, fontWeight:500, color:"var(--text-dim)", marginBottom:5}}>Plan name *</div>
            <input className="input" style={{width:"100%", boxSizing:"border-box"}} value={name}
              onChange={e => setName(e.target.value)} placeholder="e.g. Release regression — full" autoFocus />
          </div>
          <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:12}}>
            <div>
              <div style={{fontSize:11, fontWeight:500, color:"var(--text-dim)", marginBottom:5}}>Environment</div>
              <select className="input" value={env} onChange={e => setEnv(e.target.value)} style={{width:"100%"}}>
                <option value="staging">staging</option>
                <option value="preview">preview</option>
                <option value="local">local</option>
                <option value="production">production</option>
              </select>
            </div>
            <div>
              <div style={{fontSize:11, fontWeight:500, color:"var(--text-dim)", marginBottom:5}}>Schedule (label)</div>
              <input className="input" style={{width:"100%", boxSizing:"border-box"}} value={schedule}
                onChange={e => setSchedule(e.target.value)} placeholder="Manual / 0 2 * * * / on PR" />
            </div>
          </div>
        </div>

        <div style={{padding:"10px 14px", borderBottom:"1px solid var(--border)"}}>
          <input className="input" style={{width:"100%", boxSizing:"border-box"}}
            placeholder="Search tests by title or ID…" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <div style={{overflowY:"auto", flex:1}}>
          {filtered.length === 0 && <div className="empty" style={{padding:"24px 18px", fontSize:12}}>No tests match.</div>}
          {filtered.map(t => (
            <label key={t.id} style={{
              display:"grid", gridTemplateColumns:"20px 1fr auto", gap:10, alignItems:"center",
              padding:"8px 18px", cursor:"pointer", fontSize:12.5,
              background: selected.has(t.id) ? "var(--surface-2)" : "transparent",
            }}>
              <input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleSel(t.id)} />
              <div>
                <div style={{fontWeight:500, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{t.title}</div>
                <div className="mono dim" style={{fontSize:10.5}}>{t.id}{t.folder ? ` · ${t.folder}` : ""}</div>
              </div>
              <StatusBadge s={t.status} />
            </label>
          ))}
        </div>

        <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", padding:"12px 18px", borderTop:"1px solid var(--border)"}}>
          {error ? <span className="mono" style={{fontSize:11, color:"var(--danger)"}}>{error}</span> : <span className="mono dim" style={{fontSize:11}}>{selected.size} selected</span>}
          <div style={{display:"flex", alignItems:"center", gap:10}}>
            <button className="btn ghost" onClick={onClose}>Cancel</button>
            <button className="btn accent" onClick={handleSave} disabled={saving || !name.trim()}>
              {saving ? "Saving…" : "Create plan"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function NewRunModal({ onClose, onCreated }) {
  const [step, setStep] = React.useState(1);
  const [tests, setTests] = React.useState([]);
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState(new Set());
  const [name, setName] = React.useState("");
  const [env, setEnv] = React.useState("staging");
  const [branch, setBranch] = React.useState("main");
  const [creating, setCreating] = React.useState(false);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    fetch("/api/tests", { headers: window.authHeaders() })
      .then(r => r.json())
      .then(data => setTests(data))
      .catch(() => { if (window.TH_DATA) setTests(window.TH_DATA.tests || []); });
  }, []);

  const filtered = tests.filter(t =>
    !search ||
    t.title.toLowerCase().includes(search.toLowerCase()) ||
    t.id.toLowerCase().includes(search.toLowerCase())
  );

  const toggleSel = (id) => {
    setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const handleCreate = async () => {
    if (!name.trim()) { setError("Run name is required."); return; }
    setCreating(true);
    setError(null);
    const runId = "R-" + Math.floor(1000 + Math.random() * 9000);
    try {
      const run = await window.TH_API.createRun({
        id: runId,
        name: name.trim(),
        status: "running",
        env,
        branch,
        test_ids: [...selected],
      });
      onCreated(run.id);
    } catch (e) {
      setError(e.message);
      setCreating(false);
    }
  };

  const overlayStyle = {
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000,
    display: "flex", alignItems: "center", justifyContent: "center",
  };
  const panelStyle = {
    background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: 8,
    width: 560, maxHeight: "80vh", display: "flex", flexDirection: "column", overflow: "hidden",
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={panelStyle} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{display:"flex", alignItems:"center", padding:"16px 18px 14px", borderBottom:"1px solid var(--border)"}}>
          <div>
            <div style={{fontSize:14, fontWeight:600}}>{step === 1 ? "Select tests" : "Configure run"}</div>
            <div style={{fontSize:11, color:"var(--text-dim)", marginTop:2}}>
              {step === 1 ? `${selected.size} selected` : `${selected.size} test${selected.size !== 1 ? "s" : ""} will run`}
            </div>
          </div>
          <button className="btn ghost icon sm" style={{marginLeft:"auto"}} onClick={onClose}><Icon name="x" /></button>
        </div>

        {step === 1 ? (
          <>
            <div style={{padding:"10px 14px", borderBottom:"1px solid var(--border)"}}>
              <input
                className="input"
                style={{width:"100%", boxSizing:"border-box"}}
                placeholder="Search by title or ID…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                autoFocus
              />
            </div>
            <div style={{overflowY:"auto", flex:1}}>
              {filtered.length === 0 && (
                <div className="empty" style={{padding:"24px 18px", fontSize:12}}>No tests match.</div>
              )}
              {filtered.map(t => (
                <label
                  key={t.id}
                  style={{
                    display:"grid", gridTemplateColumns:"20px 1fr auto",
                    gap:10, alignItems:"center",
                    padding:"8px 18px", cursor:"pointer", fontSize:12.5,
                    background: selected.has(t.id) ? "var(--surface-2)" : "transparent",
                  }}
                >
                  <input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleSel(t.id)} />
                  <div>
                    <div style={{fontWeight:500, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{t.title}</div>
                    <div className="mono dim" style={{fontSize:10.5}}>{t.id}{t.folder ? ` · ${t.folder}` : ""}</div>
                  </div>
                  <StatusBadge s={t.status} />
                </label>
              ))}
            </div>
            <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", padding:"12px 18px", borderTop:"1px solid var(--border)"}}>
              <button className="btn ghost" onClick={onClose}>Cancel</button>
              <div style={{display:"flex", alignItems:"center", gap:10}}>
                <span className="mono dim" style={{fontSize:11}}>{selected.size} selected</span>
                <button className="btn accent" onClick={() => setStep(2)} disabled={selected.size === 0}>
                  Configure →
                </button>
              </div>
            </div>
          </>
        ) : (
          <>
            <div style={{padding:"18px", display:"flex", flexDirection:"column", gap:14, overflowY:"auto", flex:1}}>
              <div>
                <div style={{fontSize:11, fontWeight:500, color:"var(--text-dim)", marginBottom:5}}>Run name *</div>
                <input
                  className="input"
                  style={{width:"100%", boxSizing:"border-box"}}
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="e.g. Release regression · v2.4"
                  autoFocus
                />
              </div>
              <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:12}}>
                <div>
                  <div style={{fontSize:11, fontWeight:500, color:"var(--text-dim)", marginBottom:5}}>Environment</div>
                  <select className="input" value={env} onChange={e => setEnv(e.target.value)} style={{width:"100%"}}>
                    <option value="staging">staging</option>
                    <option value="preview">preview</option>
                    <option value="local">local</option>
                    <option value="production">production</option>
                  </select>
                </div>
                <div>
                  <div style={{fontSize:11, fontWeight:500, color:"var(--text-dim)", marginBottom:5}}>Branch</div>
                  <input
                    className="input"
                    style={{width:"100%", boxSizing:"border-box"}}
                    value={branch}
                    onChange={e => setBranch(e.target.value)}
                    placeholder="main"
                  />
                </div>
              </div>
              {error && <div style={{color:"var(--fail)", fontSize:12}}>{error}</div>}
            </div>
            <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", padding:"12px 18px", borderTop:"1px solid var(--border)"}}>
              <button className="btn ghost" onClick={() => setStep(1)}>← Back</button>
              <button className="btn accent" onClick={handleCreate} disabled={creating || !name.trim()}>
                {creating ? "Creating…" : "Create & start"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function RunDefectModal({ runId, onClose, onCreated }) {
  const [form, setForm] = useState({ title: "", severity: "med", description: "" });
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const d = await TH_API.createDefect({
        title: form.title.trim(),
        severity: form.severity,
        description: form.description.trim() || null,
        run_id: runId,
      });
      onCreated(d);
    } catch (e) {}
    setSaving(false);
  };

  return (
    <div style={{position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center"}} onClick={onClose}>
      <div style={{background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:8, padding:24, width:440}} onClick={e => e.stopPropagation()}>
        <h2 style={{fontSize:15, fontWeight:600, margin:"0 0 16px"}}>File defect for {runId}</h2>
        <div style={{display:"flex", flexDirection:"column", gap:10}}>
          <div>
            <label style={{fontSize:11, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:4}}>Title</label>
            <input className="input" style={{width:"100%", boxSizing:"border-box"}} value={form.title} placeholder="Describe the bug…" onChange={e => setForm(f => ({...f, title: e.target.value}))} autoFocus />
          </div>
          <div>
            <label style={{fontSize:11, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:4}}>Description (optional)</label>
            <textarea className="textarea" style={{width:"100%", boxSizing:"border-box", minHeight:56}} value={form.description} placeholder="Steps to reproduce…" onChange={e => setForm(f => ({...f, description: e.target.value}))} />
          </div>
          <div>
            <label style={{fontSize:11, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:4}}>Severity</label>
            <select className="input" value={form.severity} onChange={e => setForm(f => ({...f, severity: e.target.value}))}>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="med">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>
        <div style={{display:"flex", gap:8, justifyContent:"flex-end", marginTop:20}}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn accent" onClick={handleCreate} disabled={saving || !form.title.trim()}>
            {saving ? "Filing…" : "File defect"}
          </button>
        </div>
      </div>
    </div>
  );
}

function FileDropZone({ entityType, entityId, onUploaded }) {
  const [dragging, setDragging] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const handleFiles = async (files) => {
    if (!files.length || !entityId) return;
    setUploading(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        const att = await TH_API.uploadAttachment(entityType, entityId, file);
        onUploaded(att);
      }
    } catch (e) {
      setError("Upload failed: " + e.message);
    }
    setUploading(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <div>
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        style={{
          border: `2px dashed ${dragging ? "var(--accent)" : "var(--border)"}`,
          borderRadius: "var(--radius)",
          padding: 16,
          textAlign: "center",
          fontSize: 12,
          color: "var(--text-dim)",
          transition: "border-color .15s",
        }}
      >
        {uploading ? "Uploading…" : (
          <>
            Drop files here or{" "}
            <label style={{ color: "var(--accent)", cursor: "pointer" }}>
              browse
              <input
                type="file"
                multiple
                style={{ display: "none" }}
                onChange={e => handleFiles(e.target.files)}
              />
            </label>
          </>
        )}
      </div>
      {error && <div style={{color:"var(--fail)", fontSize:11, marginTop:4}}>{error}</div>}
    </div>
  );
}

function AttachmentCard({ att, onDelete }) {
  const isImage = att.mime_type && att.mime_type.startsWith("image/");
  const handleDelete = async () => {
    try {
      await TH_API.deleteAttachment(att.id);
      onDelete(att.id);
    } catch (e) {}
  };
  return (
    <div style={{border:"1px solid var(--border)", borderRadius:"var(--radius)", overflow:"hidden", background:"var(--bg-2)"}}>
      {isImage ? (
        <img
          src={`/api/attachments/${att.id}`}
          alt={att.filename}
          style={{width:"100%", height:80, objectFit:"cover", display:"block"}}
          onError={e => { e.target.style.display="none"; }}
        />
      ) : (
        <div style={{height:80, background:"var(--surface-2)", display:"grid", placeItems:"center"}}>
          <span className="mono dim" style={{fontSize:10}}>
            {att.mime_type || "file"}
          </span>
        </div>
      )}
      <div style={{padding:"6px 8px", display:"flex", alignItems:"center", gap:4}}>
        <a
          href={`/api/attachments/${att.id}`}
          target="_blank"
          className="mono"
          style={{fontSize:11, flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", color:"var(--text)"}}
        >{att.filename}</a>
        <button
          className="btn ghost icon sm"
          style={{color:"var(--fail)", padding:"1px 4px", fontSize:10}}
          onClick={handleDelete}
          title="Delete attachment"
        >×</button>
      </div>
    </div>
  );
}

window.RunDetail = RunDetail;
window.Runs = Runs;
