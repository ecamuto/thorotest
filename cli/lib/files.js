"use strict";
/** Collect YAML test files from CLI path arguments. */
const fs = require("node:fs");
const path = require("node:path");

const YAML_EXT = new Set([".yml", ".yaml"]);
const SKIP_DIRS = new Set(["node_modules", ".git", "dist", "venv", "__pycache__"]);

/**
 * Expand a list of file/directory paths into [{path, content}].
 * Directories are walked recursively for *.yml / *.yaml; `path` in the result
 * is posix-style and relative to `cwd` (used as the server-side source_path,
 * so it must be stable across machines).
 * Throws Error when an explicit argument does not exist or a named file is
 * not a YAML file.
 */
function collectYamlFiles(args, cwd = process.cwd()) {
  const found = [];
  const seen = new Set();

  const add = (abs) => {
    const rel = path.relative(cwd, abs).split(path.sep).join("/");
    const key = rel || path.basename(abs);
    if (seen.has(key)) return;
    seen.add(key);
    found.push({ path: key.startsWith("..") ? abs.split(path.sep).join("/") : key, content: fs.readFileSync(abs, "utf8") });
  };

  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name) && !entry.name.startsWith(".")) walk(path.join(dir, entry.name));
      } else if (entry.isFile() && YAML_EXT.has(path.extname(entry.name).toLowerCase())) {
        add(path.join(dir, entry.name));
      }
    }
  };

  for (const arg of args) {
    const abs = path.resolve(cwd, arg);
    let st;
    try {
      st = fs.statSync(abs);
    } catch {
      throw new Error(`no such file or directory: ${arg}`);
    }
    if (st.isDirectory()) {
      walk(abs);
    } else if (YAML_EXT.has(path.extname(abs).toLowerCase())) {
      add(abs);
    } else {
      throw new Error(`not a YAML file: ${arg}`);
    }
  }
  return found;
}

module.exports = { collectYamlFiles };
