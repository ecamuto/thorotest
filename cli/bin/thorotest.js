#!/usr/bin/env node
"use strict";
/**
 * thorotest — command-line client for ThoroTest.
 *
 * Exit codes:
 *   0  success
 *   1  lint/sync validation failures (bad YAML, skipped files)
 *   2  usage error (unknown command, missing argument, missing config)
 *   3  server or network error (5xx, unreachable host)
 *   4  authentication/authorization error (401/403)
 */
const { resolveConfig, UsageError } = require("../lib/config");
const { ApiError, NetworkError } = require("../lib/api");
const { red, dim } = require("../lib/output");

const VERSION = require("../package.json").version;

const COMMANDS = {
  status: () => require("../lib/commands/status"),
  lint: () => require("../lib/commands/lint"),
  sync: () => require("../lib/commands/sync"),
  token: () => require("../lib/commands/token"),
};

// Flags that take a value; everything else is boolean.
const VALUE_FLAGS = new Set(["url", "token", "name", "scope", "ref", "source"]);

const HELP = `thorotest ${VERSION} — command-line client for ThoroTest

Usage
  thorotest <command> [options]

Commands
  status                      Server health, current user, test & run counts
  lint <file|dir> [...]       Validate YAML test files locally (offline)
  sync <file|dir> [...]       Push YAML test definitions to the server
  token create --name <name>  Mint a long-lived API token (admin only)

Global options
  --url <url>       Server base URL           (env THOROTEST_URL)
  --token <token>   API token                 (env THOROTEST_TOKEN)
  --json            Machine-readable output
  -h, --help        Show this help
  -v, --version     Show version

Sync options
  --dry-run         Validate on the server and report changes without saving
  --ref <label>     Label recorded as source_ref (default: cli)
  --source <src>    Source identity, must start with cli:// (default: cli://local)
  --force           Push even when local lint finds errors (server skips bad files)

Config resolution: flags > env > ./.thorotest.json > ~/.config/thorotest/config.json
Docs: docs/cli.md`;

/** Parse argv into { command, args, flags }. */
function parseArgv(argv) {
  const flags = {};
  const args = [];
  let command = null;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-h" || a === "--help") flags.help = true;
    else if (a === "-v" || a === "--version") flags.version = true;
    else if (a.startsWith("--")) {
      const eq = a.indexOf("=");
      if (eq !== -1) {
        flags[a.slice(2, eq)] = a.slice(eq + 1);
      } else {
        const name = a.slice(2);
        if (VALUE_FLAGS.has(name)) {
          const val = argv[++i];
          if (val === undefined) throw new UsageError(`--${name} requires a value`);
          flags[name] = val;
        } else {
          flags[name] = true;
        }
      }
    } else if (!command) command = a;
    else args.push(a);
  }
  return { command, args, flags };
}

async function main() {
  let parsed;
  try {
    parsed = parseArgv(process.argv.slice(2));
  } catch (e) {
    console.error(red(`error: ${e.message}`));
    return 2;
  }
  const { command, args, flags } = parsed;

  if (flags.version) return console.log(VERSION), 0;
  if (flags.help || !command) return console.log(HELP), command ? 0 : 2;

  const load = COMMANDS[command];
  if (!load) {
    console.error(red(`error: unknown command '${command}'`) + dim("\nRun `thorotest --help` for usage."));
    return 2;
  }

  try {
    const cfg = resolveConfig(flags);
    return await load().run(cfg, flags, args);
  } catch (e) {
    if (e instanceof UsageError) {
      console.error(red(`error: ${e.message}`));
      return 2;
    }
    if (e instanceof ApiError) {
      console.error(red(`error: ${e.message}`) + dim(` (HTTP ${e.status})`));
      if (e.status === 401) console.error(dim("Check THOROTEST_TOKEN — the token may be revoked or expired."));
      if (e.status === 403) console.error(dim("Your role does not allow this operation."));
      return e.status === 401 || e.status === 403 ? 4 : 3;
    }
    if (e instanceof NetworkError) {
      console.error(red(`error: ${e.message}`));
      return 3;
    }
    console.error(red(`error: ${e.message}`));
    return 2;
  }
}

main().then((code) => process.exit(code));
