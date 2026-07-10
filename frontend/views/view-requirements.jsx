// Requirements view — features/stories/epics with test coverage

function CoverageBar({ coverage }) {
  const c = coverage || { linked: 0, passed: 0, failed: 0, untested: 0, pass_rate: 0 };
  if (!c.linked) {
    return <span className="mono dim" style={{fontSize:11}}>no tests</span>;
  }
  const pct = n => `${(n / c.linked) * 100}%`;
  return (
    <div style={{display:"flex", alignItems:"center", gap:8, minWidth:180}}>
      <div style={{flex:1, height:8, borderRadius:4, overflow:"hidden", display:"flex", background:"var(--bg-3)"}}>
        {c.passed > 0 && <div style={{width:pct(c.passed), background:"var(--pass)"}} />}
        {c.failed > 0 && <div style={{width:pct(c.failed), background:"var(--fail)"}} />}
        {c.untested > 0 && <div style={{width:pct(c.untested), background:"var(--text-dim)"}} />}
      </div>
      <span className="mono" style={{fontSize:11, color: c.failed ? "var(--fail)" : c.untested ? "var(--warn)" : "var(--pass)", minWidth:34, textAlign:"right"}}>
        {Math.round(c.pass_rate * 100)}%
      </span>
    </div>
  );
}

function Requirements({ currentUser }) {
  const [requirements, setRequirements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState("all");
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterCovered, setFilterCovered] = useState("all");
  const [editing, setEditing] = useState(null); // requirement object or {} for new
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);

  const canWrite = !currentUser || ["admin", "manager", "tester"].includes(currentUser.role);
  const canDelete = !currentUser || currentUser.role === "admin";

  const load = () => {
    setLoading(true);
    TH_API.getRequirements({ status: filterStatus, type: filterType, covered: filterCovered, search })
      .then(data => { setRequirements(data); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, [filterStatus, filterType, filterCovered]);

  const handleSearch = (e) => { if (e.key === "Enter") load(); };

  const handleDelete = async (id) => {
    try {
      await TH_API.deleteRequirement(id);
      setRequirements(prev => prev.filter(r => r.id !== id));
    } catch (e) {}
    setDeleteConfirmId(null);
  };

  const onSaved = (r, isNew) => {
    setRequirements(prev => isNew ? [r, ...prev] : prev.map(x => x.id === r.id ? r : x));
    setEditing(null);
  };

  const total = requirements.length;
  const uncovered = requirements.filter(r => r.coverage.linked === 0).length;
  const atRisk = requirements.filter(r => r.coverage.failed > 0).length;

  const typeTag = t => t === "epic" ? "priority-high" : t === "story" ? "priority-med" : "priority-low";
  const statusColor = s => {
    if (s === "active") return "var(--pass)";
    if (s === "draft") return "var(--warn)";
    if (s === "deprecated") return "var(--text-dim)";
    return "var(--text-muted)";
  };

  return (
    <div style={{display:"flex", flexDirection:"column", height:"100%"}}>
      <div className="page-h" style={{padding:"18px 22px 0", marginBottom:14}}>
        <div>
          <h1 className="page-title">Requirements</h1>
          <div className="page-sub">Features, stories, and epics — track which are covered by tests and which are at risk.</div>
        </div>
        {canWrite && (
          <div className="actions">
            <button className="btn accent" onClick={() => setEditing({})}><Icon name="plus" /> New requirement</button>
          </div>
        )}
      </div>

      {/* Summary chips */}
      <div style={{display:"flex", gap:8, padding:"0 22px 14px"}}>
        {[
          { label: "Total", count: total, color: "var(--text)", covered: "all" },
          { label: "Uncovered", count: uncovered, color: "var(--warn)", covered: "false" },
          { label: "At risk (failing)", count: atRisk, color: "var(--fail)", covered: "all", risk: true },
        ].map(c => (
          <button
            key={c.label}
            className={"btn sm" + (filterCovered === c.covered && !c.risk && c.covered !== "all" ? " accent" : "")}
            style={{gap:6}}
            onClick={() => { if (!c.risk) setFilterCovered(filterCovered === c.covered ? "all" : c.covered); }}
          >
            <span style={{color:c.color, fontWeight:700}}>{c.count}</span>
            <span>{c.label}</span>
          </button>
        ))}
      </div>

      {/* Filters */}
      <div style={{display:"flex", gap:8, padding:"0 22px 10px", alignItems:"center"}}>
        <input className="input" style={{width:220}} placeholder="Search requirements…" value={search} onChange={e => setSearch(e.target.value)} onKeyDown={handleSearch} />
        <select className="input" style={{width:120}} value={filterType} onChange={e => setFilterType(e.target.value)}>
          <option value="all">All types</option>
          <option value="epic">Epic</option>
          <option value="story">Story</option>
          <option value="feature">Feature</option>
        </select>
        <select className="input" style={{width:120}} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="draft">Draft</option>
          <option value="done">Done</option>
          <option value="deprecated">Deprecated</option>
        </select>
        <select className="input" style={{width:130}} value={filterCovered} onChange={e => setFilterCovered(e.target.value)}>
          <option value="all">Any coverage</option>
          <option value="true">Covered</option>
          <option value="false">Uncovered</option>
        </select>
        {(search || filterType !== "all" || filterStatus !== "all" || filterCovered !== "all") && (
          <button className="btn sm ghost" onClick={() => { setSearch(""); setFilterType("all"); setFilterStatus("all"); setFilterCovered("all"); }}>Clear</button>
        )}
        <div className="spacer" />
        <span className="mono dim" style={{fontSize:11}}>{requirements.length} requirement{requirements.length !== 1 ? "s" : ""}</span>
      </div>

      {/* Table */}
      <div style={{flex:1, overflowY:"auto", padding:"0 22px 32px"}}>
        <div className="card" style={{padding:0}}>
          {loading ? (
            <div className="mono dim" style={{padding:"32px", textAlign:"center"}}>Loading…</div>
          ) : requirements.length === 0 ? (
            <div className="mono dim" style={{padding:"32px", textAlign:"center"}}>No requirements found.</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th style={{width:90}}>ID</th>
                  <th>Title</th>
                  <th style={{width:80}}>Type</th>
                  <th style={{width:90}}>Status</th>
                  <th style={{width:200}}>Coverage</th>
                  <th style={{width:70}}>Tests</th>
                  <th style={{width:64}}></th>
                </tr>
              </thead>
              <tbody>
                {requirements.map(r => (
                  <tr key={r.id} style={r.status === "deprecated" ? {opacity:0.5} : {}}>
                    <td className="mono" style={{fontSize:11.5}}>
                      {r.id}
                      {r.external_key && (
                        <a href={r.external_url || "#"} target="_blank" rel="noreferrer" title="View in tracker" style={{display:"block", fontSize:10, color:"var(--accent)", textDecoration:"none"}}>
                          {r.external_key}
                        </a>
                      )}
                    </td>
                    <td>
                      <div style={{fontWeight:500}}>{r.title}</div>
                      {r.description && (
                        <div style={{fontSize:11, color:"var(--text-muted)", marginTop:2, lineHeight:1.4, maxWidth:480, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{r.description}</div>
                      )}
                      {r.owner && <div style={{fontSize:10.5, color:"var(--text-dim)", marginTop:2}}>Owner {r.owner}</div>}
                    </td>
                    <td><span className={"tag " + typeTag(r.type)}>{r.type}</span></td>
                    <td><span style={{fontSize:11.5, color:statusColor(r.status)}}>{r.status}</span></td>
                    <td><CoverageBar coverage={r.coverage} /></td>
                    <td className="mono dim" style={{fontSize:11}}>{r.coverage.linked}</td>
                    <td>
                      <div style={{display:"flex", gap:2}}>
                        {canWrite && <button className="btn ghost sm" style={{padding:"2px 6px"}} onClick={() => setEditing(r)} title="Edit"><Icon name="settings" /></button>}
                        {canDelete && <button className="btn ghost sm" style={{color:"var(--fail)", padding:"2px 6px"}} onClick={() => setDeleteConfirmId(r.id)} title="Delete"><Icon name="x" /></button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {editing && (
        <RequirementModal
          requirement={editing.id ? editing : null}
          onClose={() => setEditing(null)}
          onSaved={onSaved}
        />
      )}

      {deleteConfirmId && (
        <div style={{position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center"}} onClick={() => setDeleteConfirmId(null)}>
          <div style={{background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:8, padding:24, width:360}} onClick={e => e.stopPropagation()}>
            <h2 style={{fontSize:15, fontWeight:600, margin:"0 0 10px"}}>Delete {deleteConfirmId}?</h2>
            <p style={{fontSize:12.5, color:"var(--text-muted)", margin:"0 0 20px"}}>This unlinks it from all tests. Permanent.</p>
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

function TestPicker({ selected, onChange }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);

  const runSearch = async (q) => {
    if (!q.trim()) { setResults([]); return; }
    try {
      const data = await TH_API.listTests({ search: q, limit: 20 });
      setResults(data);
    } catch (e) { setResults([]); }
  };

  const add = (id) => { if (!selected.includes(id)) onChange([...selected, id]); setQuery(""); setResults([]); setOpen(false); };
  const remove = (id) => onChange(selected.filter(x => x !== id));

  return (
    <div>
      <div style={{display:"flex", flexWrap:"wrap", gap:6, marginBottom:6}}>
        {selected.map(id => (
          <span key={id} className="tag" style={{display:"inline-flex", alignItems:"center", gap:4}}>
            <span className="mono" style={{fontSize:11}}>{id}</span>
            <button className="btn ghost sm" style={{padding:0, width:16, height:16, lineHeight:1}} onClick={() => remove(id)} title="Remove"><Icon name="x" /></button>
          </span>
        ))}
        {selected.length === 0 && <span className="mono dim" style={{fontSize:11}}>No tests linked yet.</span>}
      </div>
      <div style={{position:"relative"}}>
        <input
          className="input"
          style={{width:"100%", boxSizing:"border-box"}}
          placeholder="Search tests to link (id or title)…"
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true); runSearch(e.target.value); }}
          onFocus={() => setOpen(true)}
        />
        {open && results.length > 0 && (
          <div style={{position:"absolute", top:"100%", left:0, right:0, zIndex:10, background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:6, marginTop:2, maxHeight:200, overflowY:"auto"}}>
            {results.map(t => (
              <div key={t.id} className="nav-item" style={{padding:"6px 10px", cursor:"pointer", display:"flex", gap:8, alignItems:"center"}} onClick={() => add(t.id)}>
                <span className="mono" style={{fontSize:11, color:"var(--text-dim)"}}>{t.id}</span>
                <span style={{fontSize:12, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{t.title}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function RequirementModal({ requirement, onClose, onSaved }) {
  const isNew = !requirement;
  const [form, setForm] = useState({
    title: requirement?.title || "",
    type: requirement?.type || "feature",
    status: requirement?.status || "active",
    priority: requirement?.priority || "med",
    owner: requirement?.owner || "",
    description: requirement?.description || "",
    test_ids: requirement?.test_ids || [],
  });
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const payload = {
        title: form.title.trim(),
        type: form.type,
        status: form.status,
        priority: form.priority,
        owner: form.owner.trim() || null,
        description: form.description.trim() || null,
        test_ids: form.test_ids,
      };
      const r = isNew
        ? await TH_API.createRequirement(payload)
        : await TH_API.updateRequirement(requirement.id, payload);
      onSaved(r, isNew);
    } catch (e) {}
    setSaving(false);
  };

  const L = { fontSize:11, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:4 };

  return (
    <div style={{position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center"}} onClick={onClose}>
      <div style={{background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:8, padding:24, width:520, maxHeight:"85vh", overflowY:"auto"}} onClick={e => e.stopPropagation()}>
        <h2 style={{fontSize:15, fontWeight:600, margin:"0 0 16px"}}>{isNew ? "New requirement" : `Edit ${requirement.id}`}</h2>
        <div style={{display:"flex", flexDirection:"column", gap:10}}>
          <div>
            <label style={L}>Title</label>
            <input className="input" style={{width:"100%", boxSizing:"border-box"}} value={form.title} placeholder="e.g. Guest checkout" onChange={e => setForm(f => ({...f, title: e.target.value}))} autoFocus />
          </div>
          <div style={{display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:10}}>
            <div>
              <label style={L}>Type</label>
              <select className="input" value={form.type} onChange={e => setForm(f => ({...f, type: e.target.value}))}>
                <option value="epic">Epic</option>
                <option value="story">Story</option>
                <option value="feature">Feature</option>
              </select>
            </div>
            <div>
              <label style={L}>Status</label>
              <select className="input" value={form.status} onChange={e => setForm(f => ({...f, status: e.target.value}))}>
                <option value="active">Active</option>
                <option value="draft">Draft</option>
                <option value="done">Done</option>
                <option value="deprecated">Deprecated</option>
              </select>
            </div>
            <div>
              <label style={L}>Priority</label>
              <select className="input" value={form.priority} onChange={e => setForm(f => ({...f, priority: e.target.value}))}>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="med">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
          </div>
          <div>
            <label style={L}>Owner (optional)</label>
            <input className="input" style={{width:"100%", boxSizing:"border-box"}} value={form.owner} placeholder="anna@example.com" onChange={e => setForm(f => ({...f, owner: e.target.value}))} />
          </div>
          <div>
            <label style={L}>Description (optional)</label>
            <textarea className="textarea" style={{width:"100%", boxSizing:"border-box", minHeight:60}} value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))} />
          </div>
          <div>
            <label style={L}>Linked tests</label>
            <TestPicker selected={form.test_ids} onChange={ids => setForm(f => ({...f, test_ids: ids}))} />
          </div>
        </div>
        {!isNew && (
          <div style={{marginTop:18, borderTop:"1px solid var(--border)", paddingTop:6}}>
            <label style={L}>Change history</label>
            <div style={{marginLeft:-22, marginRight:-22}}>
              <ChangeHistory entityType="requirement" entityId={requirement.id} />
            </div>
          </div>
        )}
        <div style={{display:"flex", gap:8, justifyContent:"flex-end", marginTop:20}}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn accent" onClick={save} disabled={saving || !form.title.trim()}>
            {saving ? "Saving…" : (isNew ? "Create" : "Save")}
          </button>
        </div>
      </div>
    </div>
  );
}

window.Requirements = Requirements;
window.CoverageBar = CoverageBar;
