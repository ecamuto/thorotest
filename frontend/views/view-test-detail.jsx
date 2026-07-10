// Test case detail — with YAML, lineage, history

function TestDetail({ testId, onBack, currentUser }) {
  const [test, setTest] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [tab, setTab] = useState("definition");
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [defectCount, setDefectCount] = useState(null);
  const [reqCount, setReqCount] = useState(null);

  React.useEffect(() => {
    const id = testId || "TC-2301";
    setLoading(true);
    fetch(`/api/tests/${id}`, { headers: window.authHeaders() })
      .then(r => { if (!r.ok) throw new Error("not found"); return r.json(); })
      .then(t => {
        setTest({ ...t, folder: t.folder_id, updated: t.updated_at, lastRun: t.last_run_at });
        setLoading(false);
      })
      .catch(() => {
        // Fall back to demo data by exact id only — never substitute an
        // unrelated test, so an unknown id renders the "Test not found" state.
        const D = window.TH_DATA;
        setTest(D?.tests.find(t => t.id === id) || null);
        setLoading(false);
      });
  }, [testId]);

  React.useEffect(() => {
    if (!test) return;
    TH_API.getTestDefects(test.id)
      .then(d => setDefectCount(d.length))
      .catch(() => {});
    TH_API.getTestRequirements(test.id)
      .then(r => setReqCount(r.length))
      .catch(() => {});
  }, [test?.id]);

  const saveTitle = async () => {
    if (!titleDraft.trim() || titleDraft === test.title) { setEditingTitle(false); return; }
    setSaving(true);
    try {
      await fetch(`/api/tests/${test.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("th_token")}` },
        body: JSON.stringify({ title: titleDraft.trim() }),
      });
      setTest(t => ({ ...t, title: titleDraft.trim() }));
    } catch (e) {}
    setEditingTitle(false);
    setSaving(false);
  };

  const handleDelete = async () => {
    try { await fetch(`/api/tests/${test.id}`, { method: "DELETE", headers: { "Authorization": `Bearer ${localStorage.getItem("th_token")}` } }); } catch (e) {}
    onBack();
  };

  if (loading) return (
    <div style={{display:"flex", height:"100%", alignItems:"center", justifyContent:"center"}}>
      <span className="mono dim">Loading…</span>
    </div>
  );

  if (!test) return (
    <div style={{display:"flex", height:"100%", alignItems:"center", justifyContent:"center"}}>
      <span className="mono dim">Test not found.</span>
    </div>
  );

  return (
    <div style={{display:"flex", flexDirection:"column", height:"100%", overflow:"hidden"}}>
      {/* Header */}
      <div style={{padding:"18px 22px 0"}}>
        <div style={{display:"flex", alignItems:"center", gap:8, fontSize:11.5, color:"var(--text-dim)", marginBottom:8}}>
          <button className="btn ghost sm" onClick={onBack}><span style={{transform:"rotate(180deg)", display:"inline-flex"}}><Icon name="chev" /></span> Library</button>
          <span>/</span>
          <span className="mono" style={{color:"var(--text-muted)"}}>{test.id}</span>
        </div>

        <div style={{display:"flex", alignItems:"flex-start", gap:14, marginBottom:14}}>
          <div style={{flex:1, minWidth:0}}>
            <div style={{display:"flex", alignItems:"center", gap:10, marginBottom:6}}>
              <StatusSelect s={test.status} testId={test.id} onChanged={s => setTest(t => ({...t, status: s}))} />
              <span className={"tag priority-" + (test.priority === "high" ? "high" : test.priority === "med" ? "med" : "low")}>priority: {test.priority}</span>
              {test.auto ? <span className="tag" style={{color:"var(--info)", borderColor:"oklch(from var(--info) l c h / 0.3)"}}>automated · {test.runner}</span> : <span className="tag">manual</span>}
              {test.tags.map(tg => <span key={tg} className="tag">{tg}</span>)}
            </div>
            {editingTitle ? (
              <div style={{display:"flex", alignItems:"center", gap:8, marginBottom:4}}>
                <input
                  className="input"
                  style={{fontSize:20, fontWeight:600, flex:1}}
                  value={titleDraft}
                  autoFocus
                  onChange={e => setTitleDraft(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") saveTitle(); if (e.key === "Escape") setEditingTitle(false); }}
                />
                <button className="btn sm accent" onClick={saveTitle} disabled={saving}>Save</button>
                <button className="btn sm" onClick={() => setEditingTitle(false)}>Cancel</button>
              </div>
            ) : (
              window.can && window.can(currentUser, "write") ? (
                <h1
                  style={{fontSize:22, fontWeight:600, letterSpacing:"-0.02em", margin:"0 0 4px", lineHeight:1.25, cursor:"text"}}
                  title="Click to edit title"
                  onClick={() => { setTitleDraft(test.title); setEditingTitle(true); }}
                >{test.title}</h1>
              ) : (
                <h1
                  style={{fontSize:22, fontWeight:600, letterSpacing:"-0.02em", margin:"0 0 4px", lineHeight:1.25}}
                >{test.title}</h1>
              )
            )}
            <div style={{fontSize:12.5, color:"var(--text-muted)", display:"flex", alignItems:"center", gap:10}}>
              <span className="mono">{test.id}</span>
              <span className="dim">·</span>
              <span>Owned by <b style={{color:"var(--text)"}}>{test.owner || "unassigned"}</b></span>
              {test.updated_at && <><span className="dim">·</span><span>Updated <span className="mono">{new Date(test.updated_at).toLocaleDateString()}</span></span></>}
              {test.source_path && <><span className="dim">·</span><span className="mono" style={{color:"var(--accent)"}}>{test.source_path}</span></>}
            </div>
          </div>
          <div style={{display:"flex", gap:6}}>
            {window.can && window.can(currentUser, "delete") && (
              <button className="btn" style={{color:"var(--fail)"}} onClick={() => setDeleteConfirm(true)}><Icon name="x" /> Delete</button>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        <div className={"tab" + (tab === "definition" ? " active" : "")} onClick={() => setTab("definition")}>Definition</div>
        <div className={"tab" + (tab === "history" ? " active" : "")} onClick={() => setTab("history")}>Run history</div>
        <div className={"tab" + (tab === "defects" ? " active" : "")} onClick={() => setTab("defects")}>Defects{defectCount !== null && defectCount > 0 ? <span className="count">{defectCount}</span> : null}</div>
        <div className={"tab" + (tab === "requirements" ? " active" : "")} onClick={() => setTab("requirements")}>Requirements{reqCount !== null && reqCount > 0 ? <span className="count">{reqCount}</span> : null}</div>
        <div className={"tab" + (tab === "comments" ? " active" : "")} onClick={() => setTab("comments")}>Comments</div>
        <div className={"tab" + (tab === "git" ? " active" : "")} onClick={() => setTab("git")}>Git history</div>
      </div>

      <div style={{overflowY:"auto", flex:1}}>
        {tab === "definition" && <DefinitionTab test={test} currentUser={currentUser} />}
        {tab === "history" && <HistoryTab test={test} />}
        {tab === "defects" && <DefectsTab test={test} currentUser={currentUser} />}
        {tab === "requirements" && <RequirementsTab test={test} currentUser={currentUser} onCountChange={setReqCount} />}
        {tab === "comments" && <CommentsTab test={test} />}
        {tab === "git" && <GitHistoryTab test={test} />}
      </div>

      {deleteConfirm && (
        <div style={{position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center"}} onClick={() => setDeleteConfirm(false)}>
          <div style={{background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:8, padding:24, width:400}} onClick={e => e.stopPropagation()}>
            <h2 style={{fontSize:15, fontWeight:600, margin:"0 0 10px"}}>Delete {test.id}?</h2>
            <p style={{fontSize:12.5, color:"var(--text-muted)", margin:"0 0 20px", lineHeight:1.5}}>"{test.title}" will be permanently deleted.</p>
            <div style={{display:"flex", gap:8, justifyContent:"flex-end"}}>
              <button className="btn" onClick={() => setDeleteConfirm(false)}>Cancel</button>
              <button className="btn" style={{background:"var(--fail)", color:"white", border:"none"}} onClick={handleDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DefinitionTab({ test, currentUser }) {
  const [steps, setSteps] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [dirty, setDirty] = React.useState(false);
  const [editingIdx, setEditingIdx] = React.useState(null); // index of step being edited

  React.useEffect(() => {
    if (!test?.id) return;
    setLoading(true);
    TH_API.getTestSteps(test.id)
      .then(data => { setSteps(data); setLoading(false); })
      .catch(() => { setSteps([]); setLoading(false); });
  }, [test?.id]);

  const addStep = () => {
    const newStep = { _local: true, action: "", expected_result: "" };
    setSteps(prev => [...prev, newStep]);
    setEditingIdx(steps.length);
    setDirty(true);
  };

  const updateStep = (idx, field, value) => {
    setSteps(prev => prev.map((s, i) => i === idx ? { ...s, [field]: value } : s));
    setDirty(true);
  };

  const deleteStep = (idx) => {
    setSteps(prev => prev.filter((_, i) => i !== idx));
    setEditingIdx(null);
    setDirty(true);
  };

  const moveStep = (idx, direction) => {
    const newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= steps.length) return;
    setSteps(prev => {
      const arr = [...prev];
      [arr[idx], arr[newIdx]] = [arr[newIdx], arr[idx]];
      return arr;
    });
    setDirty(true);
  };

  const saveSteps = async () => {
    setSaving(true);
    try {
      const payload = steps.map(s => ({
        action: s.action || "",
        expected_result: s.expected_result || null,
      }));
      const saved = await TH_API.replaceTestSteps(test.id, payload);
      setSteps(saved);
      setDirty(false);
      setEditingIdx(null);
    } catch (e) {}
    setSaving(false);
  };

  return (
    <div style={{display:"grid", gridTemplateColumns:"1fr 380px", gap:14, padding:"18px 22px 32px"}}>
      <div style={{display:"flex", flexDirection:"column", gap:14}}>
        {/* Steps editor */}
        <div className="card">
          <div className="card-h">
            <div className="card-title">Steps</div>
            <div className="card-sub">
              {loading ? "Loading…" : `${steps.length} step${steps.length !== 1 ? "s" : ""}`}
            </div>
            <div className="spacer" />
            {dirty && window.can && window.can(currentUser, "write") && (
              <button className="btn sm accent" onClick={saveSteps} disabled={saving}>
                {saving ? "Saving…" : "Save steps"}
              </button>
            )}
            {window.can && window.can(currentUser, "write") && (
              <button className="btn sm ghost" onClick={addStep} disabled={saving}>
                <Icon name="plus" /> Add step
              </button>
            )}
          </div>

          {loading ? (
            <div className="mono dim" style={{padding:"16px 14px", fontSize:12}}>Loading steps…</div>
          ) : steps.length === 0 ? (
            <div className="mono dim" style={{padding:"16px 14px", fontSize:12}}>
              No steps yet — add the first step.
            </div>
          ) : (
            <div>
              {steps.map((s, idx) => (
                <div key={s.id || ("local-" + idx)} className={"step" + (editingIdx === idx ? " active" : "")}>
                  <div className="step-num">{idx + 1}</div>
                  <div className="step-text" style={{flex:1}}>
                    {editingIdx === idx ? (
                      <div style={{display:"flex", flexDirection:"column", gap:6, padding:"4px 0"}}>
                        <input
                          className="input"
                          style={{fontSize:12.5}}
                          placeholder="Action (e.g. Click Submit)"
                          value={s.action || ""}
                          autoFocus
                          onChange={e => updateStep(idx, "action", e.target.value)}
                        />
                        <input
                          className="input"
                          style={{fontSize:12.5}}
                          placeholder="Expected result (optional)"
                          value={s.expected_result || ""}
                          onChange={e => updateStep(idx, "expected_result", e.target.value)}
                        />
                        {window.can && window.can(currentUser, "write") && (
                          <div style={{display:"flex", gap:6}}>
                            <button className="btn sm ghost" onClick={() => setEditingIdx(null)}>Done</button>
                            <button className="btn sm ghost" style={{color:"var(--fail)"}} onClick={() => deleteStep(idx)}>
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div
                        onClick={window.can && window.can(currentUser, "write") ? () => setEditingIdx(idx) : undefined}
                        style={{cursor: window.can && window.can(currentUser, "write") ? "text" : "default"}}
                      >
                        <div>{s.action || <span className="dim">No action text</span>}</div>
                        {s.expected_result && (
                          <div className="expected">→ {s.expected_result}</div>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="step-actions" style={{display:"flex", flexDirection:"column", gap:2}}>
                    <button
                      className="btn ghost icon sm"
                      title="Move up"
                      onClick={() => moveStep(idx, -1)}
                      disabled={idx === 0}
                    >▲</button>
                    <button
                      className="btn ghost icon sm"
                      title="Move down"
                      onClick={() => moveStep(idx, 1)}
                      disabled={idx === steps.length - 1}
                    >▼</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* YAML source — rendered only when this test is synced from git */}
        {test.source_path && <YamlSourceCard test={test}
          onPushed={patch => setTest(t => ({...t, ...patch}))} />}
      </div>

      {/* Side column — keep unchanged from original */}
      <div style={{display:"flex", flexDirection:"column", gap:14}}>
        <div className="card">
          <div className="card-h"><div className="card-title">Details</div></div>
          <div className="card-b" style={{display:"flex", flexDirection:"column", gap:10, fontSize:12}}>
            <Detail label="Type" value={<span className="tag">{test.type || "manual"}</span>} />
            <Detail label="Priority" value={test.priority || "—"} />
            <Detail label="Status" value={test.status ? <StatusBadge s={test.status} /> : "—"} />
            <Detail label="Owner" value={test.owner || "unassigned"} />
            <Detail label="Last run" value={test.last_run_at ? new Date(test.last_run_at).toLocaleString() : "—"} mono />
            <Detail label="Updated" value={test.updated_at ? new Date(test.updated_at).toLocaleString() : "—"} mono />
            <Detail label="Tags" value={
              (test.tags && test.tags.length)
                ? <span style={{display:"flex", gap:4, flexWrap:"wrap"}}>{test.tags.map(t => <span key={t} className="tag">{t}</span>)}</span>
                : <span className="dim">—</span>
            } />
          </div>
        </div>
      </div>
    </div>
  );
}

function Step({num, text, children, active, pass, fail}) {
  return (
    <div className={"step" + (active ? " active" : pass ? " pass" : fail ? " fail" : "")}>
      <div className="step-num">{num}</div>
      <div className="step-text">
        {text}
        {children}
      </div>
      <div className="step-actions">
        <button className="btn ghost icon sm"><Icon name="more" /></button>
      </div>
    </div>
  );
}

function Detail({label, value, mono}) {
  return (
    <div style={{display:"flex", alignItems:"center", gap:10}}>
      <div style={{color:"var(--text-dim)", fontSize:11, textTransform:"uppercase", letterSpacing:"0.06em", width:120, flexShrink:0}}>{label}</div>
      <div className={mono ? "mono" : ""} style={{flex:1, minWidth:0}}>{value}</div>
    </div>
  );
}

function YamlSourceCard({test, onPushed}) {
  const [pushing, setPushing] = useState(false);
  const [msg, setMsg] = useState(null);   // {kind: "ok"|"err", text}
  const ref = test.source_ref || "";
  const shortRef = ref.slice(0, 7);
  // {repo_url}/blob/{ref}/{path} → exact file at the synced commit on GitHub.
  const ghUrl = test.repo_url && ref
    ? `${test.repo_url.replace(/\.git$/, "").replace(/\/$/, "")}/blob/${ref}/${test.source_path}`
    : null;
  const synced = test.source_synced_at
    ? new Date(test.source_synced_at).toLocaleString()
    : null;

  async function push() {
    setPushing(true);
    setMsg(null);
    try {
      const r = await TH_API.pushTestToGit(test.id);
      onPushed && onPushed({ source_ref: r.commit, source_synced_at: new Date().toISOString() });
      setMsg({ kind: "ok", text: `Pushed · ${(r.commit || "").slice(0, 7)}` });
    } catch (e) {
      setMsg({ kind: "err", text: e.message });
    } finally {
      setPushing(false);
    }
  }

  return (
    <div className="card">
      <div className="card-h">
        <div className="card-title mono">{test.source_path}</div>
        <div className="card-sub">
          synced from git{shortRef ? ` · ${shortRef}` : ""}{synced ? ` · ${synced}` : ""}
        </div>
        <div className="spacer" />
        <button className="btn sm" onClick={push} disabled={pushing}
                title="Commit this test's current state back to its source file on git">
          <Icon name="upload" /> {pushing ? "Pushing…" : "Push to git"}
        </button>
        {ghUrl && (
          <a className="btn sm" href={ghUrl} target="_blank" rel="noopener noreferrer">
            <Icon name="github" /> View on GitHub
          </a>
        )}
      </div>
      {msg && (
        <div style={{padding:"8px 14px 0", fontSize:12,
                     color: msg.kind === "ok" ? "var(--green, #2e7d32)" : "var(--red, #c62828)"}}>
          {msg.text}
        </div>
      )}
      <div style={{padding:14}}>
        {test.source_body
          ? <pre className="code"><code>{test.source_body}</code></pre>
          : <div className="mono dim" style={{fontSize:11.5}}>No file contents cached. Re-run sync.</div>}
      </div>
    </div>
  );
}

function HistoryTab({test}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [flakyLoading, setFlakyLoading] = React.useState(false);
  const [flakyError, setFlakyError] = React.useState(null);
  const [flakyResult, setFlakyResult] = React.useState(null);

  useEffect(() => {
    setLoading(true);
    TH_API.getTestHistory(test.id)
      .then(data => { setRows(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [test.id]);

  const trend = rows.map(r => r.case_status);

  return (
    <div style={{padding:"18px 22px 32px"}}>
      {/* Needs at least two runs to reason about variability, regardless of outcome. */}
      {rows.length >= 2 && (
        <div className="card" style={{marginBottom:14, borderColor:"var(--purple)"}}>
          <div className="card-h">
            <div className="card-title">AI Flaky Analysis</div>
            <div className="card-sub">Claude analyzes run history for patterns</div>
            <div className="spacer" />
            {!flakyResult && (
              <button
                className="btn sm"
                style={{background:"var(--purple)", color:"oklch(0.16 0 0)", borderColor:"var(--purple)"}}
                disabled={flakyLoading}
                onClick={() => {
                  setFlakyLoading(true);
                  setFlakyError(null);
                  TH_API.analyzeFlaky({test_id: test.id})
                    .then(data => { setFlakyResult(data); setFlakyLoading(false); })
                    .catch(err => { setFlakyError(err.message); setFlakyLoading(false); });
                }}
              >
                {flakyLoading ? "Analyzing…" : <><Icon name="sparkle" /> Analyze flaky</>}
              </button>
            )}
          </div>
          {flakyError && <div className="card-b" style={{color:"var(--fail)", fontSize:12}}>{flakyError}</div>}
          {flakyResult && (
            <div className="card-b">
              <div style={{fontSize:13, fontWeight:500, marginBottom:8}}>Diagnosis</div>
              <div style={{fontSize:12.5, marginBottom:14, lineHeight:1.6}}>{flakyResult.diagnosis}</div>
              {flakyResult.recommendations && flakyResult.recommendations.length > 0 && (
                <>
                  <div style={{fontSize:13, fontWeight:500, marginBottom:8}}>Recommendations</div>
                  <ul style={{margin:0, paddingLeft:18, fontSize:12.5, lineHeight:1.7}}>
                    {flakyResult.recommendations.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </>
              )}
              <button className="btn sm" style={{marginTop:12}} onClick={() => { setFlakyResult(null); setFlakyError(null); }}>Reset</button>
            </div>
          )}
        </div>
      )}
      {trend.length > 0 && (
        <div className="card" style={{marginBottom:14}}>
          <div className="card-h">
            <div className="card-title">Run trend</div>
            <div className="card-sub">{trend.length} run{trend.length !== 1 ? "s" : ""}</div>
            <div className="spacer" />
            <div className="mono dim" style={{fontSize:11}}>← oldest</div>
          </div>
          <div className="card-b">
            <div style={{display:"flex", gap:3, alignItems:"flex-end", height:48}}>
              {[...trend].reverse().map((s, i) => {
                const h = 24 + (i * 7) % 24;
                const bg = s === "pass" ? "var(--pass)" : s === "fail" ? "var(--fail)" : s === "running" ? "var(--info)" : "var(--warn)";
                return <div key={i} style={{flex:1, minWidth:8, height:`${h}px`, background:bg, borderRadius:1, opacity:0.85}} />;
              })}
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="mono dim" style={{padding:"24px 0", textAlign:"center"}}>Loading…</div>
      ) : rows.length === 0 ? (
        <div className="mono dim" style={{padding:"24px 0", textAlign:"center"}}>No runs found for this test.</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Run</th>
              <th>Name</th>
              <th>Status</th>
              <th>Duration</th>
              <th>Env</th>
              <th>Branch</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.run_id}>
                <td className="mono">{r.run_id}</td>
                <td style={{fontSize:12, maxWidth:220, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{r.run_name}</td>
                <td><StatusBadge s={r.case_status} /></td>
                <td className="mono dim">{r.duration || "—"}</td>
                <td><span className="tag">{r.env || "—"}</span></td>
                <td className="mono dim">{r.branch || "—"}</td>
                <td className="mono dim">{r.started || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const STATUS_TRANSITIONS = {
  open: ["in_progress", "resolved", "closed"],
  in_progress: ["open", "resolved", "closed"],
  resolved: ["open", "closed"],
  closed: ["open"],
};

function DefectsTab({ test, currentUser }) {
  const [defects, setDefects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: "", severity: "med", run_id: "", description: "" });
  const [saving, setSaving] = useState(false);
  const [runs, setRuns] = useState([]);
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);

  useEffect(() => {
    setLoading(true);
    TH_API.getTestDefects(test.id)
      .then(data => { setDefects(data); setLoading(false); })
      .catch(() => setLoading(false));
    TH_API.getRuns().then(setRuns).catch(() => {});
  }, [test.id]);

  const handleCreate = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const d = await TH_API.createDefect({
        title: form.title.trim(),
        severity: form.severity,
        description: form.description.trim() || null,
        test_id: test.id,
        run_id: form.run_id || null,
      });
      setDefects(prev => [d, ...prev]);
      setShowCreate(false);
      setForm({ title: "", severity: "med", run_id: "", description: "" });
    } catch (e) {}
    setSaving(false);
  };

  const handleStatusChange = async (id, newStatus) => {
    try {
      const updated = await TH_API.updateDefect(id, { status: newStatus });
      setDefects(prev => prev.map(d => d.id === id ? updated : d));
    } catch (e) {}
  };

  const handleDelete = async (id) => {
    try {
      await TH_API.deleteDefect(id);
      setDefects(prev => prev.filter(d => d.id !== id));
    } catch (e) {}
    setDeleteConfirmId(null);
  };

  const severityClass = s => s === "critical" || s === "high" ? "priority-high" : s === "med" ? "priority-med" : "priority-low";

  const statusColor = s => {
    if (s === "open") return "var(--fail)";
    if (s === "in_progress") return "var(--warn)";
    if (s === "resolved" || s === "closed") return "var(--pass)";
    return "var(--text-muted)";
  };

  return (
    <div style={{padding:"18px 22px 32px"}}>
      <div style={{display:"flex", alignItems:"center", marginBottom:14}}>
        <div className="spacer" />
        {window.can && window.can(currentUser, "write") && (
          <button className="btn sm accent" onClick={() => setShowCreate(true)}><Icon name="plus" /> Create defect</button>
        )}
      </div>

      {loading ? (
        <div className="mono dim" style={{padding:"24px 0", textAlign:"center"}}>Loading…</div>
      ) : defects.length === 0 ? (
        <div className="mono dim" style={{padding:"24px 0", textAlign:"center"}}>No defects linked to this test.</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th style={{width:90}}>ID</th>
              <th>Title</th>
              <th style={{width:130}}>Status</th>
              <th style={{width:90}}>Severity</th>
              <th style={{width:90}}>Run</th>
              <th style={{width:32}}></th>
            </tr>
          </thead>
          <tbody>
            {defects.map(d => (
              <tr key={d.id} style={d.status === "closed" ? {opacity:0.5} : {}}>
                <td className="mono" style={{fontSize:11.5}}>{d.id}</td>
                <td>
                  <div style={{fontWeight:500}}>{d.title}</div>
                  {d.description && <div style={{fontSize:11, color:"var(--text-muted)", marginTop:2, lineHeight:1.4}}>{d.description}</div>}
                </td>
                <td>
                  <select
                    className="input"
                    style={{fontSize:11, padding:"2px 6px", height:24, color:statusColor(d.status), background:"transparent", borderColor:"transparent", cursor:"pointer"}}
                    value={d.status}
                    onChange={e => handleStatusChange(d.id, e.target.value)}
                  >
                    <option value="open">open</option>
                    <option value="in_progress">in_progress</option>
                    <option value="resolved">resolved</option>
                    <option value="closed">closed</option>
                  </select>
                </td>
                <td><span className={"tag " + severityClass(d.severity)}>{d.severity}</span></td>
                <td className="mono dim" style={{fontSize:11}}>{d.run_id || "—"}</td>
                <td>
                  <button
                    className="btn ghost sm"
                    style={{color:"var(--fail)", padding:"2px 6px"}}
                    onClick={() => setDeleteConfirmId(d.id)}
                    title="Delete defect"
                  ><Icon name="x" /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showCreate && (
        <div style={{position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center"}} onClick={() => setShowCreate(false)}>
          <div style={{background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:8, padding:24, width:480}} onClick={e => e.stopPropagation()}>
            <h2 style={{fontSize:15, fontWeight:600, margin:"0 0 16px"}}>Create defect</h2>
            <div style={{display:"flex", flexDirection:"column", gap:10}}>
              <div>
                <label style={{fontSize:11, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:4}}>Title</label>
                <input className="input" style={{width:"100%", boxSizing:"border-box"}} value={form.title} placeholder="Describe the bug…" onChange={e => setForm(f => ({...f, title: e.target.value}))} autoFocus />
              </div>
              <div>
                <label style={{fontSize:11, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:4}}>Description (optional)</label>
                <textarea className="textarea" style={{width:"100%", boxSizing:"border-box", minHeight:60}} value={form.description} placeholder="Steps to reproduce, root cause hypothesis…" onChange={e => setForm(f => ({...f, description: e.target.value}))} />
              </div>
              <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:10}}>
                <div>
                  <label style={{fontSize:11, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:4}}>Severity</label>
                  <select className="input" value={form.severity} onChange={e => setForm(f => ({...f, severity: e.target.value}))}>
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="med">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>
                <div>
                  <label style={{fontSize:11, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:4}}>Linked run (optional)</label>
                  <select className="input" value={form.run_id} onChange={e => setForm(f => ({...f, run_id: e.target.value}))}>
                    <option value="">— none —</option>
                    {runs.map(r => <option key={r.id} value={r.id}>{r.id} · {r.name.slice(0,30)}</option>)}
                  </select>
                </div>
              </div>
            </div>
            <div style={{display:"flex", gap:8, justifyContent:"flex-end", marginTop:20}}>
              <button className="btn" onClick={() => setShowCreate(false)}>Cancel</button>
              <button className="btn accent" onClick={handleCreate} disabled={saving || !form.title.trim()}>
                {saving ? "Creating…" : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteConfirmId && (
        <div style={{position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center"}} onClick={() => setDeleteConfirmId(null)}>
          <div style={{background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:8, padding:24, width:360}} onClick={e => e.stopPropagation()}>
            <h2 style={{fontSize:15, fontWeight:600, margin:"0 0 10px"}}>Delete {deleteConfirmId}?</h2>
            <p style={{fontSize:12.5, color:"var(--text-muted)", margin:"0 0 20px"}}>This action is permanent.</p>
            <div style={{display:"flex", gap:8, justifyContent:"flex-end"}}>
              <button className="btn" onClick={() => setDeleteConfirmId(null)}>Cancel</button>
              <button className="btn" style={{background:"var(--fail)", color:"white", border:"none"}} onClick={() => handleDelete(deleteConfirmId)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RequirementsTab({ test, currentUser, onCountChange }) {
  const [reqs, setReqs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [linking, setLinking] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);

  const canWrite = window.can ? window.can(currentUser, "write") : true;

  const load = () => {
    setLoading(true);
    TH_API.getTestRequirements(test.id)
      .then(data => { setReqs(data); onCountChange && onCountChange(data.length); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, [test.id]);

  const searchReqs = async (q) => {
    if (!q.trim()) { setResults([]); return; }
    try {
      const data = await TH_API.getRequirements({ search: q });
      const linkedIds = new Set(reqs.map(r => r.id));
      setResults(data.filter(r => !linkedIds.has(r.id)));
    } catch (e) { setResults([]); }
  };

  const link = async (reqId) => {
    try {
      await TH_API.linkRequirementTest(reqId, test.id);
      setQuery(""); setResults([]); setLinking(false);
      load();
    } catch (e) {}
  };

  const unlink = async (reqId) => {
    try {
      await TH_API.unlinkRequirementTest(reqId, test.id);
      load();
    } catch (e) {}
  };

  const typeTag = t => t === "epic" ? "priority-high" : t === "story" ? "priority-med" : "priority-low";

  return (
    <div style={{padding:"18px 22px 32px"}}>
      <div style={{display:"flex", alignItems:"center", marginBottom:14}}>
        <div className="card-sub">Requirements this test helps verify.</div>
        <div className="spacer" />
        {canWrite && (
          <button className="btn sm accent" onClick={() => setLinking(v => !v)}><Icon name="link" /> Link requirement</button>
        )}
      </div>

      {linking && (
        <div className="card" style={{padding:12, marginBottom:14}}>
          <input
            className="input"
            style={{width:"100%", boxSizing:"border-box"}}
            placeholder="Search requirements to link…"
            value={query}
            onChange={e => { setQuery(e.target.value); searchReqs(e.target.value); }}
            autoFocus
          />
          {results.length > 0 && (
            <div style={{marginTop:8, display:"flex", flexDirection:"column", gap:4}}>
              {results.map(r => (
                <div key={r.id} className="nav-item" style={{padding:"6px 8px", cursor:"pointer", display:"flex", gap:8, alignItems:"center"}} onClick={() => link(r.id)}>
                  <span className="mono" style={{fontSize:11, color:"var(--text-dim)"}}>{r.id}</span>
                  <span style={{fontSize:12}}>{r.title}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {loading ? (
        <div className="mono dim" style={{padding:"24px 0", textAlign:"center"}}>Loading…</div>
      ) : reqs.length === 0 ? (
        <div className="mono dim" style={{padding:"24px 0", textAlign:"center"}}>No requirements linked to this test.</div>
      ) : (
        <div className="card" style={{padding:0}}>
          <table className="table">
            <thead>
              <tr>
                <th style={{width:90}}>ID</th>
                <th>Title</th>
                <th style={{width:80}}>Type</th>
                <th style={{width:200}}>Coverage</th>
                {canWrite && <th style={{width:32}}></th>}
              </tr>
            </thead>
            <tbody>
              {reqs.map(r => (
                <tr key={r.id}>
                  <td className="mono" style={{fontSize:11.5}}>{r.id}</td>
                  <td style={{fontWeight:500}}>{r.title}</td>
                  <td><span className={"tag " + typeTag(r.type)}>{r.type}</span></td>
                  <td><CoverageBar coverage={r.coverage} /></td>
                  {canWrite && (
                    <td>
                      <button className="btn ghost sm" style={{color:"var(--fail)", padding:"2px 6px"}} onClick={() => unlink(r.id)} title="Unlink"><Icon name="x" /></button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CommentsTab({test}) {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [posting, setPosting] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [reviewRequested, setReviewRequested] = useState(false);
  const [users, setUsers] = useState([]);
  const [mention, setMention] = useState(null); // { query, start }
  const [mentionIdx, setMentionIdx] = useState(0);
  const textareaRef = React.useRef(null);

  useEffect(() => {
    setLoading(true);
    TH_API.getTestComments(test.id)
      .then(data => { setComments(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [test.id]);

  useEffect(() => {
    if (typeof TH_API.getUsers === "function") {
      TH_API.getUsers().then(setUsers).catch(() => {});
    }
  }, []);

  const filteredUsers = mention
    ? users.filter(u => (u.display_name || u.username).toLowerCase().startsWith(mention.query.toLowerCase())).slice(0, 6)
    : [];

  const handleDraftChange = (e) => {
    const val = e.target.value;
    setDraft(val);
    const cursor = e.target.selectionStart;
    const textBefore = val.slice(0, cursor);
    const atIdx = textBefore.lastIndexOf("@");
    if (atIdx !== -1) {
      const fragment = textBefore.slice(atIdx + 1);
      if (!fragment.includes(" ") && !fragment.includes("\n")) {
        setMention({ query: fragment, start: atIdx });
        setMentionIdx(0);
        return;
      }
    }
    setMention(null);
  };

  const insertMention = (user) => {
    const name = user.display_name || user.username;
    const before = draft.slice(0, mention.start);
    const after = draft.slice(mention.start + 1 + mention.query.length);
    const newDraft = before + "@" + name + " " + after;
    setDraft(newDraft);
    setMention(null);
    setTimeout(() => {
      const pos = (before + "@" + name + " ").length;
      textareaRef.current?.setSelectionRange(pos, pos);
      textareaRef.current?.focus();
    }, 0);
  };

  const handleKeyDown = (e) => {
    if (mention && filteredUsers.length > 0) {
      if (e.key === "ArrowDown") { e.preventDefault(); setMentionIdx(i => (i + 1) % filteredUsers.length); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setMentionIdx(i => (i - 1 + filteredUsers.length) % filteredUsers.length); return; }
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); insertMention(filteredUsers[mentionIdx]); return; }
      if (e.key === "Escape") { setMention(null); return; }
    }
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handlePost();
  };

  const handlePost = async () => {
    if (!draft.trim()) return;
    setPosting(true);
    try {
      const c = await TH_API.addComment(test.id, "You", draft.trim());
      setComments(prev => [...prev, c]);
      setDraft("");
    } catch (e) {}
    setPosting(false);
  };

  const handleRequestReview = async () => {
    setRequesting(true);
    try {
      const c = await TH_API.addComment(test.id, "You", "Requested a review on this test.");
      setComments(prev => [...prev, c]);
      setReviewRequested(true);
    } catch (e) {}
    setRequesting(false);
  };

  return (
    <div style={{padding:"18px 22px 32px", maxWidth:760}}>
      {loading ? (
        <div className="mono dim" style={{padding:"24px 0", textAlign:"center"}}>Loading…</div>
      ) : comments.length === 0 ? (
        <div className="mono dim" style={{padding:"14px 0"}}>No comments yet.</div>
      ) : (
        comments.map(c => (
          <div key={c.id} style={{display:"flex", gap:12, padding:"14px 0", borderBottom:"1px solid var(--border)"}}>
            <div className="avatar">{c.who.split(" ").map(x=>x[0]).join("").slice(0,2)}</div>
            <div style={{flex:1}}>
              <div style={{display:"flex", gap:8, alignItems:"baseline"}}>
                <b style={{fontSize:12.5}}>{c.who}</b>
                <span className="mono dim" style={{fontSize:10.5}}>{c.when}</span>
              </div>
              <div style={{fontSize:12.5, color:"var(--text-muted)", marginTop:4, lineHeight:1.5}}>{c.text}</div>
            </div>
          </div>
        ))
      )}
      <div style={{position:"relative", marginTop:14}}>
        <textarea
          ref={textareaRef}
          className="textarea"
          placeholder="Add a comment… @ to mention, : for emoji, # to link a test"
          style={{fontFamily:"var(--font-sans)", fontSize:12.5, width:"100%", boxSizing:"border-box"}}
          value={draft}
          onChange={handleDraftChange}
          onKeyDown={handleKeyDown}
          onBlur={() => setTimeout(() => setMention(null), 150)}
        />
        {mention && filteredUsers.length > 0 && (
          <div style={{
            position:"absolute", bottom:"calc(100% + 4px)", left:0,
            background:"var(--bg-card, #1e1e2e)", border:"1px solid var(--border)",
            borderRadius:6, boxShadow:"0 4px 16px rgba(0,0,0,.3)", minWidth:200, zIndex:100,
          }}>
            {filteredUsers.map((u, i) => (
              <div
                key={u.username}
                onMouseDown={() => insertMention(u)}
                style={{
                  display:"flex", alignItems:"center", gap:8, padding:"7px 12px",
                  cursor:"pointer", fontSize:12.5,
                  background: i === mentionIdx ? "var(--bg-hover, rgba(255,255,255,.06))" : "transparent",
                }}
                onMouseEnter={() => setMentionIdx(i)}
              >
                <div className="avatar" style={{width:22, height:22, fontSize:9, flexShrink:0}}>
                  {(u.display_name || u.username).split(" ").map(x=>x[0]).join("").slice(0,2).toUpperCase()}
                </div>
                <span>{u.display_name || u.username}</span>
                <span className="mono dim" style={{fontSize:10.5, marginLeft:"auto"}}>@{u.username}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div style={{display:"flex", gap:6, marginTop:8}}>
        <button className="btn primary sm" onClick={handlePost} disabled={posting || !draft.trim()}>
          {posting ? "Posting…" : "Comment"}
        </button>
        <button className="btn sm" onClick={handleRequestReview} disabled={requesting || reviewRequested}>
          {reviewRequested ? "Review requested" : requesting ? "Requesting…" : "Request review"}
        </button>
      </div>
    </div>
  );
}

function GitHistoryTab({test}) {
  const ref = test.source_ref || "";
  const base = test.repo_url ? test.repo_url.replace(/\.git$/, "").replace(/\/$/, "") : "";
  const fileUrl = base && ref && test.source_path ? `${base}/blob/${ref}/${test.source_path}` : null;
  const historyUrl = base && test.source_path ? `${base}/commits/${ref || ""}/${test.source_path}` : null;

  if (!test.source_path) {
    return (
      <div style={{padding:"18px 22px 32px"}}>
        <div className="empty" style={{padding:"48px 18px", textAlign:"center"}}>
          <div style={{fontSize:13, marginBottom:6}}>No linked source.</div>
          <div className="mono dim" style={{fontSize:11}}>
            Sync a repository (Configure → GitHub) to link this test to a file and its commit history.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{padding:"18px 22px 32px"}}>
      <div className="card">
        <div className="card-h">
          <div className="card-title mono" style={{fontSize:11.5}}>{test.source_path}</div>
          <div className="spacer" />
          {ref && <div className="mono dim" style={{fontSize:11}}>@ {ref.slice(0, 8)}</div>}
        </div>
        <div style={{padding:"14px", display:"flex", flexDirection:"column", gap:10, fontSize:12.5}}>
          <Detail label="Repository" value={base
            ? <a href={base} target="_blank" rel="noreferrer" className="mono">{base.replace(/^https?:\/\//, "")}</a>
            : <span className="mono dim">—</span>} />
          <Detail label="Ref" value={<span className="mono">{ref || "—"}</span>} />
          <div style={{display:"flex", gap:8, marginTop:4}}>
            {fileUrl && <a href={fileUrl} target="_blank" rel="noreferrer" className="btn sm"><Icon name="github" /> View file</a>}
            {historyUrl && <a href={historyUrl} target="_blank" rel="noreferrer" className="btn sm ghost">Commit history</a>}
          </div>
        </div>
      </div>
    </div>
  );
}

window.TestDetail = TestDetail;
window.Detail = Detail;
