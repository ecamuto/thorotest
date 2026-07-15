"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { parse, ParseError } = require("../lib/yaml");

// ── happy path (mirrors backend/tests/test_github_sync.py parsing cases) ──

test("parses the documented file shape", () => {
  const doc = parse(`
id: TC-2301
title: "Stripe card charge succeeds on test card"
type: e2e
runner: playwright
status: passed
priority: P1
owner: anna@example.com
tags: [smoke, payment]
folder: Checkout/Payment
`);
  assert.equal(doc.id, "TC-2301");
  assert.equal(doc.title, "Stripe card charge succeeds on test card");
  assert.equal(doc.type, "e2e");
  assert.equal(doc.runner, "playwright");
  assert.equal(doc.priority, "P1");
  assert.deepEqual(doc.tags, ["smoke", "payment"]);
  assert.equal(doc.folder, "Checkout/Payment");
});

test("block list for tags", () => {
  const doc = parse("title: t\ntags:\n  - smoke\n  - auth\n");
  assert.deepEqual(doc.tags, ["smoke", "auth"]);
});

test("single-quoted strings unescape doubled quotes", () => {
  assert.equal(parse("title: 'it''s fine'").title, "it's fine");
});

test("double-quoted strings handle escapes", () => {
  assert.equal(parse('title: "line1\\nline2"').title, "line1\nline2");
});

test("plain scalars are typed", () => {
  const doc = parse("title: t\ncount: 3\nflag: true\nnothing: null\nfloaty: 1.5");
  assert.equal(doc.count, 3);
  assert.equal(doc.flag, true);
  assert.equal(doc.nothing, null);
  assert.equal(doc.floaty, 1.5);
});

test("comments and blank lines are ignored", () => {
  const doc = parse("# header\n\ntitle: t # trailing\n");
  assert.equal(doc.title, "t");
});

test("hash inside quoted string is not a comment", () => {
  assert.equal(parse('title: "a # b"').title, "a # b");
});

test("leading --- document marker is accepted", () => {
  assert.equal(parse("---\ntitle: t").title, "t");
});

test("empty value yields null", () => {
  const doc = parse("title: t\nrunner:\nowner: x");
  assert.equal(doc.runner, null);
});

test("trailing key with empty value yields null", () => {
  assert.equal(parse("title: t\nrunner:").runner, null);
});

test("inline empty list", () => {
  assert.deepEqual(parse("title: t\ntags: []").tags, []);
});

test("quoted items in inline list keep commas", () => {
  assert.deepEqual(parse('title: t\ntags: ["a,b", c]').tags, ["a,b", "c"]);
});

// ── rejections ──────────────────────────────────────────────────

const rejects = (content, re) => {
  assert.throws(() => parse(content), (e) => e instanceof ParseError && re.test(e.message));
};

test("rejects top-level list", () => rejects("- a\n- b", /must be a mapping/));
test("rejects empty document", () => rejects("# only comments\n", /empty YAML/));
test("rejects nested mappings", () => rejects("title: t\nmeta:\n  a: b", /nested mappings/));
test("rejects mappings inside lists", () => rejects("title: t\nsteps:\n  - name: x", /mappings inside lists/));
test("rejects block scalars", () => rejects("title: |\n  multi", /block scalars/));
test("rejects anchors", () => rejects("title: &a val", /anchors/));
test("rejects multiple documents", () => rejects("title: a\n---\ntitle: b", /multiple YAML documents/));
test("rejects duplicate keys", () => rejects("title: a\ntitle: b", /duplicate key 'title'/));
test("rejects tab indentation", () => rejects("title: t\n\tbad: x", /tabs are not allowed/));
test("rejects unterminated double quote", () => rejects("title: \"open", /unterminated double/));
test("rejects unterminated single quote", () => rejects("title: 'open", /unterminated single/));
test("rejects unterminated inline list", () => rejects("title: t\ntags: [a, b", /unterminated inline list/));
test("rejects nested collections in list", () => rejects("title: t\ntags: [[a]]", /nested collections/));
test("rejects inline mapping value", () => rejects("title: t\nmeta: {a: b}", /nested inline mappings/));
test("rejects list item without key", () => rejects("  - stray", /list item without/));

test("parse errors carry line numbers", () => {
  try {
    parse("title: t\nmeta:\n  a: b");
    assert.fail("should throw");
  } catch (e) {
    assert.equal(e.line, 3);
  }
});
