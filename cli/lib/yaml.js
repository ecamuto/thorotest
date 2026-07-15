"use strict";
/**
 * Minimal YAML parser for ThoroTest "test as code" files.
 *
 * The documented file shape is a flat mapping of scalars plus one optional
 * list (`tags`), so this parser deliberately supports only that subset:
 *
 *   - `key: scalar` with plain, 'single' or "double" quoted values
 *   - inline lists  `tags: [smoke, payment]`
 *   - block lists   `tags:` followed by `  - item` lines
 *   - full-line and trailing `# comments`, blank lines, a leading `---`
 *
 * Anything outside the subset (nested mappings, block scalars `|`/`>`,
 * anchors, multiple documents) raises a ParseError with a line number and a
 * hint, so `thorotest lint` fails loudly instead of guessing. Server-side
 * validation (`thorotest sync --dry-run`) accepts full YAML and is the
 * escape hatch for exotic files.
 *
 * Plain scalars are typed like YAML 1.1 core: true/false, null/~, numbers.
 */

class ParseError extends Error {
  constructor(message, line) {
    super(message);
    this.line = line; // 1-based line number when known; callers render "path:line"
  }
}

const KEY_RE = /^([A-Za-z0-9_.-]+):(.*)$/;

/** Strip a trailing ` # comment` from an unquoted scalar chunk. */
function stripTrailingComment(s) {
  let inS = false, inD = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === "'" && !inD) inS = !inS;
    else if (c === '"' && !inS) inD = !inD;
    else if (c === "#" && !inS && !inD && (i === 0 || s[i - 1] === " " || s[i - 1] === "\t")) {
      return s.slice(0, i);
    }
  }
  return s;
}

function typePlainScalar(raw) {
  const s = raw.trim();
  if (s === "" ) return null;
  if (/^(true|True|TRUE)$/.test(s)) return true;
  if (/^(false|False|FALSE)$/.test(s)) return false;
  if (/^(null|Null|NULL|~)$/.test(s)) return null;
  if (/^[+-]?\d+$/.test(s)) return parseInt(s, 10);
  if (/^[+-]?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?$/.test(s)) return parseFloat(s);
  return s;
}

function unescapeDouble(s, line) {
  let out = "";
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c !== "\\") { out += c; continue; }
    const n = s[++i];
    if (n === undefined) throw new ParseError("dangling backslash in double-quoted string", line);
    const map = { n: "\n", t: "\t", r: "\r", '"': '"', "\\": "\\", "0": "\0" };
    if (!(n in map)) throw new ParseError(`unsupported escape \\${n} in double-quoted string`, line);
    out += map[n];
  }
  return out;
}

/** Parse one scalar token (possibly quoted). Returns the JS value. */
function parseScalar(raw, line) {
  const s = raw.trim();
  if (s.startsWith('"')) {
    if (s.length < 2 || !s.endsWith('"')) throw new ParseError("unterminated double-quoted string", line);
    return unescapeDouble(s.slice(1, -1), line);
  }
  if (s.startsWith("'")) {
    if (s.length < 2 || !s.endsWith("'")) throw new ParseError("unterminated single-quoted string", line);
    return s.slice(1, -1).replace(/''/g, "'");
  }
  if (s.startsWith("|") || s.startsWith(">")) {
    throw new ParseError("block scalars (| / >) are not supported by local lint — use `thorotest sync --dry-run` for server-side validation", line);
  }
  if (s.startsWith("&") || s.startsWith("*")) {
    throw new ParseError("YAML anchors/aliases are not supported", line);
  }
  if (s.startsWith("{")) {
    throw new ParseError("nested inline mappings are not supported (flat schema expected)", line);
  }
  return typePlainScalar(s);
}

/** Split the inside of an inline list on top-level commas, respecting quotes. */
function parseInlineList(raw, line) {
  const inner = raw.trim().slice(1, -1).trim();
  if (inner === "") return [];
  const items = [];
  let cur = "", inS = false, inD = false;
  for (const c of inner) {
    if (c === "'" && !inD) { inS = !inS; cur += c; }
    else if (c === '"' && !inS) { inD = !inD; cur += c; }
    else if (c === "," && !inS && !inD) { items.push(cur); cur = ""; }
    else if ((c === "[" || c === "{") && !inS && !inD) {
      throw new ParseError("nested collections inside a list are not supported", line);
    }
    else cur += c;
  }
  if (inS || inD) throw new ParseError("unterminated quote in inline list", line);
  items.push(cur);
  return items.map((it) => parseScalar(it, line));
}

/**
 * Parse a single YAML test document.
 * Returns a plain object. Throws ParseError on anything outside the subset.
 */
function parse(text) {
  if (typeof text !== "string") throw new ParseError("input must be a string");
  const lines = text.split(/\r\n|\r|\n/);
  const doc = {};
  let sawDocStart = false;
  let sawAnyKey = false;
  let pendingListKey = null; // key whose value is being built from `- item` lines

  for (let idx = 0; idx < lines.length; idx++) {
    const lineNo = idx + 1;
    const rawLine = lines[idx];
    const noComment = stripTrailingComment(rawLine);
    if (noComment.trim() === "") continue;

    if (/^\t/.test(rawLine)) {
      throw new ParseError("tabs are not allowed for YAML indentation", lineNo);
    }

    const trimmed = noComment.trim();

    if (trimmed === "---") {
      if (sawDocStart || sawAnyKey) {
        throw new ParseError("multiple YAML documents are not supported (one test per file)", lineNo);
      }
      sawDocStart = true;
      continue;
    }
    if (trimmed === "...") continue;

    const indented = /^\s/.test(noComment);

    // Block list item under a pending key.
    if (indented && trimmed.startsWith("- ") || (indented && trimmed === "-")) {
      if (!pendingListKey) {
        throw new ParseError("list item without a preceding `key:` line", lineNo);
      }
      const itemRaw = trimmed === "-" ? "" : trimmed.slice(2);
      if (KEY_RE.test(itemRaw.trim()) && /:\s/.test(itemRaw + " ")) {
        // `- key: value` — a mapping inside a list.
        throw new ParseError("mappings inside lists are not supported (flat schema expected)", lineNo);
      }
      doc[pendingListKey].push(parseScalar(itemRaw, lineNo));
      continue;
    }

    if (indented) {
      throw new ParseError("nested mappings are not supported (flat schema expected)", lineNo);
    }

    if (trimmed.startsWith("- ")) {
      throw new ParseError("top-level YAML must be a mapping (key: value), not a list", lineNo);
    }

    const m = trimmed.match(KEY_RE);
    if (!m) {
      throw new ParseError(`expected \`key: value\`, got: ${trimmed.slice(0, 60)}`, lineNo);
    }
    const key = m[1];
    const rest = m[2];

    if (Object.prototype.hasOwnProperty.call(doc, key)) {
      throw new ParseError(`duplicate key '${key}'`, lineNo);
    }
    sawAnyKey = true;
    // A previous `key:` with no list items following was an empty value.
    if (pendingListKey && doc[pendingListKey].length === 0) {
      doc[pendingListKey] = null;
    }
    pendingListKey = null;

    const value = rest.trim();
    if (value === "") {
      // Either an empty value or a block list follows.
      doc[key] = [];
      pendingListKey = key;
      continue;
    }
    if (value.startsWith("[")) {
      if (!value.endsWith("]")) throw new ParseError("unterminated inline list", lineNo);
      doc[key] = parseInlineList(value, lineNo);
      continue;
    }
    doc[key] = parseScalar(value, lineNo);
  }

  // A key left with an empty block list that never got items was an empty value.
  if (pendingListKey && doc[pendingListKey].length === 0) {
    doc[pendingListKey] = null;
  }

  if (!sawAnyKey) throw new ParseError("empty YAML document (expected a `key: value` mapping)");
  return doc;
}

module.exports = { parse, ParseError };
