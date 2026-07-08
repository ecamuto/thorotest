// Pipelines, Insights, Integrations, Landing — remaining views

function Pipelines() {
  const { data: D, loading, error } = useInitialData();

  if (loading) return (
    <div className="page fade-in">
      <div className="empty">Loading…</div>
    </div>
  );

  if (!D) return (
    <div className="page fade-in">
      <div className="empty">Error loading data{error ? `: ${error}` : ""}.</div>
    </div>
  );

  return (
    <div className="page fade-in">
      <div className="page-h">
        <div>
          <h1 className="page-title">CI pipelines</h1>
          <div className="page-sub">Every CI run that touched your tests, alongside the manual results. Same timeline, one source of truth.</div>
        </div>
      </div>

      <div className="card" style={{marginBottom:14}}>
        <div className="card-h">
          <div>
            <div className="card-title">Recent runs</div>
            <div className="card-sub">CI pipeline results imported into ThoroTest</div>
          </div>
        </div>
        {D.pipelines.length === 0 ? (
          <div className="empty" style={{padding:"48px 18px", textAlign:"center"}}>
            <div style={{fontSize:13, marginBottom:6}}>No pipeline runs yet.</div>
            <div className="mono dim" style={{fontSize:11}}>
              Connect a CI provider (Configure → integrations) or push JUnit results to see runs here.
            </div>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th style={{width:36}}></th>
                <th>Workflow</th>
                <th style={{width:100}}>Status</th>
                <th style={{width:100}}>Duration</th>
                <th style={{width:120}}>Commit</th>
                <th style={{width:100}}>Branch</th>
                <th style={{width:120}}>Author</th>
                <th style={{width:100}}>When</th>
              </tr>
            </thead>
            <tbody>
              {D.pipelines.map(p => (
                <tr key={p.id} style={{cursor:"pointer"}}>
                  <td>
                    <span style={{display:"inline-flex", width:18, height:18}}>
                      {p.platform === "github" ? I.github : p.platform === "gitlab" ? I.gitlab : I.jenkins}
                    </span>
                  </td>
                  <td>{p.name}</td>
                  <td><StatusBadge s={p.status} /></td>
                  <td className="mono dim">{p.duration}</td>
                  <td className="mono" style={{color:"var(--accent)"}}>{p.commit}</td>
                  <td className="mono dim">{p.branch}</td>
                  <td className="mono dim">{p.author}</td>
                  <td className="mono dim">{p.when}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Insights() {
  const [ins, setIns] = React.useState(null);
  const [insLoading, setInsLoading] = React.useState(true);

  React.useEffect(() => {
    fetch('/api/insights', { headers: window.authHeaders() })
      .then(r => r.json())
      .then(data => { setIns(data); setInsLoading(false); })
      .catch(() => setInsLoading(false));
  }, []);

  const totalTests = ins ? String(ins.total_tests) : "—";
  const automationRate = ins ? `${ins.automation_rate}%` : "—";
  const folderCoverage = ins ? ins.folder_coverage : null;

  return (
    <div className="page fade-in">
      <div className="page-h">
        <div>
          <h1 className="page-title">Insights</h1>
          <div className="page-sub">Test health, coverage, and where your team is losing time.</div>
        </div>
      </div>

      <div className="grid grid-4" style={{marginBottom:14}}>
        <Metric label="Test cases" value={insLoading ? "…" : totalTests} />
        <Metric label="Automation rate" value={insLoading ? "…" : automationRate} />
        <Metric label="Pass rate" value={insLoading ? "…" : (ins && ins.pass_rate != null ? `${ins.pass_rate}%` : "—")} />
        <Metric label="Open defects" value={insLoading ? "…" : (ins && ins.open_defects != null ? String(ins.open_defects) : "—")} />
      </div>

      <div className="grid grid-2" style={{marginBottom:14}}>
        <div className="card">
          <div className="card-h"><div className="card-title">Coverage by area</div></div>
          <div className="card-b" style={{display:"flex", flexDirection:"column", gap:10}}>
            {folderCoverage && folderCoverage.length > 0 ? (
              folderCoverage.map((f, i) => (
                <CoverageRow key={i} label={f.name} value={f.value} mapped={f.mapped} warn={f.value < 60} />
              ))
            ) : (
              <div className="mono dim" style={{fontSize:11.5, padding:"8px 0"}}>
                {insLoading ? "Loading…" : "No coverage data — link requirements to tests to see coverage by area."}
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-h"><div className="card-title">Top 5 flaky tests</div><div className="card-sub">{">"} 10 runs in 30d</div></div>
          <table className="table">
            <tbody>
              {ins && ins.top_flaky && ins.top_flaky.length > 0 ? (
                ins.top_flaky.map(r => (
                  <tr key={r.id}>
                    <td className="mono" style={{width:80}}>{r.id}</td>
                    <td style={{fontSize:12}}>{r.title}</td>
                    <td className="mono" style={{color:"var(--fail)", width:50, textAlign:"right"}}>{r.fail_rate}%</td>
                    <td className="mono dim" style={{width:60, textAlign:"right"}}>{r.total_runs} runs</td>
                  </tr>
                ))
              ) : insLoading ? (
                <tr><td colSpan={4} style={{textAlign:"center", color:"var(--text-dim)", fontSize:12}}>Loading…</td></tr>
              ) : (
                <tr><td colSpan={4} style={{textAlign:"center", color:"var(--text-dim)", fontSize:12}}>No flaky tests found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-h"><div className="card-title">Manual vs automated</div><div className="card-sub">share of the test library</div></div>
          <div className="card-b">
            <div className="bar" style={{height:10}}>
              <span className="seg-pass" style={{width:`${ins ? ins.automation_rate : 0}%`}} />
              <span style={{background:"var(--info)", width:`${100 - (ins ? ins.automation_rate : 0)}%`}} />
            </div>
            <div style={{display:"flex", justifyContent:"space-between", marginTop:8, fontSize:11}}>
              <span className="mono"><span style={{color:"var(--accent)"}}>●</span> automated {ins ? ins.automation_rate : 0}%</span>
              <span className="mono"><span style={{color:"var(--info)"}}>●</span> manual {100 - (ins ? ins.automation_rate : 0)}%</span>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-h"><div className="card-title">Open defects by severity</div></div>
          <div className="card-b" style={{display:"flex", flexDirection:"column", gap:10}}>
            {insLoading ? (
              <div className="mono dim" style={{fontSize:11.5}}>Loading…</div>
            ) : ins && ins.open_defects > 0 ? (
              <>
                <CoverageRow label="Critical" value={Math.round((ins.open_critical || 0) / ins.open_defects * 100)} mapped={`${ins.open_critical || 0}/${ins.open_defects}`} warn />
                <CoverageRow label="High" value={Math.round((ins.open_high || 0) / ins.open_defects * 100)} mapped={`${ins.open_high || 0}/${ins.open_defects}`} warn />
              </>
            ) : (
              <div className="mono dim" style={{fontSize:11.5, padding:"8px 0"}}>No open defects.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function CoverageRow({label, value, mapped, warn}) {
  return (
    <div>
      <div style={{display:"flex", justifyContent:"space-between", marginBottom:4, fontSize:12}}>
        <span>{label}</span>
        <span className="mono dim" style={{fontSize:11}}>{mapped} <b style={{color: warn ? "var(--warn)" : "var(--text)"}}>{value}%</b></span>
      </div>
      <div className="bar">
        <span style={{width:`${value}%`, background: warn ? "var(--warn)" : "var(--accent)"}} />
      </div>
    </div>
  );
}

window.Pipelines = Pipelines;
window.Insights = Insights;
