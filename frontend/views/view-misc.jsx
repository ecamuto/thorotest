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
        <div className="actions">
          <button className="btn"><Icon name="plus" /> Connect provider</button>
        </div>
      </div>

      <div className="grid grid-4" style={{marginBottom:14}}>
        <ConnCard icon="github" name="GitHub Actions" status="connected" repos="3 repos · 12 workflows" color="oklch(0.96 0 0)" />
        <ConnCard icon="gitlab" name="GitLab CI" status="connected" repos="1 project · 4 pipelines" color="oklch(0.65 0.15 35)" />
        <ConnCard icon="jenkins" name="Jenkins" status="connected" repos="1 server · 6 jobs" color="oklch(0.65 0.15 240)" />
        <ConnCard icon="plug" name="Add provider" status="empty" repos="CircleCI, Buildkite, Drone..." />
      </div>

      <div className="card" style={{marginBottom:14}}>
        <div className="card-h">
          <div>
            <div className="card-title">Recent runs</div>
            <div className="card-sub">across all providers · last 24h</div>
          </div>
          <div className="spacer" />
          <div className="chip active">All</div>
          <div className="chip">Failing only</div>
          <div className="chip">Main branch</div>
        </div>
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
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-h"><div className="card-title">Failing test → CI workflow</div><div className="card-sub">flaky correlation</div></div>
          <div className="card-b">
            {[
              { test: "TC-2212 — Cart persists (guest)", wf: "e2e.yml", rate: "32%" },
              { test: "TC-1045 — Password reset 60s SLA", wf: "nightly.yml", rate: "18%" },
              { test: "TC-2302 — 3DS challenge intercepts", wf: "e2e.yml", rate: "12%" },
            ].map((r, i) => (
              <div key={i} style={{display:"grid", gridTemplateColumns:"1fr 130px 60px", gap:10, alignItems:"center", padding:"10px 0", borderBottom: i < 2 ? "1px solid var(--border)" : "none", fontSize:12}}>
                <div>
                  <div>{r.test}</div>
                  <div className="mono dim" style={{fontSize:10.5}}>{r.wf}</div>
                </div>
                <div className="bar" style={{height:4}}>
                  <span className="seg-fail" style={{width:r.rate}} />
                  <span style={{background:"var(--surface-2)", width:`calc(100% - ${r.rate})`}} />
                </div>
                <div className="mono" style={{color:"var(--fail)", textAlign:"right"}}>{r.rate}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-h"><div className="card-title">Pipeline duration trend</div><div className="card-sub">14 days · all workflows</div></div>
          <div className="card-b">
            <div style={{height:120, display:"flex", alignItems:"flex-end", gap:3}}>
              {[42,46,38,52,44,40,48,55,46,42,38,45,44,41].map((v, i) => (
                <div key={i} style={{flex:1, height:`${v*2}%`, background:"var(--info-soft)", borderTop:"2px solid var(--info)", borderRadius:1}} />
              ))}
            </div>
            <div className="mono dim" style={{fontSize:10.5, marginTop:8, display:"flex", justifyContent:"space-between"}}>
              <span>14d ago</span>
              <span>avg 44m 12s</span>
              <span>today</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ConnCard({icon, name, status, repos, color}) {
  if (status === "empty") {
    return (
      <div className="card" style={{padding:14, display:"flex", alignItems:"center", gap:10, cursor:"pointer", borderStyle:"dashed"}}>
        <div style={{width:32, height:32, background:"var(--surface-2)", borderRadius:"var(--radius)", display:"grid", placeItems:"center", color:"var(--text-dim)"}}>
          <Icon name="plus" />
        </div>
        <div style={{minWidth:0}}>
          <div style={{fontWeight:500, fontSize:12.5}}>{name}</div>
          <div className="mono dim" style={{fontSize:10.5}}>{repos}</div>
        </div>
      </div>
    );
  }
  return (
    <div className="card" style={{padding:14, display:"flex", alignItems:"center", gap:10}}>
      <div style={{width:32, height:32, background:"var(--surface-2)", borderRadius:"var(--radius)", display:"grid", placeItems:"center", color: color || "var(--text)"}}>
        <span style={{display:"inline-flex", width:18, height:18}}>{I[icon]}</span>
      </div>
      <div style={{minWidth:0, flex:1}}>
        <div style={{fontWeight:500, fontSize:12.5, display:"flex", alignItems:"center", gap:6}}>
          {name} <span className="status pass" style={{padding:"0 5px", fontSize:9}}>ON</span>
        </div>
        <div className="mono dim" style={{fontSize:10.5}}>{repos}</div>
      </div>
    </div>
  );
}

function Insights() {
  const [ins, setIns] = React.useState(null);
  const [insLoading, setInsLoading] = React.useState(true);

  React.useEffect(() => {
    fetch('/api/insights')
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
        <div className="actions">
          <div className="chip">Last 30 days <Icon name="chevD" /></div>
          <button className="btn">Export</button>
        </div>
      </div>

      <div className="grid grid-4" style={{marginBottom:14}}>
        <Metric label="Test cases" value={insLoading ? "…" : totalTests} delta="+12 vs prev 30d" up />
        <Metric label="Automation rate" value={insLoading ? "…" : automationRate} delta="+5pp vs prev 30d" up />
        <Metric label="Flakiness" value="3.1%" delta="−0.4pp" up />
        <Metric label="Mean time to fix" value="14h" delta="−3h" up />
      </div>

      <div className="grid grid-2" style={{marginBottom:14}}>
        <div className="card">
          <div className="card-h"><div className="card-title">Coverage by area</div></div>
          <div className="card-b" style={{display:"flex", flexDirection:"column", gap:10}}>
            {folderCoverage ? (
              folderCoverage.map((f, i) => (
                <CoverageRow key={i} label={f.name} value={f.value} mapped={f.mapped} warn={f.value < 60} />
              ))
            ) : (
              <>
                <CoverageRow label="Authentication" value={91} mapped="24/24" />
                <CoverageRow label="Checkout" value={78} mapped="41/52" />
                <CoverageRow label="Billing" value={52} mapped="18/35" warn />
                <CoverageRow label="Admin panel" value={71} mapped="33/47" />
                <CoverageRow label="Public API" value={84} mapped="56/67" />
                <CoverageRow label="Mobile" value={43} mapped="29/68" warn />
              </>
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
          <div className="card-h"><div className="card-title">Manual vs automated execution time</div></div>
          <div className="card-b">
            <div style={{display:"flex", gap:14}}>
              <div style={{flex:1}}>
                <div className="mono dim" style={{fontSize:10.5, textTransform:"uppercase", letterSpacing:"0.06em"}}>Manual</div>
                <div className="metric-value" style={{fontSize:22, marginTop:4}}>147h</div>
                <div className="metric-delta">across 4 testers</div>
              </div>
              <div style={{flex:1}}>
                <div className="mono dim" style={{fontSize:10.5, textTransform:"uppercase", letterSpacing:"0.06em"}}>Automated</div>
                <div className="metric-value" style={{fontSize:22, marginTop:4, color:"var(--accent)"}}>312h</div>
                <div className="metric-delta">CPU time on CI</div>
              </div>
            </div>
            <div className="bar" style={{height:10, marginTop:14}}>
              <span className="seg-pass" style={{width:`${ins ? ins.automation_rate : 68}%`}} />
              <span style={{background:"var(--info)", width:`${100 - (ins ? ins.automation_rate : 68)}%`}} />
            </div>
            <div style={{display:"flex", justifyContent:"space-between", marginTop:6, fontSize:11}}>
              <span className="mono"><span style={{color:"var(--accent)"}}>●</span> automated {ins ? ins.automation_rate : 68}%</span>
              <span className="mono"><span style={{color:"var(--info)"}}>●</span> manual {100 - (ins ? ins.automation_rate : 68)}%</span>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-h"><div className="card-title">Activity heatmap</div><div className="card-sub">runs per hour · last 7 days</div></div>
          <div className="card-b">
            <Heatmap />
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

function Heatmap() {
  const days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
  return (
    <div style={{display:"grid", gridTemplateColumns:"30px repeat(24, 1fr)", gap:2}}>
      <div></div>
      {Array.from({length: 24}).map((_, i) => i % 4 === 0 ? <div key={i} className="mono dim" style={{fontSize:9, textAlign:"center", gridColumn:`span 4`}}>{i.toString().padStart(2,"0")}</div> : null).filter(Boolean)}
      {days.map((d, di) => (
        <React.Fragment key={d}>
          <div className="mono dim" style={{fontSize:10, paddingTop:2}}>{d}</div>
          {Array.from({length:24}).map((_, h) => {
            const v = Math.max(0, Math.min(1, (Math.sin(h/3 + di) + 1)/2 * (h > 8 && h < 20 ? 1 : 0.3)));
            const op = di === 5 || di === 6 ? v * 0.3 : v;
            return <div key={h} style={{aspectRatio:"1", background:`oklch(from var(--accent) l c h / ${op})`, borderRadius:1}} />;
          })}
        </React.Fragment>
      ))}
    </div>
  );
}

window.Pipelines = Pipelines;
window.Insights = Insights;
