// ThoroTest — Docs & API view

const DOC_SECTIONS = [
  { id: "quickstart", label: "Quickstart",  icon: "branch" },
  { id: "rest",       label: "REST API",    icon: "doc" },
  { id: "cli",        label: "CLI",         icon: "play" },
  { id: "sdks",       label: "SDKs",        icon: "filter" },
  { id: "webhooks",   label: "Webhooks",    icon: "plug" },
];

const METHOD_STYLE = {
  get:    { color: "var(--info)",  bg: "var(--info-soft)"  },
  post:   { color: "var(--pass)",  bg: "var(--pass-soft)"  },
  patch:  { color: "var(--warn)",  bg: "var(--warn-soft)"  },
  delete: { color: "var(--fail)",  bg: "var(--fail-soft)"  },
  put:    { color: "var(--warn)",  bg: "var(--warn-soft)"  },
};

function MethodBadge({ method }) {
  const s = METHOD_STYLE[method.toLowerCase()] || { color: "var(--text-muted)", bg: "var(--surface)" };
  return (
    <span style={{
      display: "inline-block", fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700,
      color: s.color, background: s.bg, padding: "2px 7px", borderRadius: 4,
      textTransform: "uppercase", letterSpacing: "0.06em", minWidth: 50, textAlign: "center",
    }}>
      {method.toUpperCase()}
    </span>
  );
}

function useCopy() {
  const [copied, setCopied] = React.useState(null);
  const copy = (text, key) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(null), 1500);
    });
  };
  return [copied, copy];
}

function CodeBlock({ children }) {
  return (
    <pre className="code" style={{ marginTop: 8, marginBottom: 0 }}>
      {children}
    </pre>
  );
}

/* ── schema resolver ──────────────────────────────────── */

function resolveRef(ref, schemas) {
  if (!ref) return null;
  const name = ref.replace("#/components/schemas/", "");
  return schemas[name] || null;
}

function resolveSchema(schema, schemas, depth = 0) {
  if (!schema || depth > 3) return null;
  if (schema.$ref) return resolveSchema(resolveRef(schema.$ref, schemas), schemas, depth + 1);
  if (schema.allOf) return resolveSchema(schema.allOf[0], schemas, depth + 1);
  return schema;
}

function SchemaFields({ schema, schemas, depth = 0 }) {
  const resolved = resolveSchema(schema, schemas);
  if (!resolved) return null;

  if (resolved.type === "array") {
    return (
      <div>
        <span style={{ fontSize: 11, color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>array of:</span>
        <div style={{ marginLeft: 12 }}>
          <SchemaFields schema={resolved.items} schemas={schemas} depth={depth + 1} />
        </div>
      </div>
    );
  }

  if (resolved.properties) {
    const required = resolved.required || [];
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {Object.entries(resolved.properties).map(([name, prop]) => {
          const resolvedProp = resolveSchema(prop, schemas);
          const type = resolvedProp?.type || (resolvedProp?.allOf ? "object" : prop.$ref ? "object" : "any");
          const isReq = required.includes(name);
          return (
            <div key={name} style={{ display: "flex", alignItems: "baseline", gap: 8, fontSize: 11.5 }}>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--text)", minWidth: 120 }}>{name}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--info)" }}>{type}</span>
              {isReq && <span style={{ fontSize: 10, color: "var(--fail)", fontFamily: "var(--font-mono)" }}>required</span>}
              {resolvedProp?.description && (
                <span style={{ color: "var(--text-dim)", fontSize: 11 }}>{resolvedProp.description}</span>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  const type = resolved.type || "any";
  return <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--info)" }}>{type}</span>;
}

/* ── endpoint card ────────────────────────────────────── */

function EndpointCard({ method, path, op, schemas }) {
  const [open, setOpen] = React.useState(false);

  const params = op.parameters || [];
  const pathParams  = params.filter(p => p.in === "path");
  const queryParams = params.filter(p => p.in === "query");
  const bodySchema  = op.requestBody?.content?.["application/json"]?.schema;
  const resp200     = op.responses?.["200"]?.content?.["application/json"]?.schema
                   || op.responses?.["201"]?.content?.["application/json"]?.schema;

  return (
    <div style={{
      border: "1px solid var(--border)", borderRadius: 8, marginBottom: 6, overflow: "hidden",
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", display: "flex", alignItems: "center", gap: 10,
          padding: "10px 14px", background: open ? "var(--surface)" : "transparent",
          border: "none", cursor: "pointer", textAlign: "left",
        }}
      >
        <MethodBadge method={method} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--text)", flex: 1 }}>{path}</span>
        {op.summary && (
          <span style={{ fontSize: 12, color: "var(--text-muted)", marginRight: 8 }}>{op.summary}</span>
        )}
        <span style={{ fontSize: 10, color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 14 }}>
          {op.description && (
            <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.6 }}>{op.description}</p>
          )}

          {pathParams.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Path params</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {pathParams.map(p => (
                  <div key={p.name} style={{ display: "flex", alignItems: "baseline", gap: 8, fontSize: 11.5 }}>
                    <span style={{ fontFamily: "var(--font-mono)", color: "var(--text)", minWidth: 120 }}>{p.name}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--info)" }}>{p.schema?.type || "string"}</span>
                    {p.required && <span style={{ fontSize: 10, color: "var(--fail)", fontFamily: "var(--font-mono)" }}>required</span>}
                    {p.description && <span style={{ color: "var(--text-dim)", fontSize: 11 }}>{p.description}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {queryParams.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Query params</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {queryParams.map(p => (
                  <div key={p.name} style={{ display: "flex", alignItems: "baseline", gap: 8, fontSize: 11.5 }}>
                    <span style={{ fontFamily: "var(--font-mono)", color: "var(--text)", minWidth: 120 }}>{p.name}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--info)" }}>{p.schema?.type || "string"}</span>
                    {p.required && <span style={{ fontSize: 10, color: "var(--fail)", fontFamily: "var(--font-mono)" }}>required</span>}
                    {p.description && <span style={{ color: "var(--text-dim)", fontSize: 11 }}>{p.description}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {bodySchema && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Request body</div>
              <SchemaFields schema={bodySchema} schemas={schemas} />
            </div>
          )}

          {resp200 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Response</div>
              <SchemaFields schema={resp200} schemas={schemas} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── REST API section ─────────────────────────────────── */

function RestApiSection() {
  const [spec, setSpec]   = React.useState(null);
  const [err, setErr]     = React.useState(null);
  const [group, setGroup] = React.useState(null);

  React.useEffect(() => {
    fetch("/openapi.json")
      .then(r => r.json())
      .then(data => {
        setSpec(data);
        // default to first group
        const groups = buildGroups(data);
        if (groups.length) setGroup(groups[0].tag);
      })
      .catch(() => setErr("Could not load /openapi.json"));
  }, []);

  if (err)  return <div style={{ color: "var(--fail)", fontSize: 13 }}>{err}</div>;
  if (!spec) return <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading spec…</div>;

  const schemas = spec.components?.schemas || {};
  const groups  = buildGroups(spec);
  const current = groups.find(g => g.tag === group) || groups[0];

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div className="page-title" style={{ fontSize: 18 }}>REST API</div>
        <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 4 }}>
          Base URL: <code style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>http://localhost:8000/api</code>
          &nbsp;·&nbsp; Auth: <code style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>Authorization: Bearer &lt;token&gt;</code>
        </div>
      </div>

      <div style={{ display: "flex", gap: 0, borderBottom: "1px solid var(--border)", marginBottom: 16 }}>
        {groups.map(g => (
          <button
            key={g.tag}
            className={"tab" + (g.tag === (current?.tag) ? " active" : "")}
            onClick={() => setGroup(g.tag)}
            style={{ border: "none", background: "transparent", cursor: "pointer", textTransform: "capitalize" }}
          >
            {g.tag}
            <span className="count">{g.endpoints.length}</span>
          </button>
        ))}
      </div>

      {current && (
        <div>
          {current.endpoints.map(({ method, path, op }) => (
            <EndpointCard key={method + path} method={method} path={path} op={op} schemas={schemas} />
          ))}
        </div>
      )}
    </div>
  );
}

function buildGroups(spec) {
  const map = {};
  for (const [path, methods] of Object.entries(spec.paths || {})) {
    for (const [method, op] of Object.entries(methods)) {
      if (!["get","post","patch","put","delete"].includes(method)) continue;
      const tag = (op.tags?.[0] || "other").toLowerCase();
      if (!map[tag]) map[tag] = [];
      map[tag].push({ method, path, op });
    }
  }
  const TAG_ORDER = ["tests","runs","defects","requirements","folders","auth","projects","categories","activity","pipelines"];
  const sorted = [...TAG_ORDER.filter(t => map[t]), ...Object.keys(map).filter(t => !TAG_ORDER.includes(t))];
  return sorted.map(tag => ({ tag, endpoints: map[tag] }));
}

/* ── Quickstart section ───────────────────────────────── */

function QuickstartSection() {
  return (
    <div style={{ maxWidth: 700 }}>
      <div className="page-title" style={{ fontSize: 18, marginBottom: 4 }}>Quickstart</div>
      <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 28, lineHeight: 1.6 }}>
        Get started with ThoroTest in under 60 seconds.
      </div>

      <DocStep n="1" title="Start the server">
        <CodeBlock>{`cd thorotest
make dev          # builds the frontend and starts the app on :8000`}</CodeBlock>
      </DocStep>

      <DocStep n="2" title="Register an account">
        <CodeBlock>{`curl -X POST http://localhost:8000/api/auth/register \\
  -H "Content-Type: application/json" \\
  -d '{"username": "alice", "email": "alice@example.com", "password": "secret1"}'`}</CodeBlock>
      </DocStep>

      <DocStep n="3" title="Get a token">
        <CodeBlock>{`curl -X POST http://localhost:8000/api/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"email": "alice@example.com", "password": "secret1"}'

# → { "access_token": "eyJ...", "token_type": "bearer" }
TOKEN="eyJ..."`}</CodeBlock>
      </DocStep>

      <DocStep n="4" title="List your tests">
        <CodeBlock>{`curl http://localhost:8000/api/tests?limit=50&offset=0 \\
  -H "Authorization: Bearer $TOKEN"
# Pagination: limit/offset (max 1000/page); the X-Total-Count response
# header carries the total row count for the filtered query.`}</CodeBlock>
      </DocStep>

      <DocStep n="5" title="Create a test">
        <CodeBlock>{`curl -X POST http://localhost:8000/api/tests \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "Login flow",
    "type": "manual",
    "status": "draft",
    "priority": "high"
  }'`}</CodeBlock>
      </DocStep>

      <DocStep n="6" title="Start a run">
        <CodeBlock>{`curl -X POST http://localhost:8000/api/runs \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "Sprint 14 regression",
    "environment": "staging",
    "test_ids": ["TC-1001", "TC-1002"]
  }'`}</CodeBlock>
      </DocStep>

      <div style={{ marginTop: 28, padding: "14px 16px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.7 }}>
        <strong style={{ color: "var(--text)" }}>Python example</strong>
        <CodeBlock>{`import httpx

BASE = "http://localhost:8000/api"

r = httpx.post(f"{BASE}/auth/login", json={"email": "alice@example.com", "password": "secret1"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

tests = httpx.get(f"{BASE}/tests", headers=headers).json()
print(f"{len(tests)} tests found")`}</CodeBlock>
      </div>
    </div>
  );
}

function DocStep({ n, title, children }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <span style={{
          width: 22, height: 22, borderRadius: "50%", background: "var(--accent)",
          color: "#fff", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0,
        }}>{n}</span>
        <span style={{ fontSize: 13.5, fontWeight: 600 }}>{title}</span>
      </div>
      <div style={{ marginLeft: 32 }}>{children}</div>
    </div>
  );
}

/* ── CLI section ──────────────────────────────────────── */

function CliSection() {
  const [copied, copy] = useCopy();
  const cmds = [
    { cmd: "thorotest run [--env staging]", desc: "Execute all tests in the current project." },
    { cmd: "thorotest run --filter tag=smoke", desc: "Run a filtered subset of tests." },
    { cmd: "thorotest new test",  desc: "Interactive wizard to create a new test case." },
    { cmd: "thorotest new run",   desc: "Start a new run from the CLI." },
    { cmd: "thorotest sync",      desc: "Push local YAML test definitions to the server." },
    { cmd: "thorotest lint",      desc: "Validate YAML schema before sync." },
    { cmd: "thorotest status",    desc: "Show current project, active runs, last results." },
    { cmd: "thorotest token create --name ci", desc: "Generate a long-lived API token for CI." },
  ];

  return (
    <div style={{ maxWidth: 700 }}>
      <div className="page-title" style={{ fontSize: 18, marginBottom: 4 }}>CLI</div>
      <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 20, lineHeight: 1.6 }}>
        <code style={{ fontFamily: "var(--font-mono)" }}>npm install -g @thorotest/cli</code>
        &nbsp;·&nbsp; Requires Node 18+
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {cmds.map(c => (
          <button
            key={c.cmd}
            onClick={() => copy(c.cmd, c.cmd)}
            style={{ display: "flex", gap: 16, alignItems: "baseline", padding: "8px 12px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, cursor: "pointer", textAlign: "left", width: "100%", transition: "background 0.1s" }}
            title="Click to copy"
          >
            <code style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)", minWidth: 260, flex: 1 }}>{c.cmd}</code>
            <span style={{ fontSize: 12.5, color: "var(--text-muted)", flex: 1 }}>{c.desc}</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: copied === c.cmd ? "var(--pass)" : "var(--text-dim)", minWidth: 50, textAlign: "right" }}>
              {copied === c.cmd ? "✓ copied" : "copy"}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── SDKs section ─────────────────────────────────────── */

function SdksSection() {
  const sdks = [
    {
      lang: "TypeScript / JavaScript",
      install: "npm install @thorotest/sdk",
      snippet: `import { ThoroTest } from "@thorotest/sdk";

const th = new ThoroTest({ token: process.env.TH_TOKEN });

const tests = await th.tests.list({ status: "active" });
const run   = await th.runs.create({ name: "CI run", testIds: tests.map(t => t.id) });`,
    },
    {
      lang: "Python",
      install: "pip install thorotest",
      snippet: `from thorotest import ThoroTest

th = ThoroTest(token=os.environ["TH_TOKEN"])

tests = th.tests.list(status="active")
run   = th.runs.create(name="CI run", test_ids=[t.id for t in tests])`,
    },
    {
      lang: "Go",
      install: "go get github.com/thorotest/sdk-go",
      snippet: `client := thorotest.New(os.Getenv("TH_TOKEN"))

tests, _ := client.Tests.List(ctx, &thorotest.TestFilter{Status: "active"})
run, _   := client.Runs.Create(ctx, &thorotest.CreateRunInput{Name: "CI run"})`,
    },
  ];

  return (
    <div style={{ maxWidth: 720 }}>
      <div className="page-title" style={{ fontSize: 18, marginBottom: 16 }}>SDKs</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {sdks.map(s => (
          <div key={s.lang} style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", background: "var(--surface)", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{s.lang}</span>
              <code style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--text-muted)" }}>{s.install}</code>
            </div>
            <CodeBlock>{s.snippet}</CodeBlock>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Webhooks section ─────────────────────────────────── */

function WebhooksSection() {
  const [copied, copy] = useCopy();
  const events = [
    { name: "run.created",    desc: "A new test run was created." },
    { name: "run.completed",  desc: "A run finished (passed, failed, or aborted)." },
    { name: "test.created",   desc: "A new test case was added to the library." },
    { name: "test.updated",   desc: "A test case was edited or its status changed." },
    { name: "defect.created", desc: "A defect was linked to a test or run." },
  ];

  return (
    <div style={{ maxWidth: 700 }}>
      <div className="page-title" style={{ fontSize: 18, marginBottom: 4 }}>Webhooks</div>
      <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 20, lineHeight: 1.6 }}>
        ThoroTest POSTs a JSON payload to your endpoint on each event. Verify with <code style={{ fontFamily: "var(--font-mono)" }}>X-ThoroTest-Signature</code> (HMAC-SHA256).
      </div>

      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Events</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {events.map(e => (
            <button
              key={e.name}
              onClick={() => copy(e.name, e.name)}
              style={{ display: "flex", gap: 16, alignItems: "baseline", padding: "7px 12px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, cursor: "pointer", textAlign: "left", width: "100%" }}
              title="Click to copy event name"
            >
              <code style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--warn)", minWidth: 180 }}>{e.name}</code>
              <span style={{ fontSize: 12.5, color: "var(--text-muted)", flex: 1 }}>{e.desc}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: copied === e.name ? "var(--pass)" : "var(--text-dim)" }}>
                {copied === e.name ? "✓ copied" : "copy"}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Payload shape</div>
      <CodeBlock>{`{
  "event":   "run.completed",
  "ts":      "2025-05-26T14:03:00Z",
  "project": "my-project",
  "data": {
    "run_id": "R-0042",
    "status": "failed",
    "passed": 31,
    "failed": 4,
    "total":  35
  }
}`}</CodeBlock>
    </div>
  );
}

/* ── main Docs component ──────────────────────────────── */

function Docs() {
  const [section, setSection] = React.useState("quickstart");

  return (
    <div className="page fade-in" style={{ padding: 0, display: "flex", gap: 0, maxWidth: 1100, height: "100%" }}>
      {/* sidebar */}
      <div style={{
        width: 180, flexShrink: 0,
        borderRight: "1px solid var(--border)",
        padding: "20px 0",
        display: "flex", flexDirection: "column", gap: 2,
      }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", letterSpacing: "0.06em", textTransform: "uppercase", padding: "0 16px", marginBottom: 6 }}>Docs & API</div>
        {DOC_SECTIONS.map(s => (
          <button
            key={s.id}
            className={"nav-item" + (section === s.id ? " active" : "")}
            style={{ margin: "0 8px", borderRadius: 6, border: "none", background: section === s.id ? "var(--nav-active-bg, rgba(99,102,241,0.12))" : "transparent", color: section === s.id ? "var(--accent)" : "var(--text)", cursor: "pointer", textAlign: "left", display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", fontSize: 13 }}
            onClick={() => setSection(s.id)}
            aria-current={section === s.id ? "page" : undefined}
          >
            <Icon name={s.icon} className="nav-icon" />
            {s.label}
          </button>
        ))}
      </div>

      {/* content */}
      <div style={{ flex: 1, padding: "28px 36px", overflowY: "auto" }}>
        {section === "quickstart" && <QuickstartSection />}
        {section === "rest"       && <RestApiSection />}
        {section === "cli"        && <CliSection />}
        {section === "sdks"       && <SdksSection />}
        {section === "webhooks"   && <WebhooksSection />}
      </div>
    </div>
  );
}
window.Docs = Docs;
