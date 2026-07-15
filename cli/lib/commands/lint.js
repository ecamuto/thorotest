"use strict";
/** `thorotest lint <paths…>` — validate YAML test files locally, no server needed. */
const { collectYamlFiles } = require("../files");
const { lintFiles } = require("../lint");
const { red, green, yellow, dim, printJson } = require("../output");
const { UsageError } = require("../config");

function run(_cfg, flags, args) {
  if (args.length === 0) throw new UsageError("usage: thorotest lint <file|dir> [...]");

  const files = collectYamlFiles(args);
  if (files.length === 0) throw new UsageError(`no .yml/.yaml files found under: ${args.join(", ")}`);

  const { errors, warnings } = lintFiles(files);

  if (flags.json) {
    printJson({
      files: files.length,
      errors: errors.map((e) => ({ path: e.path, line: e.line ?? null, message: e.message })),
      warnings: warnings.map((w) => ({ path: w.path, line: w.line ?? null, message: w.message })),
      ok: errors.length === 0,
    });
    return errors.length === 0 ? 0 : 1;
  }

  for (const e of errors) {
    const loc = e.line ? `${e.path}:${e.line}` : e.path;
    console.error(`${red("error")}   ${loc}: ${e.message}`);
  }
  for (const w of warnings) {
    const loc = w.line ? `${w.path}:${w.line}` : w.path;
    console.error(`${yellow("warning")} ${loc}: ${w.message}`);
  }

  const summary = `${files.length} file${files.length === 1 ? "" : "s"}, ` +
    `${errors.length} error${errors.length === 1 ? "" : "s"}, ` +
    `${warnings.length} warning${warnings.length === 1 ? "" : "s"}`;
  if (errors.length === 0) {
    console.log(`${green("✓")} ${summary}`);
    return 0;
  }
  console.error(`${red("✗")} ${summary}`);
  return 1;
}

module.exports = { run };
