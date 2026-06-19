// Test Hub — public landing page (standalone, no app dependency)

// Icons
const I = {
  github: <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.53 2.34 1.09 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.26-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.02A9.5 9.5 0 0 1 12 6.8a9.5 9.5 0 0 1 2.5.34c1.9-1.29 2.74-1.02 2.74-1.02.55 1.38.2 2.39.1 2.65.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.94.36.31.68.92.68 1.85V21c0 .26.18.58.69.48A10 10 0 0 0 12 2z"/></svg>,
  dots: <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/></svg>,
};

function Icon({name, className}) {
  return <span className={"icon " + (className || "")} style={{display:"inline-flex", width:14, height:14}}>{I[name]}</span>;
}

function StatusBadge({s}) {
  const map = {pass:"Pass", fail:"Fail", skip:"Skip", warn:"Warn", running:"Running"};
  return <span className={`badge badge-${s}`}>{map[s] || s}</span>;
}

function Pillar({num, title, body}) {
  return (
    <div style={{borderLeft:"1px solid var(--border)", padding:"4px 0 4px 18px"}}>
      <div className="mono dim" style={{fontSize:10.5, marginBottom:6}}>{num}</div>
      <div style={{fontSize:15, fontWeight:600, letterSpacing:"-0.01em", marginBottom:8, lineHeight:1.25}}>{title}</div>
      <div style={{fontSize:12.5, color:"var(--text-muted)", lineHeight:1.55}}>{body}</div>
    </div>
  );
}

function Step2({n, title, body, code}) {
  return (
    <div style={{display:"flex", gap:14}}>
      <div className="mono" style={{fontSize:12, color:"var(--accent)", fontWeight:500, flexShrink:0, paddingTop:1}}>0{n}</div>
      <div>
        <div style={{fontSize:14, fontWeight:500, marginBottom:4}}>{title}</div>
        <div style={{fontSize:12.5, color:"var(--text-muted)", marginBottom:8, lineHeight:1.5}}>{body}</div>
        <code style={{display:"inline-block", fontFamily:"var(--font-mono)", fontSize:11, background:"var(--surface)", border:"1px solid var(--border)", padding:"4px 9px", borderRadius:"var(--radius)", color:"var(--accent)"}}>$ {code}</code>
      </div>
    </div>
  );
}

function Stat({n, label}) {
  return (
    <div>
      <div className="mono" style={{fontSize:22, fontWeight:500, letterSpacing:"-0.02em"}}>{n}</div>
      <div className="mono dim" style={{fontSize:10.5, textTransform:"uppercase", letterSpacing:"0.06em"}}>{label}</div>
    </div>
  );
}

function Landing() {
  return (
    <div style={{overflowY:"auto", height:"100%", background:"var(--bg)", position:"relative"}}>
      {/* Top nav */}
      <div style={{
        position:"sticky", top:0, zIndex:10,
        padding:"14px 32px",
        background:"oklch(from var(--bg) l c h / 0.85)",
        backdropFilter:"blur(8px)",
        borderBottom:"1px solid var(--border)",
        display:"flex", alignItems:"center", gap:24
      }}>
        <div style={{display:"flex", alignItems:"center", gap:9}}>
          <div className="brand-mark">T</div>
          <span className="brand-name">Test Hub</span>
        </div>
        <div style={{display:"flex", gap:18, fontSize:12.5, color:"var(--text-muted)"}}>
          <a>Docs</a>
          <a>Quickstart</a>
          <a>API</a>
          <a>Examples</a>
          <a>Changelog</a>
        </div>
        <div className="spacer" />
        <div style={{display:"flex", alignItems:"center", gap:8}}>
          <a className="btn ghost sm" style={{display:"flex", alignItems:"center", gap:6}}>
            <Icon name="github" /> testhub-dev/testhub <span className="mono dim" style={{marginLeft:4}}>★ 4,128</span>
          </a>
          <button className="btn accent sm">Self-host</button>
        </div>
      </div>

      <div className="landing">
        {/* Hero */}
        <div className="fade-in">
          <div className="eyebrow"><span className="dot" /> v1.4 · Apache 2.0 · self-hostable</div>
          <h1>
            Tests as code,<br/>
            <span className="accent">visualized for humans.</span>
          </h1>
          <div className="lede">
            Test Hub is an open-source test management workspace. Your test cases live as YAML in your repo. The UI is a thin layer that makes them runnable, traceable, and reviewable — for QAs, devs, and PMs in the same view.
          </div>

          <div style={{display:"flex", gap:8, marginTop:24}}>
            <button className="btn accent" style={{padding:"8px 14px"}}>Self-host in 60s</button>
            <button className="btn" style={{padding:"8px 14px"}}><Icon name="github" /> Star on GitHub</button>
            <button className="btn ghost" style={{padding:"8px 14px"}}>Read the docs →</button>
          </div>

          <div style={{display:"flex", alignItems:"center", gap:8, marginTop:18, fontSize:11.5, color:"var(--text-dim)"}}>
            <code className="mono" style={{background:"var(--surface)", border:"1px solid var(--border)", padding:"5px 10px", borderRadius:"var(--radius)"}}>
              $ pnpm dlx testhub init
            </code>
            <span>or run with Docker · no telemetry · MIT-licensed</span>
          </div>
        </div>

        {/* Visual — hero terminal/yaml split */}
        <div style={{marginTop:48, marginBottom:48, border:"1px solid var(--border)", borderRadius:"var(--radius-lg)", background:"var(--surface)", boxShadow:"var(--shadow-2)", overflow:"hidden"}} className="fade-in">
          <div style={{padding:"10px 14px", borderBottom:"1px solid var(--border)", display:"flex", alignItems:"center", gap:8, background:"var(--bg-2)"}}>
            <span style={{width:10, height:10, borderRadius:"50%", background:"var(--surface-3)"}} />
            <span style={{width:10, height:10, borderRadius:"50%", background:"var(--surface-3)"}} />
            <span style={{width:10, height:10, borderRadius:"50%", background:"var(--surface-3)"}} />
            <span className="mono dim" style={{fontSize:11, marginLeft:8}}>~/acme-web</span>
          </div>
          <div style={{display:"grid", gridTemplateColumns:"1fr 1fr"}}>
            <div style={{padding:18, borderRight:"1px solid var(--border)"}}>
              <div className="mono dim" style={{fontSize:10.5, textTransform:"uppercase", letterSpacing:"0.08em", marginBottom:10}}>tests/checkout/payment/stripe-charge.yml</div>
              <pre className="code" style={{border:"none", background:"transparent", padding:0, fontSize:11}}>
{`# `}<span className="c">Test Hub — Tests as Code</span>{`
`}<span className="k">id</span>{`: TC-2301
`}<span className="k">title</span>{`: `}<span className="s">"Stripe card charge succeeds"</span>{`
`}<span className="k">type</span>{`: `}<span className="t">automated</span>{`
`}<span className="k">runner</span>{`: `}<span className="t">playwright</span>{`
`}<span className="k">tags</span>{`: [`}<span className="s">"smoke"</span>{`, `}<span className="s">"p0"</span>{`]
`}<span className="k">requirements</span>{`: [`}<span className="s">"REQ-PAY-001"</span>{`]
`}<span className="k">steps</span>{`:
  - `}<span className="k">do</span>{`: `}<span className="s">"Open product page"</span>{`
    `}<span className="k">expect</span>{`: `}<span className="s">"CTA visible"</span>{`
  - `}<span className="k">do</span>{`: `}<span className="s">"Add to cart"</span>{`
    `}<span className="k">expect</span>{`: `}<span className="s">"Subtotal = $49"</span>{`
  - `}<span className="k">do</span>{`: `}<span className="s">"Submit Stripe payment"</span>{`
    `}<span className="k">expect</span>{`: `}<span className="s">"Captured in 4s"</span>
              </pre>
            </div>
            <div style={{padding:18, background:"var(--bg-2)"}}>
              <div className="mono dim" style={{fontSize:10.5, textTransform:"uppercase", letterSpacing:"0.08em", marginBottom:10}}>Test Hub · live preview</div>
              <div style={{display:"flex", alignItems:"center", gap:8, marginBottom:8}}>
                <StatusBadge s="pass" />
                <span className="mono dim" style={{fontSize:10.5}}>TC-2301</span>
              </div>
              <div style={{fontSize:14, fontWeight:500, lineHeight:1.3, marginBottom:8}}>Stripe card charge succeeds on test card</div>
              <div style={{fontSize:11.5, color:"var(--text-muted)", marginBottom:14}}>3 steps · auto · playwright · last run 12m ago</div>
              <div className="bar" style={{height:8, marginBottom:6}}>
                <span className="seg-pass" style={{width:"82%"}} />
                <span className="seg-fail" style={{width:"4%"}} />
                <span className="seg-warn" style={{width:"6%"}} />
                <span style={{background:"var(--surface-2)", width:"8%"}} />
              </div>
              <div className="mono dim" style={{fontSize:10.5}}>48 runs · 82% pass · 2.4% flaky</div>

              <div style={{marginTop:18, padding:10, border:"1px solid oklch(from var(--accent) l c h / 0.4)", borderRadius:"var(--radius)", background:"var(--accent-soft)"}}>
                <div style={{fontSize:11, fontFamily:"var(--font-mono)", color:"var(--accent)", marginBottom:4}}>← UI edits commit back to git as YAML</div>
                <div style={{fontSize:11, color:"var(--text-muted)"}}>No proprietary DB. Your tests are portable.</div>
              </div>
            </div>
          </div>
        </div>

        {/* Pillars */}
        <div style={{marginTop:48}}>
          <div className="eyebrow"><span className="dot" /> Why Test Hub</div>
          <h2 style={{fontSize:32, fontWeight:600, letterSpacing:"-0.02em", margin:"14px 0 32px", maxWidth:600, lineHeight:1.15}}>One workspace where every test — manual or automated — is a first-class citizen.</h2>

          <div className="grid grid-3">
            <Pillar
              num="01"
              title="Tests as code, by default"
              body="Cases are YAML in your repo. Git is the source of truth. The UI commits back via PR — no lock-in, no DB-only artefacts."
            />
            <Pillar
              num="02"
              title="Manual and automated, side by side"
              body="A QA executing a smoke flow and a Playwright CI run land in the same timeline. Compare, filter, attribute flakes — all together."
            />
            <Pillar
              num="03"
              title="Lineage you can actually read"
              body="See requirement → test → code file → CI run → defect in one graph. Click anything to traverse. No spreadsheets, no broken JIRA links."
            />
            <Pillar
              num="04"
              title="AI that respects your codebase"
              body="Suggestions are grounded in your actual source files and existing tests. It tells you what's missing — it doesn't hallucinate fixtures."
            />
            <Pillar
              num="05"
              title="CI-native"
              body="First-party adapters for GitHub Actions, GitLab CI, Jenkins. Built-in support for Playwright, Cypress, Jest, Vitest, pytest results."
            />
            <Pillar
              num="06"
              title="Self-host or hosted"
              body="Apache 2.0. Run with Docker in 60 seconds, deploy to your cluster, or use our hosted edition for teams. Same product."
            />
          </div>
        </div>

        {/* Quickstart */}
        <div style={{marginTop:64}}>
          <div className="eyebrow"><span className="dot" /> Quickstart</div>
          <h2 style={{fontSize:32, fontWeight:600, letterSpacing:"-0.02em", margin:"14px 0 24px"}}>60 seconds to your first run.</h2>

          <div className="grid grid-2">
            <div>
              <div style={{display:"flex", flexDirection:"column", gap:14}}>
                <Step2 n="1" title="Install" body="Run the CLI in your project root. It scaffolds .testhub/ and a first example test." code="pnpm dlx testhub init" />
                <Step2 n="2" title="Define a test" body="A YAML file under tests/. Either write it by hand or let the AI draft from a prompt." code="testhub new 'cart persists on reload'" />
                <Step2 n="3" title="Run it" body="Locally for manual cases. From CI for automated. Results stream back to the UI in real time." code="testhub run --plan smoke" />
              </div>
            </div>

            <div className="card" style={{padding:0}}>
              <div style={{padding:"10px 14px", borderBottom:"1px solid var(--border)", display:"flex", alignItems:"center", gap:8}}>
                <span className="mono dim" style={{fontSize:11}}>terminal · zsh</span>
                <div className="spacer" />
                <Icon name="dots" />
              </div>
              <pre className="code" style={{border:"none", borderRadius:0, fontSize:11.5, padding:18, background:"var(--bg-2)"}}>
{`$ pnpm dlx testhub init
`}<span className="c">✓ created .testhub/config.yml</span>{`
`}<span className="c">✓ created tests/example.yml</span>{`
`}<span className="c">✓ wrote .github/workflows/testhub.yml</span>{`

$ testhub run --plan smoke
`}<span className="t">▶</span>{` running 12 tests in parallel
  `}<span className="s">✓</span>{` TC-1042 sign in with valid credentials       `}<span className="c">0.4s</span>{`
  `}<span className="s">✓</span>{` TC-1044 lockout after 5 attempts             `}<span className="c">1.8s</span>{`
  `}<span className="s">✓</span>{` TC-2210 cart counter updates                 `}<span className="c">0.1s</span>{`
  `}<span className="s">✓</span>{` TC-2301 stripe charge succeeds               `}<span className="c">0.5s</span>{`
  `}<span className="s">✗</span>{` TC-2212 cart persists (guest)                `}<span className="c">0.4s</span>{`

`}<span className="c">  11 passed · 1 failed · 4.2s total</span>{`
`}<span className="c">  → view run at https://testhub.local/r/1287</span>
              </pre>
            </div>
          </div>
        </div>

        {/* Final CTA + stats */}
        <div style={{marginTop:64, padding:"40px 32px", border:"1px solid var(--border)", borderRadius:"var(--radius-lg)", background:"var(--bg-2)", textAlign:"center"}}>
          <div className="eyebrow" style={{justifyContent:"center"}}><span className="dot" /> Open source</div>
          <h2 style={{fontSize:30, fontWeight:600, letterSpacing:"-0.02em", margin:"14px auto 14px", maxWidth:520, lineHeight:1.2}}>Built in the open. Run anywhere. Yours forever.</h2>
          <div style={{fontSize:13.5, color:"var(--text-muted)", maxWidth:520, margin:"0 auto 24px"}}>
            Apache 2.0 · no proprietary lock-in · works on a laptop or a k8s cluster. Contribute on GitHub.
          </div>

          <div style={{display:"flex", gap:6, justifyContent:"center"}}>
            <button className="btn accent" style={{padding:"8px 14px"}}>Self-host now</button>
            <button className="btn" style={{padding:"8px 14px"}}><Icon name="github" /> Star on GitHub</button>
          </div>

          <div style={{display:"flex", gap:32, justifyContent:"center", marginTop:32, fontSize:12}}>
            <Stat n="4,128" label="GitHub stars" />
            <Stat n="142" label="contributors" />
            <Stat n="63" label="releases" />
            <Stat n="1.2k" label="Discord members" />
          </div>
        </div>

        <div style={{marginTop:64, paddingTop:24, borderTop:"1px solid var(--border)", display:"flex", alignItems:"center", gap:14, fontSize:11.5, color:"var(--text-dim)"}}>
          <div className="brand-mark" style={{transform:"scale(0.9)"}}>T</div>
          <span>Test Hub</span>
          <span className="mono">v1.4.2</span>
          <span className="spacer" />
          <span className="mono">Apache 2.0 · made in the open</span>
        </div>
      </div>
    </div>
  );
}

document.documentElement.setAttribute("data-theme", "dark");

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<Landing />);
