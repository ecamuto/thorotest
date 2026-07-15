"use strict";
/**
 * Resolve server URL + API token. Precedence (highest wins):
 *
 *   1. command-line flags        --url / --token
 *   2. environment variables     THOROTEST_URL / THOROTEST_TOKEN
 *   3. project config            ./.thorotest.json   (walks up to the git root)
 *   4. user config               ~/.config/thorotest/config.json
 *
 * Config files are plain JSON: { "url": "https://...", "token": "..." }.
 * Keep tokens out of project files that get committed — prefer the env var
 * or the user config for secrets.
 */
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const PROJECT_FILE = ".thorotest.json";

function readJsonIfExists(p) {
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch (e) {
    if (e.code === "ENOENT") return null;
    throw new Error(`cannot read config ${p}: ${e.message}`);
  }
}

/** Walk from cwd upward looking for .thorotest.json; stop at fs root or a .git dir boundary. */
function findProjectConfig(startDir) {
  let dir = startDir;
  for (;;) {
    const candidate = path.join(dir, PROJECT_FILE);
    const cfg = readJsonIfExists(candidate);
    if (cfg) return { cfg, path: candidate };
    const isRepoRoot = fs.existsSync(path.join(dir, ".git"));
    const parent = path.dirname(dir);
    if (isRepoRoot || parent === dir) return null;
    dir = parent;
  }
}

function userConfigPath() {
  const base = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config");
  return path.join(base, "thorotest", "config.json");
}

/**
 * Build the effective config. `flags` is the parsed CLI flags object.
 * Returns { url, token, sources: {url, token} } — `sources` names where each
 * value came from, for `status` output and error messages.
 */
function resolveConfig(flags, env = process.env, cwd = process.cwd()) {
  const project = findProjectConfig(cwd);
  const user = readJsonIfExists(userConfigPath());

  const pick = (key, flagVal) => {
    if (flagVal) return { value: flagVal, source: "flag" };
    if (env[`THOROTEST_${key.toUpperCase()}`]) {
      return { value: env[`THOROTEST_${key.toUpperCase()}`], source: "env" };
    }
    if (project && project.cfg[key]) return { value: project.cfg[key], source: project.path };
    if (user && user[key]) return { value: user[key], source: userConfigPath() };
    return { value: null, source: null };
  };

  const url = pick("url", flags.url);
  const token = pick("token", flags.token);
  return {
    url: url.value ? String(url.value).replace(/\/+$/, "") : null,
    token: token.value,
    sources: { url: url.source, token: token.source },
  };
}

function requireUrl(cfg) {
  if (!cfg.url) {
    throw new UsageError(
      "no server URL configured — pass --url, set THOROTEST_URL, or add \"url\" to .thorotest.json");
  }
}

function requireAuth(cfg) {
  requireUrl(cfg);
  if (!cfg.token) {
    throw new UsageError(
      "no API token configured — pass --token, set THOROTEST_TOKEN, or add \"token\" to ~/.config/thorotest/config.json\n" +
      "Create one in the web UI (Settings → API tokens) or with: thorotest token create --name <name>");
  }
}

class UsageError extends Error {}

module.exports = { resolveConfig, requireUrl, requireAuth, UsageError, userConfigPath, PROJECT_FILE };
