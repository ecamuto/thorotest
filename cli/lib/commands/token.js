"use strict";
/** `thorotest token create --name <name>` — mint a long-lived API token (admin only). */
const { request } = require("../api");
const { requireAuth, UsageError } = require("../config");
const { green, yellow, dim, bold, printJson } = require("../output");

async function run(cfg, flags, args) {
  const sub = args[0];
  if (sub !== "create") {
    throw new UsageError("usage: thorotest token create --name <name> [--scope <scope>]");
  }
  if (!flags.name) throw new UsageError("token create requires --name <name>");
  requireAuth(cfg);

  const { data } = await request(cfg, "POST", "/api/tokens", {
    name: flags.name,
    scope: flags.scope || "",
  });

  if (flags.json) return printJson(data), 0;

  console.log(`${green("✓")} token '${data.name}' created ${dim(`(id ${data.id})`)}`);
  console.log(`${bold(data.token)}`);
  console.error(yellow("This token is shown once — store it now (e.g. as a CI secret)."));
  return 0;
}

module.exports = { run };
