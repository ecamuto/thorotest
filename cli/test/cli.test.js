"use strict";
/**
 * End-to-end CLI tests: spawn bin/thorotest.js against a mock ThoroTest
 * server (node:http) and assert on stdout, exit codes, and captured request
 * bodies. HOME/XDG_CONFIG_HOME point at a temp dir so a developer's real
 * config can never leak into a test.
 */
const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");
const { execFile } = require("node:child_process");

const BIN = path.join(__dirname, "..", "bin", "thorotest.js");
const TOKEN = "tt_test_token";

let server, baseUrl, tmpHome, fixtures;
const captured = { syncBodies: [], tokenBodies: [] };

function startMockServer() {
  return new Promise((resolve) => {
    server = http.createServer((req, res) => {
      const authed = req.headers.authorization === `Bearer ${TOKEN}`;
      const json = (code, body, headers = {}) => {
        res.writeHead(code, { "Content-Type": "application/json", ...headers });
        res.end(JSON.stringify(body));
      };

      if (req.url === "/health") return json(200, { status: "ok" });
      if (!authed) return json(401, { detail: "Not authenticated" });

      if (req.url === "/api/me") return json(200, { username: "enzo", role: "admin" });
      if (req.url.startsWith("/api/tests")) return json(200, [], { "X-Total-Count": "42" });
      if (req.url.startsWith("/api/runs")) {
        return json(200, [
          { id: "R-1", name: "Nightly", status: "completed", passed: 10, failed: 2, blocked: 0, total: 12, started: "2026-07-01T02:00:00Z" },
          { id: "R-2", name: "Smoke", status: "active", passed: 3, failed: 0, blocked: 1, total: 8, started: "2026-07-14T09:00:00Z" },
        ], { "X-Total-Count": "2" });
      }

      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        const data = body ? JSON.parse(body) : null;
        if (req.method === "POST" && req.url === "/api/sync/yaml") {
          captured.syncBodies.push(data);
          const parsedOk = data.files.filter((f) => /(^|\n)title:/.test(f.content));
          const skipped = data.files.length - parsedOk.length;
          return json(200, {
            created: parsedOk.length, updated: 0, skipped,
            commit: data.ref, files: data.files.length,
            warnings: skipped ? ["bad.yaml: YAML test missing required 'title'"] : [],
            dry_run: data.dry_run,
          });
        }
        if (req.method === "POST" && req.url === "/api/tokens") {
          captured.tokenBodies.push(data);
          return json(201, { id: 7, name: data.name, scope: data.scope, token: "tt_new_secret" });
        }
        json(404, { detail: "not found" });
      });
    });
    server.listen(0, "127.0.0.1", () => {
      baseUrl = `http://127.0.0.1:${server.address().port}`;
      resolve();
    });
  });
}

function runCli(args, { env = {}, cwd = tmpHome } = {}) {
  return new Promise((resolve) => {
    execFile(process.execPath, [BIN, ...args], {
      cwd,
      env: {
        PATH: process.env.PATH,
        HOME: tmpHome,
        XDG_CONFIG_HOME: path.join(tmpHome, ".config"),
        THOROTEST_URL: baseUrl,
        THOROTEST_TOKEN: TOKEN,
        NO_COLOR: "1",
        ...env,
      },
    }, (err, stdout, stderr) => {
      resolve({ code: err ? err.code : 0, stdout, stderr });
    });
  });
}

before(async () => {
  tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), "thorotest-cli-test-"));
  fixtures = path.join(tmpHome, "tests");
  fs.mkdirSync(fixtures, { recursive: true });
  fs.writeFileSync(path.join(fixtures, "login.yaml"),
    'id: TC-1\ntitle: "Login works"\ntype: e2e\ntags: [smoke]\nfolder: Auth\n');
  fs.writeFileSync(path.join(fixtures, "signup.yml"),
    "id: TC-2\ntitle: Signup works\ntype: manual\n");
  fs.writeFileSync(path.join(fixtures, "notes.txt"), "not yaml, must be ignored");
  await startMockServer();
});

after(() => {
  server.close();
  fs.rmSync(tmpHome, { recursive: true, force: true });
});

// ── global behaviour ────────────────────────────────────────────

test("--version prints version, exit 0", async () => {
  const r = await runCli(["--version"]);
  assert.equal(r.code, 0);
  assert.match(r.stdout.trim(), /^\d+\.\d+\.\d+$/);
});

test("no command prints help, exit 2", async () => {
  const r = await runCli([]);
  assert.equal(r.code, 2);
  assert.match(r.stdout, /Usage/);
});

test("unknown command exits 2", async () => {
  const r = await runCli(["frobnicate"]);
  assert.equal(r.code, 2);
  assert.match(r.stderr, /unknown command 'frobnicate'/);
});

test("missing token exits 2 with guidance", async () => {
  const r = await runCli(["status"], { env: { THOROTEST_TOKEN: "" } });
  assert.equal(r.code, 2);
  assert.match(r.stderr, /no API token configured/);
});

test("bad token exits 4", async () => {
  const r = await runCli(["status"], { env: { THOROTEST_TOKEN: "wrong" } });
  assert.equal(r.code, 4);
  assert.match(r.stderr, /Not authenticated/);
});

test("unreachable server exits 3", async () => {
  const r = await runCli(["status"], { env: { THOROTEST_URL: "http://127.0.0.1:9" } });
  assert.equal(r.code, 3);
  assert.match(r.stderr, /cannot reach/);
});

// ── status ──────────────────────────────────────────────────────

test("status prints server, user, counts and last run", async () => {
  const r = await runCli(["status"]);
  assert.equal(r.code, 0);
  assert.match(r.stdout, /enzo \(admin\)/);
  assert.match(r.stdout, /Tests\s+42/);
  assert.match(r.stdout, /2 total, 1 open/);
  assert.match(r.stdout, /Smoke.*active/); // most recent by started
});

test("status --json emits machine-readable shape", async () => {
  const r = await runCli(["status", "--json"]);
  assert.equal(r.code, 0);
  const data = JSON.parse(r.stdout);
  assert.equal(data.tests.total, 42);
  assert.equal(data.runs.open, 1);
  assert.equal(data.runs.last.id, "R-2");
});

// ── lint ────────────────────────────────────────────────────────

test("lint on valid dir exits 0 and counts files", async () => {
  const r = await runCli(["lint", "tests"]);
  assert.equal(r.code, 0);
  assert.match(r.stdout, /2 files, 0 errors/);
});

test("lint on invalid file exits 1 with file:line", async () => {
  const bad = path.join(tmpHome, "bad.yaml");
  fs.writeFileSync(bad, "id: TC-9\nmeta:\n  nested: true\n");
  const r = await runCli(["lint", "bad.yaml"]);
  assert.equal(r.code, 1);
  assert.match(r.stderr, /bad\.yaml:3: nested mappings/);
});

test("lint --json returns structured findings", async () => {
  const r = await runCli(["lint", "bad.yaml", "--json"]);
  assert.equal(r.code, 1);
  const data = JSON.parse(r.stdout);
  assert.equal(data.ok, false);
  assert.equal(data.errors[0].line, 3);
});

test("lint on missing path exits 2", async () => {
  const r = await runCli(["lint", "does-not-exist"]);
  assert.equal(r.code, 2);
});

// ── sync ────────────────────────────────────────────────────────

test("sync pushes files with relative posix paths", async () => {
  captured.syncBodies.length = 0;
  const r = await runCli(["sync", "tests", "--ref", "v9"]);
  assert.equal(r.code, 0);
  assert.match(r.stdout, /synced\s+2 files: 2 created/);
  const body = captured.syncBodies[0];
  assert.deepEqual(body.files.map((f) => f.path).sort(), ["tests/login.yaml", "tests/signup.yml"]);
  assert.equal(body.ref, "v9");
  assert.equal(body.source, "cli://local");
  assert.equal(body.dry_run, false);
});

test("sync --dry-run passes flag and reports without persisting", async () => {
  captured.syncBodies.length = 0;
  const r = await runCli(["sync", "tests", "--dry-run"]);
  assert.equal(r.code, 0);
  assert.match(r.stdout, /dry run — nothing persisted/);
  assert.equal(captured.syncBodies[0].dry_run, true);
});

test("sync refuses locally-invalid files without --force", async () => {
  captured.syncBodies.length = 0;
  const dir = path.join(tmpHome, "mixed");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "ok.yaml"), "id: TC-10\ntitle: fine\n");
  fs.writeFileSync(path.join(dir, "bad.yaml"), "id: TC-11\n"); // no title
  const r = await runCli(["sync", "mixed"]);
  assert.equal(r.code, 1);
  assert.match(r.stderr, /missing required 'title'/);
  assert.equal(captured.syncBodies.length, 0, "server must not be called");
});

test("sync --force pushes anyway and exits 1 when the server skips files", async () => {
  captured.syncBodies.length = 0;
  const r = await runCli(["sync", "mixed", "--force"]);
  assert.equal(r.code, 1);
  assert.match(r.stdout, /1 skipped/);
  assert.equal(captured.syncBodies.length, 1);
});

test("sync --json emits server stats", async () => {
  const r = await runCli(["sync", "tests", "--json"]);
  assert.equal(r.code, 0);
  const data = JSON.parse(r.stdout);
  assert.equal(data.created, 2);
  assert.equal(data.skipped, 0);
});

// ── token ───────────────────────────────────────────────────────

test("token create prints the token once", async () => {
  captured.tokenBodies.length = 0;
  const r = await runCli(["token", "create", "--name", "ci", "--scope", "sync"]);
  assert.equal(r.code, 0);
  assert.match(r.stdout, /tt_new_secret/);
  assert.match(r.stderr, /shown once/);
  assert.deepEqual(captured.tokenBodies[0], { name: "ci", scope: "sync" });
});

test("token without subcommand exits 2", async () => {
  const r = await runCli(["token"]);
  assert.equal(r.code, 2);
  assert.match(r.stderr, /usage: thorotest token create/);
});

test("token create without --name exits 2", async () => {
  const r = await runCli(["token", "create"]);
  assert.equal(r.code, 2);
  assert.match(r.stderr, /requires --name/);
});
