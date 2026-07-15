"use strict";
/** `thorotest sync <paths…>` — push local YAML test definitions to the server. */
const { request } = require("../api");
const { collectYamlFiles } = require("../files");
const { lintFiles } = require("../lint");
const { requireAuth, UsageError } = require("../config");
const { red, green, yellow, dim, printJson } = require("../output");

async function run(cfg, flags, args) {
  requireAuth(cfg);
  if (args.length === 0) throw new UsageError("usage: thorotest sync <file|dir> [...] [--dry-run] [--ref <label>] [--source <cli://...>] [--force]");

  const files = collectYamlFiles(args);
  if (files.length === 0) throw new UsageError(`no .yml/.yaml files found under: ${args.join(", ")}`);

  // Local lint gate: refuse to push files the server would skip, unless --force.
  const { errors } = lintFiles(files);
  if (errors.length > 0 && !flags.force) {
    for (const e of errors) {
      const loc = e.line ? `${e.path}:${e.line}` : e.path;
      console.error(`${red("error")} ${loc}: ${e.message}`);
    }
    console.error(`${red("✗")} ${errors.length} lint error${errors.length === 1 ? "" : "s"} — fix them or pass --force to let the server skip invalid files`);
    return 1;
  }

  const payload = {
    files,
    ref: flags.ref || "cli",
    source: flags.source || "cli://local",
    dry_run: Boolean(flags["dry-run"]),
  };
  const { data: stats } = await request(cfg, "POST", "/api/sync/yaml", payload);

  if (flags.json) {
    printJson(stats);
    return stats.skipped > 0 ? 1 : 0;
  }

  const label = stats.dry_run ? yellow("dry run — nothing persisted") : green("synced");
  console.log(`${label}  ${stats.files} file${stats.files === 1 ? "" : "s"}: ` +
    `${stats.created} created, ${stats.updated} updated, ${stats.skipped} skipped`);
  for (const w of stats.warnings || []) {
    console.error(`${yellow("skipped")} ${w}`);
  }
  return stats.skipped > 0 ? 1 : 0;
}

module.exports = { run };
