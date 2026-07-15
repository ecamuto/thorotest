"use strict";
/**
 * Validation rules for ThoroTest "test as code" YAML files.
 *
 * Mirrors the server-side normalizer (backend/importers/yaml_importer.py):
 * anything the server would *reject* is an error here; anything the server
 * would silently *coerce to a default* is a warning here, so authors learn
 * about typos before the file is synced. The alias maps below must stay in
 * lockstep with the Python `_TYPE_MAP` / `_PRIORITY_MAP` / `_STATUS_MAP`.
 */
const { parse, ParseError } = require("./yaml");

const TYPE_MAP = {
  automated: "automated", auto: "automated", e2e: "automated",
  integration: "automated", unit: "automated",
  manual: "manual",
};
const PRIORITY_MAP = {
  low: "low", p3: "low",
  med: "med", medium: "med", p2: "med", normal: "med",
  high: "high", p1: "high",
  critical: "critical", crit: "critical", p0: "critical", blocker: "critical",
};
const STATUS_MAP = {
  pass: "pass", passed: "pass", ok: "pass", green: "pass",
  fail: "fail", failed: "fail", red: "fail",
  blocked: "blocked",
  pending: "pending", todo: "pending", untested: "pending",
};

const KNOWN_KEYS = new Set([
  "id", "title", "type", "runner", "status", "priority", "owner", "tags", "folder",
]);

/**
 * Lint one file's content.
 * Returns { errors: [{message, line?}], warnings: [{message, line?}], doc? }.
 * `doc` is the parsed mapping when parsing succeeded.
 */
function lintContent(content) {
  const errors = [];
  const warnings = [];
  let doc;
  try {
    doc = parse(content);
  } catch (e) {
    if (e instanceof ParseError) {
      errors.push({ message: e.message, line: e.line });
      return { errors, warnings };
    }
    throw e;
  }

  const title = String(doc.title ?? "").trim();
  if (!title) {
    errors.push({ message: "missing required 'title'" });
  }

  for (const key of Object.keys(doc)) {
    if (!KNOWN_KEYS.has(key)) {
      warnings.push({ message: `unknown key '${key}' — ignored by the server` });
    }
  }

  const checkEnum = (key, map, fallback) => {
    if (doc[key] === undefined || doc[key] === null) return;
    const raw = String(doc[key]).trim().toLowerCase();
    if (!(raw in map)) {
      const valid = [...new Set(Object.keys(map))].join(", ");
      warnings.push({ message: `unknown ${key} '${doc[key]}' — server will import it as '${fallback}' (valid: ${valid})` });
    }
  };
  checkEnum("type", TYPE_MAP, "manual");
  checkEnum("priority", PRIORITY_MAP, "med");
  checkEnum("status", STATUS_MAP, "pending");

  if (doc.status !== undefined && doc.status !== null) {
    warnings.push({ message: "'status' is ignored by sync — a test's status is owned by run results" });
  }

  if (doc.tags !== undefined && doc.tags !== null &&
      !Array.isArray(doc.tags) && typeof doc.tags !== "string") {
    warnings.push({ message: `'tags' should be a list or comma-separated string — server will import it as []` });
  }

  if (doc.id === undefined || doc.id === null || String(doc.id).trim() === "") {
    warnings.push({ message: "no 'id' — server will generate one; a stable id keeps re-syncs idempotent if the file moves" });
  }

  return { errors, warnings, doc };
}

/**
 * Lint a set of files ([{path, content}]) with cross-file checks.
 * Returns { files: Map<path, result>, errors, warnings } where the top-level
 * arrays aggregate `{path, message, line?}` entries.
 */
function lintFiles(files) {
  const perFile = new Map();
  const errors = [];
  const warnings = [];
  const idOwners = new Map(); // id -> first path that declared it

  for (const { path, content } of files) {
    const res = lintContent(content);
    perFile.set(path, res);
    for (const e of res.errors) errors.push({ path, ...e });
    for (const w of res.warnings) warnings.push({ path, ...w });

    const id = res.doc && res.doc.id != null ? String(res.doc.id).trim() : "";
    if (id) {
      if (idOwners.has(id)) {
        errors.push({ path, message: `duplicate id '${id}' — already declared in ${idOwners.get(id)}; the later file would overwrite the earlier test` });
      } else {
        idOwners.set(id, path);
      }
    }
  }
  return { files: perFile, errors, warnings };
}

module.exports = { lintContent, lintFiles, TYPE_MAP, PRIORITY_MAP, STATUS_MAP, KNOWN_KEYS };
