// Library view — test case management

function Library({ onNav, onOpenTest, currentUser }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data: D, loading, error } = useInitialData(refreshKey);
  const [openFolders, setOpenFolders] = useState({ auth: true, checkout: true });
  const [activeFolder, setActiveFolder] = useState(null);
  const [favoritedIds, setFavoritedIds] = useState(new Set());
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterType, setFilterType] = useState("all");
  const [filterStatusOpen, setFilterStatusOpen] = useState(false);
  const [filterTypeOpen, setFilterTypeOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [tests, setTests] = useState(null);
  const [testsLoading, setTestsLoading] = useState(true);
  const [view, setView] = useState("list");
  const [selected, setSelected] = useState(new Set());
  const [showNewTest, setShowNewTest] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [bulkDeleteConfirm, setBulkDeleteConfirm] = useState(false);
  const [bulkStatusOpen, setBulkStatusOpen] = useState(false);
  const [bulkFolderOpen, setBulkFolderOpen] = useState(false);
  const [exportingCSV, setExportingCSV] = useState(false);

  const refresh = () => { setRefreshKey(k => k + 1); setSelected(new Set()); };

  useEffect(() => {
    window.TH_API.getFavorites().then(data => setFavoritedIds(new Set(data.map(f => f.folder_id)))).catch(() => {});
  }, []);

  const toggleFavorite = async (e, folderId) => {
    e.stopPropagation();
    try {
      if (favoritedIds.has(folderId)) {
        await window.TH_API.removeFavorite(folderId);
        setFavoritedIds(s => { const n = new Set(s); n.delete(folderId); return n; });
      } else {
        await window.TH_API.addFavorite(folderId);
        setFavoritedIds(s => new Set([...s, folderId]));
      }
      window.dispatchEvent(new CustomEvent("favorites-changed"));
    } catch {}
  };

  useEffect(() => {
    const tid = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(tid);
  }, [search]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (activeFolder) params.set("folder_id", activeFolder);
    if (debouncedSearch) params.set("search", debouncedSearch);
    if (filterStatus !== "all") params.set("status", filterStatus);
    if (filterType !== "all") params.set("type", filterType);
    setTestsLoading(true);
    fetch(`/api/tests?${params}`, { headers: window.authHeaders() })
      .then(r => r.json())
      .then(data => {
        setTests(data.map(t => ({ ...t, folder: t.folder_id, lastRun: t.last_run_at, updated: t.updated_at })));
        setTestsLoading(false);
      })
      .catch(() => setTestsLoading(false));
  }, [activeFolder, debouncedSearch, filterStatus, filterType, refreshKey]);

  const selectFolder = (id) => {
    window.__currentFolderId = id;  // expose for AIAssistant cross-view navigation
    setActiveFolder(id);
  };

  const toggleFolder = (id) => setOpenFolders(s => ({...s, [id]: !s[id]}));

  const allFolderIds = useMemo(() => {
    if (!D) return [];
    const result = [];
    D.folders.forEach(f => {
      result.push(f.id);
      if (f.children) f.children.forEach(c => result.push(c.id));
    });
    return result;
  }, [D]);

  const filtered = tests ?? [];

  const toggleSel = (id) => {
    setSelected(s => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  const handleDeleteRow = async (t, e) => {
    e.stopPropagation();
    setDeleteTarget(t);
  };

  const confirmDelete = async () => {
    try {
      await fetch(`/api/tests/${deleteTarget.id}`, { method: "DELETE", headers: { "Authorization": `Bearer ${localStorage.getItem("th_token")}` } });
    } catch (e) {}
    setDeleteTarget(null);
    refresh();
  };

  const handleBulkDelete = async () => {
    try {
      await fetch("/api/tests/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("th_token")}` },
        body: JSON.stringify({ action: "delete", ids: [...selected] }),
      });
    } catch (e) {}
    setBulkDeleteConfirm(false);
    refresh();
  };

  const handleBulkStatus = async (status) => {
    try {
      await fetch("/api/tests/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("th_token")}` },
        body: JSON.stringify({ action: "update", ids: [...selected], payload: { status } }),
      });
    } catch (e) {}
    setBulkStatusOpen(false);
    refresh();
  };

  const handleBulkFolder = async (folder_id) => {
    try {
      await fetch("/api/tests/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("th_token")}` },
        body: JSON.stringify({ action: "update", ids: [...selected], payload: { folder_id } }),
      });
    } catch (e) {}
    setBulkFolderOpen(false);
    refresh();
  };

  if (loading && !D) return (
    <div style={{display:"flex", height:"100%", alignItems:"center", justifyContent:"center"}}>
      <span className="mono dim">Loading…</span>
    </div>
  );

  if (!D) return (
    <div style={{display:"flex", height:"100%", alignItems:"center", justifyContent:"center"}}>
      <span className="mono dim">Error loading data{error ? `: ${error}` : ""}.</span>
    </div>
  );

  const totalCount = D.tests.length;
  const allFoldersList = D.folders.flatMap(f => [f, ...(f.children || [])]);

  return (
    <div style={{display:"grid", gridTemplateColumns:"260px 1fr", height:"100%", overflow:"hidden"}}>
      {/* Tree sidebar */}
      <div style={{borderRight:"1px solid var(--border)", display:"flex", flexDirection:"column", background:"var(--bg-2)", overflow:"hidden"}}>
        <div style={{padding:"12px 12px 6px", display:"flex", alignItems:"center", gap:8, borderBottom:"1px solid var(--border)"}}>
          <div style={{fontSize:12, fontWeight:600}}>Folders</div>
          <div className="card-sub" style={{fontSize:10.5}}>{totalCount} tests</div>
          {window.can && window.can(currentUser, "write") && (
            <button className="btn ghost icon" style={{marginLeft:"auto"}} onClick={() => setShowNewTest(true)}><Icon name="plus" /></button>
          )}
        </div>
        <div className="tree" style={{padding:"8px 8px", overflowY:"auto", flex:1}}>
          <div className={"tree-row" + (activeFolder === null ? " active" : "")} onClick={() => selectFolder(null)}>
            <span className="caret"></span>
            <Icon name="grid" />
            <span>All tests</span>
            <span className="count">{totalCount}</span>
          </div>
          {D.folders.map(f => (
            <React.Fragment key={f.id}>
              <div className={"tree-row" + (activeFolder === f.id ? " active" : "")} onClick={() => { toggleFolder(f.id); selectFolder(f.id); }}>
                <span className={"caret" + (openFolders[f.id] ? " open" : "")}>{f.children ? <Icon name="chev" /> : null}</span>
                <span style={{color:"var(--warn)"}}>▣</span>
                <span>{f.name}</span>
                <span className="count">{f.count}</span>
                <span
                  title={favoritedIds.has(f.id) ? "Remove from favorites" : "Add to favorites"}
                  style={{marginLeft:"auto", cursor:"pointer", color: favoritedIds.has(f.id) ? "var(--warn)" : "var(--text-dim)", fontSize:12, lineHeight:1}}
                  onClick={(e) => toggleFavorite(e, f.id)}
                >{favoritedIds.has(f.id) ? "★" : "☆"}</span>
              </div>
              {openFolders[f.id] && f.children && f.children.map(c => (
                <div
                  key={c.id}
                  className={"tree-row" + (activeFolder === c.id ? " active" : "")}
                  style={{paddingLeft: 28}}
                  onClick={() => selectFolder(c.id)}
                >
                  <span style={{color:"var(--text-dim)", fontSize:10}}>—</span>
                  <span>{c.name}</span>
                  <span className="count">{c.count}</span>
                  <span
                    title={favoritedIds.has(c.id) ? "Remove from favorites" : "Add to favorites"}
                    style={{marginLeft:"auto", cursor:"pointer", color: favoritedIds.has(c.id) ? "var(--warn)" : "var(--text-dim)", fontSize:12, lineHeight:1}}
                    onClick={(e) => toggleFavorite(e, c.id)}
                  >{favoritedIds.has(c.id) ? "★" : "☆"}</span>
                </div>
              ))}
            </React.Fragment>
          ))}
        </div>
        <div style={{padding:"10px 12px", borderTop:"1px solid var(--border)", fontSize:11, color:"var(--text-dim)"}}>
          <div className="mono" style={{fontSize:10.5}}>tests/ is synced from git</div>
          <div style={{display:"flex", alignItems:"center", gap:6, marginTop:4}}>
            <span className="status pass" style={{padding:"1px 5px"}}>UP TO DATE</span>
            <span className="mono dim">main · a3c9f1d</span>
          </div>
        </div>
      </div>

      {/* Main */}
      <div style={{display:"flex", flexDirection:"column", overflow:"hidden"}}>
        {/* Toolbar */}
        <div className="toolbar">
          <div style={{fontSize:14, fontWeight:600, marginRight:8}}>
            {activeFolder ? (D.folders.find(f=>f.id===activeFolder)?.name || D.folders.flatMap(f=>f.children||[]).find(c=>c.id===activeFolder)?.name) : "All tests"}
          </div>
          <div className="card-sub">{testsLoading ? "…" : `${filtered.length} tests`}</div>
          <div className="spacer" />

          <input
            className="input"
            style={{height:28, fontSize:12, padding:"2px 8px", width:180}}
            placeholder="Search tests…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />

          <div style={{position:"relative"}}>
            <div className={"chip" + (filterStatus !== "all" ? " active" : "")} onClick={() => { setFilterStatusOpen(o => !o); setFilterTypeOpen(false); }}>
              <Icon name="filter" />
              Status: <b style={{marginLeft:2, color:"var(--text)"}}>{filterStatus}</b>
            </div>
            {filterStatusOpen && (
              <>
                <div style={{position:"fixed", inset:0, zIndex:99}} onClick={() => setFilterStatusOpen(false)} />
                <div style={{position:"absolute", top:"100%", right:0, zIndex:100, background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:"var(--radius)", minWidth:130, marginTop:4, boxShadow:"0 4px 12px rgba(0,0,0,0.3)", overflow:"hidden"}}>
                  {["all","pass","fail","warn","skip","pending"].map(st => (
                    <div key={st} style={{padding:"7px 12px", cursor:"pointer", background: st === filterStatus ? "var(--accent-soft)" : "transparent", fontSize:12}}
                      onClick={() => { setFilterStatus(st); setFilterStatusOpen(false); }}>
                      {st === "all" ? "All statuses" : <StatusBadge s={st} />}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          <div style={{position:"relative"}}>
            <div className={"chip" + (filterType !== "all" ? " active" : "")} onClick={() => { setFilterTypeOpen(o => !o); setFilterStatusOpen(false); }}>
              Type: <b style={{color:"var(--text)", marginLeft:2}}>{filterType}</b>
            </div>
            {filterTypeOpen && (
              <>
                <div style={{position:"fixed", inset:0, zIndex:99}} onClick={() => setFilterTypeOpen(false)} />
                <div style={{position:"absolute", top:"100%", right:0, zIndex:100, background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:"var(--radius)", minWidth:130, marginTop:4, boxShadow:"0 4px 12px rgba(0,0,0,0.3)", overflow:"hidden"}}>
                  {[["all","All types"],["manual","Manual"],["automated","Automated"]].map(([v,label]) => (
                    <div key={v} style={{padding:"7px 12px", cursor:"pointer", background: v === filterType ? "var(--accent-soft)" : "transparent", fontSize:12}}
                      onClick={() => { setFilterType(v); setFilterTypeOpen(false); }}>
                      {label}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          <div className="chip">Owner: <b style={{color:"var(--text)", marginLeft:2}}>any</b></div>

          <div style={{display:"flex", border:"1px solid var(--border)", borderRadius:"var(--radius)", overflow:"hidden", marginLeft:8}}>
            <button className={"btn ghost icon"} style={{background: view==="list" ? "var(--surface-2)" : "transparent", borderRadius:0}} onClick={() => setView("list")}><Icon name="list" /></button>
            <button className={"btn ghost icon"} style={{background: view==="grid" ? "var(--surface-2)" : "transparent", borderRadius:0, borderLeft:"1px solid var(--border)"}} onClick={() => setView("grid")}><Icon name="grid" /></button>
          </div>

          {window.can && window.can(currentUser, "write") && (
            <button className="btn accent sm" onClick={() => setShowNewTest(true)}><Icon name="plus" /> New test</button>
          )}
          <button
            className="btn sm"
            onClick={async () => {
              setExportingCSV(true);
              try { await window.TH_API.exportTestsCSV(activeFolder); } catch (_) {}
              setExportingCSV(false);
            }}
            disabled={exportingCSV}
            style={{marginLeft: 6}}
          >
            {exportingCSV ? "Exporting…" : "Export CSV"}
          </button>
        </div>

        {/* Bulk actions toolbar */}
        {selected.size > 0 && (
          <div style={{padding:"6px 22px", background:"var(--accent-soft)", borderBottom:"1px solid var(--border)", display:"flex", alignItems:"center", gap:10, fontSize:12, position:"relative"}}>
            <b className="mono">{selected.size} selected</b>
            {window.can && window.can(currentUser, "write") && (
              <div style={{position:"relative"}}>
                <button className="btn sm" onClick={() => { setBulkFolderOpen(o => !o); setBulkStatusOpen(false); }}>Move to folder</button>
                {bulkFolderOpen && (
                  <>
                    <div style={{position:"fixed", inset:0, zIndex:99}} onClick={() => setBulkFolderOpen(false)} />
                    <div style={{position:"absolute", top:"100%", left:0, zIndex:100, background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:"var(--radius)", minWidth:180, marginTop:4, boxShadow:"0 4px 12px rgba(0,0,0,0.3)", overflow:"hidden"}}>
                      {allFoldersList.map(f => (
                        <div key={f.id} style={{padding:"8px 14px", cursor:"pointer", fontSize:12}} onClick={() => handleBulkFolder(f.id)}>{f.name}</div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {window.can && window.can(currentUser, "write") && (
              <div style={{position:"relative"}}>
                <button className="btn sm" onClick={() => { setBulkStatusOpen(o => !o); setBulkFolderOpen(false); }}>Set status</button>
                {bulkStatusOpen && (
                  <>
                    <div style={{position:"fixed", inset:0, zIndex:99}} onClick={() => setBulkStatusOpen(false)} />
                    <div style={{position:"absolute", top:"100%", left:0, zIndex:100, background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:"var(--radius)", minWidth:120, marginTop:4, boxShadow:"0 4px 12px rgba(0,0,0,0.3)", overflow:"hidden"}}>
                      {["pass","fail","warn","skip","pending"].map(st => (
                        <div key={st} style={{padding:"7px 12px", cursor:"pointer"}} onClick={() => handleBulkStatus(st)}>
                          <StatusBadge s={st} />
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {window.can && window.can(currentUser, "delete") && (
              <button className="btn sm" style={{color:"var(--fail)"}} onClick={() => setBulkDeleteConfirm(true)}>Delete</button>
            )}
            <button className="btn ghost sm" style={{marginLeft:"auto"}} onClick={() => setSelected(new Set())}>Clear</button>
          </div>
        )}

        {/* List */}
        <div style={{overflowY:"auto", flex:1}}>
          {view === "list" ? (
            <table className="table">
              <thead>
                <tr>
                  <th style={{width:28}}></th>
                  <th style={{width:80}}>ID</th>
                  <th>Title</th>
                  <th style={{width:90}}>Type</th>
                  <th style={{width:100}}>Status</th>
                  <th style={{width:80}}>Priority</th>
                  <th style={{width:100}}>Tags</th>
                  <th style={{width:60}}>Owner</th>
                  <th style={{width:80}}>Last run</th>
                  <th style={{width:80}}>Duration</th>
                  <th style={{width:36}}></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(t => (
                  <tr key={t.id} className={selected.has(t.id) ? "selected" : ""} style={{cursor:"pointer"}} onClick={() => onOpenTest(t.id)}>
                    <td onClick={(e) => { e.stopPropagation(); toggleSel(t.id); }}>
                      <input type="checkbox" checked={selected.has(t.id)} readOnly />
                    </td>
                    <td className="mono">{t.id}</td>
                    <td>
                      <div style={{display:"flex", alignItems:"center", gap:8}}>
                        <span>{t.title}</span>
                      </div>
                    </td>
                    <td>
                      {t.auto
                        ? <span className="tag" style={{color:"var(--info)", borderColor:"oklch(from var(--info) l c h / 0.3)"}}>auto · {t.runner}</span>
                        : <span className="tag">manual</span>}
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <StatusSelect s={t.status} testId={t.id} onChanged={refresh} />
                    </td>
                    <td><span className={"tag priority-" + (t.priority === "high" ? "high" : t.priority === "med" ? "med" : "low")}>{t.priority}</span></td>
                    <td>
                      <div style={{display:"flex", gap:3, flexWrap:"wrap"}}>
                        {t.tags.slice(0,2).map(tg => <span key={tg} className="tag">{tg}</span>)}
                      </div>
                    </td>
                    <td className="mono dim">{t.owner}</td>
                    <td className="mono dim">{t.lastRun}</td>
                    <td className="mono dim">{t.duration}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {window.can && window.can(currentUser, "delete") && (
                        <button className="btn ghost icon sm" style={{opacity:0.5}} title="Delete test" onClick={(e) => handleDeleteRow(t, e)}>
                          <Icon name="x" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{padding:14, display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(280px, 1fr))", gap:12}}>
              {filtered.map(t => (
                <div key={t.id} className="card" style={{padding:14, cursor:"pointer", position:"relative"}} onClick={() => onOpenTest(t.id)}>
                  <div style={{display:"flex", alignItems:"center", gap:8, marginBottom:8}}>
                    <span className="mono dim" style={{fontSize:10.5}}>{t.id}</span>
                    <div style={{marginLeft:"auto"}} onClick={(e) => e.stopPropagation()}>
                      <StatusSelect s={t.status} testId={t.id} onChanged={refresh} />
                    </div>
                    {window.can && window.can(currentUser, "delete") && (
                      <button className="btn ghost icon sm" style={{opacity:0.5}} onClick={(e) => handleDeleteRow(t, e)}>
                        <Icon name="x" />
                      </button>
                    )}
                  </div>
                  <div style={{fontSize:13, fontWeight:500, lineHeight:1.4, marginBottom:10}}>{t.title}</div>
                  <div style={{display:"flex", alignItems:"center", gap:6, fontSize:11}}>
                    {t.auto ? <span className="tag" style={{color:"var(--info)"}}>auto</span> : <span className="tag">manual</span>}
                    <span className={"tag priority-" + (t.priority === "high" ? "high" : t.priority === "med" ? "med" : "low")}>{t.priority}</span>
                    <span className="dim mono" style={{marginLeft:"auto", fontSize:10.5}}>{t.lastRun}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {testsLoading && tests === null ? (
            <div className="empty">Loading…</div>
          ) : filtered.length === 0 ? (
            <div className="empty">No tests match the current filters.</div>
          ) : null}
        </div>
      </div>

      {/* New test modal */}
      {showNewTest && (
        <NewTestModal
          folders={D.folders.flatMap(f => [f, ...(f.children || [])])}
          defaultFolderId={activeFolder}
          onClose={() => setShowNewTest(false)}
          onCreate={refresh}
        />
      )}

      {/* Delete single confirm */}
      {deleteTarget && (
        <ConfirmDialog
          title={`Delete ${deleteTarget.id}?`}
          body={`"${deleteTarget.title}" will be permanently deleted.`}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {/* Bulk delete confirm */}
      {bulkDeleteConfirm && (
        <ConfirmDialog
          title={`Delete ${selected.size} test${selected.size > 1 ? "s" : ""}?`}
          body="Selected tests will be permanently deleted."
          onConfirm={handleBulkDelete}
          onCancel={() => setBulkDeleteConfirm(false)}
        />
      )}
    </div>
  );
}

function NewTestModal({ folders, defaultFolderId, onClose, onCreate }) {
  const [form, setForm] = useState({
    id: "", title: "", folder_id: defaultFolderId || "", type: "manual", priority: "med", owner: "", tags: ""
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  const setF = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.id.trim() || !form.title.trim()) { setErr("ID and title are required."); return; }
    setSaving(true);
    setErr(null);
    try {
      const payload = {
        id: form.id.trim(),
        title: form.title.trim(),
        folder_id: form.folder_id || null,
        type: form.type,
        priority: form.priority,
        owner: form.owner.trim() || null,
        tags: form.tags.split(",").map(t => t.trim()).filter(Boolean),
        auto: form.type === "automated",
        status: "pending",
      };
      const res = await fetch("/api/tests", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("th_token")}` },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Create failed");
      }
      onCreate();
      onClose();
    } catch (e) {
      setErr(e.message);
      setSaving(false);
    }
  };

  return (
    <div style={{position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center"}} onClick={onClose}>
      <div style={{background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:8, padding:24, width:480, maxHeight:"80vh", overflowY:"auto"}} onClick={e => e.stopPropagation()}>
        <div style={{display:"flex", alignItems:"center", marginBottom:20}}>
          <h2 style={{fontSize:15, fontWeight:600, margin:0}}>New test case</h2>
          <button className="btn ghost icon sm" style={{marginLeft:"auto"}} onClick={onClose}><Icon name="x" /></button>
        </div>

        <div style={{display:"flex", flexDirection:"column", gap:14}}>
          <FormField label="ID *" hint="e.g. TC-2400">
            <input className="input" value={form.id} onChange={e => setF("id", e.target.value)} placeholder="TC-2400" />
          </FormField>
          <FormField label="Title *">
            <input className="input" value={form.title} onChange={e => setF("title", e.target.value)} placeholder="Describe what this test verifies" />
          </FormField>
          <FormField label="Folder">
            <select className="input" value={form.folder_id} onChange={e => setF("folder_id", e.target.value)}>
              <option value="">— none —</option>
              {folders.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </FormField>
          <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:12}}>
            <FormField label="Type">
              <select className="input" value={form.type} onChange={e => setF("type", e.target.value)}>
                <option value="manual">Manual</option>
                <option value="automated">Automated</option>
              </select>
            </FormField>
            <FormField label="Priority">
              <select className="input" value={form.priority} onChange={e => setF("priority", e.target.value)}>
                <option value="high">High</option>
                <option value="med">Medium</option>
                <option value="low">Low</option>
              </select>
            </FormField>
          </div>
          <FormField label="Owner" hint="initials or username">
            <input className="input" value={form.owner} onChange={e => setF("owner", e.target.value)} placeholder="e.g. QA" />
          </FormField>
          <FormField label="Tags" hint="comma-separated">
            <input className="input" value={form.tags} onChange={e => setF("tags", e.target.value)} placeholder="smoke, payment, p0" />
          </FormField>
        </div>

        {err && <div style={{color:"var(--fail)", fontSize:12, marginTop:12}}>{err}</div>}

        <div style={{display:"flex", gap:8, marginTop:20, justifyContent:"flex-end"}}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn accent" onClick={submit} disabled={saving || !form.id.trim() || !form.title.trim()}>
            {saving ? "Creating…" : "Create test"}
          </button>
        </div>
      </div>
    </div>
  );
}

function FormField({ label, hint, children }) {
  return (
    <div>
      <div style={{fontSize:11, fontWeight:500, color:"var(--text-dim)", marginBottom:5, display:"flex", gap:6, alignItems:"baseline"}}>
        {label}
        {hint && <span style={{fontWeight:400, color:"var(--text-muted)"}}>{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function ConfirmDialog({ title, body, onConfirm, onCancel }) {
  return (
    <div style={{position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center"}} onClick={onCancel}>
      <div style={{background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:8, padding:24, width:400}} onClick={e => e.stopPropagation()}>
        <h2 style={{fontSize:15, fontWeight:600, margin:"0 0 10px"}}>{title}</h2>
        <p style={{fontSize:12.5, color:"var(--text-muted)", margin:"0 0 20px", lineHeight:1.5}}>{body}</p>
        <div style={{display:"flex", gap:8, justifyContent:"flex-end"}}>
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button className="btn" style={{background:"var(--fail)", color:"white", border:"none"}} onClick={onConfirm}>Delete</button>
        </div>
      </div>
    </div>
  );
}

window.Library = Library;
