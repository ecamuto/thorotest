// Custom fields — shared pieces for admin-defined extra fields on
// tests / defects / requirements.
//
//   useCustomFieldDefs(entityType)                    → [defs, loading]
//   <CustomFieldsInputs defs values onChange />       → form inputs (create/edit modals)
//   <CustomFieldsDisplay defs values />               → read-only rows (detail views)
//   <CustomFieldsAdmin />                             → admin manager (Admin page tab)
//
// Definitions come from GET /api/custom-fields; values ride on each record's
// `custom_fields` object and are validated server-side.

function useCustomFieldDefs(entityType) {
  const [defs, setDefs] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    TH_API.getCustomFields(entityType)
      .then(d => { if (alive) { setDefs(d); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [entityType]);
  return [defs, loading];
}

// One labelled input per definition. `values` is the record's custom_fields
// object; onChange receives the updated object.
function CustomFieldsInputs({ defs, values, onChange }) {
  if (!defs || defs.length === 0) return null;
  const set = (key, v) => onChange({ ...(values || {}), [key]: v });
  const L = { fontSize:11, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:4 };
  return (
    <>
      {defs.map(d => {
        const v = (values || {})[d.key];
        return (
          <div key={d.key}>
            <label style={L}>{d.label}{d.required ? " *" : ""}</label>
            {d.field_type === "select" ? (
              <select className="input" style={{width:"100%"}} value={v ?? ""} onChange={e => set(d.key, e.target.value || null)}>
                <option value="">— none —</option>
                {(d.options || []).map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : d.field_type === "checkbox" ? (
              <label style={{display:"flex", alignItems:"center", gap:8, cursor:"pointer", fontSize:12.5}}>
                <input type="checkbox" checked={!!v} onChange={e => set(d.key, e.target.checked)} style={{accentColor:"var(--accent)"}} />
                <span>{d.label}</span>
              </label>
            ) : d.field_type === "number" ? (
              <input className="input" type="number" style={{width:"100%", boxSizing:"border-box"}} value={v ?? ""}
                     onChange={e => set(d.key, e.target.value === "" ? null : Number(e.target.value))} />
            ) : d.field_type === "date" ? (
              <input className="input" type="date" style={{width:"100%", boxSizing:"border-box"}} value={v ?? ""}
                     onChange={e => set(d.key, e.target.value || null)} />
            ) : (
              <input className="input" style={{width:"100%", boxSizing:"border-box"}} value={v ?? ""}
                     onChange={e => set(d.key, e.target.value || null)} />
            )}
          </div>
        );
      })}
    </>
  );
}

function formatCustomFieldValue(def, v) {
  if (v === undefined || v === null || v === "") return null;
  if (def.field_type === "checkbox") return v ? "yes" : "no";
  return String(v);
}

// Read-only label/value rows for detail panels. Renders nothing when the
// record has no values for the given defs.
function CustomFieldsDisplay({ defs, values }) {
  const rows = (defs || [])
    .map(d => ({ d, text: formatCustomFieldValue(d, (values || {})[d.key]) }))
    .filter(r => r.text !== null);
  if (rows.length === 0) return null;
  return (
    <>
      {rows.map(({ d, text }) => (
        <div key={d.key} style={{display:"flex", alignItems:"center", gap:10}}>
          <div style={{color:"var(--text-dim)", fontSize:11, textTransform:"uppercase", letterSpacing:"0.06em", width:120, flexShrink:0}}>{d.label}</div>
          <div style={{flex:1, minWidth:0}}>{text}</div>
        </div>
      ))}
    </>
  );
}

// ---- Admin manager (Admin page → Custom fields tab) ------------------------

const CF_ENTITY_TYPES = [
  { id: "test", label: "Tests" },
  { id: "defect", label: "Defects" },
  { id: "requirement", label: "Requirements" },
];
const CF_FIELD_TYPES = ["text", "number", "select", "date", "checkbox"];

function CustomFieldsAdmin() {
  const [entityType, setEntityType] = useState("test");
  const [defs, setDefs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [editing, setEditing] = useState(null);   // def object, or {} for new

  const load = () => {
    setLoading(true);
    TH_API.getCustomFields(entityType)
      .then(d => { setDefs(d); setErr(null); })
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  };
  useEffect(load, [entityType]);

  const handleDelete = async (d) => {
    if (!window.confirm(`Delete field "${d.label}"? Existing values stay stored but are no longer shown.`)) return;
    try {
      await TH_API.deleteCustomField(d.id);
      setDefs(prev => prev.filter(x => x.id !== d.id));
    } catch (e) { alert(e.message); }
  };

  return (
    <div>
      <div style={{display:"flex", alignItems:"center", gap:8, marginBottom:16}}>
        <h2 style={{margin:0, fontSize:18, fontWeight:600}}>Custom fields</h2>
        <div className="spacer" style={{flex:1}} />
        <select className="input" style={{width:150}} value={entityType} onChange={e => setEntityType(e.target.value)}>
          {CF_ENTITY_TYPES.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select>
        <button className="btn accent sm" onClick={() => setEditing({})}><Icon name="plus" /> New field</button>
      </div>
      <p style={{fontSize:12.5, color:"var(--text-muted)", margin:"0 0 16px"}}>
        Extra fields shown on every {entityType} form. Values are stored per record and validated by the server.
      </p>

      {err && <div style={{color:"var(--fail)", fontSize:12, marginBottom:10}}>{err}</div>}
      {loading ? (
        <div className="mono dim" style={{padding:24}}>Loading…</div>
      ) : defs.length === 0 ? (
        <div className="mono dim" style={{padding:24}}>No custom fields for {entityType}s yet.</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Label</th>
              <th style={{width:140}}>Key</th>
              <th style={{width:100}}>Type</th>
              <th>Options</th>
              <th style={{width:80}}>Required</th>
              <th style={{width:64}}></th>
            </tr>
          </thead>
          <tbody>
            {defs.map(d => (
              <tr key={d.id}>
                <td style={{fontWeight:500}}>{d.label}</td>
                <td className="mono" style={{fontSize:11.5}}>{d.key}</td>
                <td><span className="tag">{d.field_type}</span></td>
                <td style={{fontSize:12}}>{(d.options || []).join(", ") || <span className="dim">—</span>}</td>
                <td>{d.required ? "yes" : <span className="dim">no</span>}</td>
                <td>
                  <div style={{display:"flex", gap:2}}>
                    <button className="btn ghost sm" style={{padding:"2px 6px"}} title="Edit" onClick={() => setEditing(d)}><Icon name="settings" /></button>
                    <button className="btn ghost sm" style={{color:"var(--fail)", padding:"2px 6px"}} title="Delete" onClick={() => handleDelete(d)}><Icon name="x" /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {editing && (
        <CustomFieldDefModal
          def={editing.id ? editing : null}
          entityType={entityType}
          onClose={() => setEditing(null)}
          onSaved={(d, isNew) => {
            setDefs(prev => isNew ? [...prev, d] : prev.map(x => x.id === d.id ? d : x));
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function CustomFieldDefModal({ def, entityType, onClose, onSaved }) {
  const isNew = !def;
  const [form, setForm] = useState({
    label: def?.label || "",
    field_type: def?.field_type || "text",
    options: (def?.options || []).join(", "),
    required: def?.required || false,
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  const save = async () => {
    if (!form.label.trim()) return;
    setSaving(true); setErr(null);
    const options = form.field_type === "select"
      ? form.options.split(",").map(o => o.trim()).filter(Boolean)
      : [];
    try {
      const payload = { label: form.label.trim(), field_type: form.field_type, options, required: form.required };
      const d = isNew
        ? await TH_API.createCustomField({ ...payload, entity_type: entityType })
        : await TH_API.updateCustomField(def.id, payload);
      onSaved(d, isNew);
    } catch (e) { setErr(e.message); }
    setSaving(false);
  };

  const L = { fontSize:11, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:4 };

  return (
    <div style={{position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center"}} onClick={onClose}>
      <div style={{background:"var(--bg-2)", border:"1px solid var(--border)", borderRadius:8, padding:24, width:440}} onClick={e => e.stopPropagation()}>
        <h2 style={{fontSize:15, fontWeight:600, margin:"0 0 16px"}}>
          {isNew ? `New ${entityType} field` : `Edit "${def.label}"`}
        </h2>
        <div style={{display:"flex", flexDirection:"column", gap:10}}>
          <div>
            <label style={L}>Label</label>
            <input className="input" style={{width:"100%", boxSizing:"border-box"}} value={form.label}
                   placeholder="e.g. Browser" autoFocus
                   onChange={e => setForm(f => ({...f, label: e.target.value}))} />
            {isNew && <div style={{fontSize:11, color:"var(--text-dim)", marginTop:3}}>Key is derived automatically (lowercase, underscores).</div>}
          </div>
          <div>
            <label style={L}>Type</label>
            <select className="input" style={{width:"100%"}} value={form.field_type}
                    onChange={e => setForm(f => ({...f, field_type: e.target.value}))}>
              {CF_FIELD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          {form.field_type === "select" && (
            <div>
              <label style={L}>Options (comma-separated)</label>
              <input className="input" style={{width:"100%", boxSizing:"border-box"}} value={form.options}
                     placeholder="chrome, firefox, safari"
                     onChange={e => setForm(f => ({...f, options: e.target.value}))} />
            </div>
          )}
          <label style={{display:"flex", alignItems:"center", gap:8, cursor:"pointer", fontSize:12.5}}>
            <input type="checkbox" checked={form.required} style={{accentColor:"var(--accent)"}}
                   onChange={e => setForm(f => ({...f, required: e.target.checked}))} />
            <span>Required on create</span>
          </label>
        </div>
        {err && <div style={{color:"var(--fail)", fontSize:12, marginTop:10}}>{err}</div>}
        <div style={{display:"flex", gap:8, justifyContent:"flex-end", marginTop:20}}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn accent" onClick={save} disabled={saving || !form.label.trim()}>
            {saving ? "Saving…" : (isNew ? "Create" : "Save")}
          </button>
        </div>
      </div>
    </div>
  );
}

window.useCustomFieldDefs = useCustomFieldDefs;
window.CustomFieldsInputs = CustomFieldsInputs;
window.CustomFieldsDisplay = CustomFieldsDisplay;
window.CustomFieldsAdmin = CustomFieldsAdmin;
