"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { lintContent, lintFiles } = require("../lib/lint");

const msgs = (arr) => arr.map((x) => x.message).join("\n");

test("valid file: no errors", () => {
  const r = lintContent("id: TC-1\ntitle: ok\ntype: manual\npriority: high\n");
  assert.equal(r.errors.length, 0);
  assert.equal(r.warnings.length, 0);
});

test("missing title is an error", () => {
  const r = lintContent("id: TC-1\ntype: manual\n");
  assert.match(msgs(r.errors), /missing required 'title'/);
});

test("empty title is an error", () => {
  const r = lintContent("id: TC-1\ntitle: ''\n");
  assert.match(msgs(r.errors), /missing required 'title'/);
});

test("parse failure surfaces as error with line", () => {
  const r = lintContent("title: t\nmeta:\n  a: b\n");
  assert.equal(r.errors.length, 1);
  assert.equal(r.errors[0].line, 3);
});

test("type aliases are accepted without warning", () => {
  for (const t of ["automated", "auto", "e2e", "integration", "unit", "manual", "E2E"]) {
    const r = lintContent(`id: TC-1\ntitle: ok\ntype: ${t}\n`);
    assert.equal(msgs(r.warnings).includes("unknown type"), false, `type ${t}`);
  }
});

test("unknown type warns with coercion target", () => {
  const r = lintContent("id: TC-1\ntitle: ok\ntype: exploratory\n");
  assert.match(msgs(r.warnings), /unknown type 'exploratory' — server will import it as 'manual'/);
});

test("priority aliases accepted, unknown warns to med", () => {
  const ok = lintContent("id: TC-1\ntitle: ok\npriority: P0\n");
  assert.equal(msgs(ok.warnings).includes("unknown priority"), false);
  const bad = lintContent("id: TC-1\ntitle: ok\npriority: urgent\n");
  assert.match(msgs(bad.warnings), /unknown priority 'urgent' — server will import it as 'med'/);
});

test("status always warns that sync ignores it", () => {
  const r = lintContent("id: TC-1\ntitle: ok\nstatus: passed\n");
  assert.match(msgs(r.warnings), /'status' is ignored by sync/);
});

test("unknown status also warns about coercion", () => {
  const r = lintContent("id: TC-1\ntitle: ok\nstatus: flaky\n");
  assert.match(msgs(r.warnings), /unknown status 'flaky'/);
});

test("unknown keys warn", () => {
  const r = lintContent("id: TC-1\ntitle: ok\nsteps: []\n");
  assert.match(msgs(r.warnings), /unknown key 'steps'/);
});

test("missing id warns about idempotency", () => {
  const r = lintContent("title: ok\n");
  assert.match(msgs(r.warnings), /no 'id'/);
});

test("tags as comma string is fine (server splits it)", () => {
  const r = lintContent("id: TC-1\ntitle: ok\ntags: smoke, auth\n");
  assert.equal(msgs(r.warnings).includes("'tags'"), false);
});

test("tags as number warns", () => {
  const r = lintContent("id: TC-1\ntitle: ok\ntags: 3\n");
  assert.match(msgs(r.warnings), /'tags' should be a list/);
});

// ── cross-file ──────────────────────────────────────────────────

test("duplicate id across files is an error naming both files", () => {
  const r = lintFiles([
    { path: "a.yaml", content: "id: TC-1\ntitle: a\n" },
    { path: "b.yaml", content: "id: TC-1\ntitle: b\n" },
  ]);
  assert.equal(r.errors.length, 1);
  assert.match(r.errors[0].message, /duplicate id 'TC-1' — already declared in a\.yaml/);
  assert.equal(r.errors[0].path, "b.yaml");
});

test("distinct ids across files pass", () => {
  const r = lintFiles([
    { path: "a.yaml", content: "id: TC-1\ntitle: a\n" },
    { path: "b.yaml", content: "id: TC-2\ntitle: b\n" },
  ]);
  assert.equal(r.errors.length, 0);
});
