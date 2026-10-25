"use strict";
/** `thorotest run <integration-id>` — dispatch CI and wait for result import. */
const { request } = require("../api");
const { requireAuth, UsageError } = require("../config");
const { green, red, yellow, dim, bold, printJson } = require("../output");

const TERMINAL = new Set(["done", "error"]);

function positiveNumber(value, flag, fallback, { allowZero = false } = {}) {
  if (value === undefined) return fallback;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || (allowZero ? parsed < 0 : parsed <= 0)) {
    throw new UsageError(`--${flag} must be ${allowZero ? "zero or a positive" : "a positive"} number`);
  }
  return parsed;
}

function payloadFrom(flags) {
  const payload = {};
  if (flags.ref) payload.ref = flags.ref;
  if (flags.workflow) payload.workflow = flags.workflow;
  if (flags.artifact) payload.artifact = flags.artifact;
  if (flags.name) payload.run_name = flags.name;
  return payload;
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function resultShape(dispatched, job) {
  return {
    job_id: dispatched.job_id,
    integration_id: job.integration_id,
    provider: job.provider,
    workflow: job.workflow,
    ref: job.ref,
    status: job.status,
    pipeline_status: job.pipeline_status,
    external_run_id: job.external_run_id ?? job.gh_run_id ?? null,
    external_url: job.external_url ?? job.gh_run_url ?? null,
    imported: job.imported || {},
    error: job.error || null,
  };
}

async function run(cfg, flags, args) {
  requireAuth(cfg);
  if (args.length !== 1) {
    throw new UsageError("usage: thorotest run <integration-id> [--ref <ref>] [--no-wait]");
  }

  const integrationId = args[0];
  const timeoutSeconds = positiveNumber(flags.timeout, "timeout", 2100);
  const intervalSeconds = positiveNumber(flags.interval, "interval", 5, { allowZero: true });
  const encodedId = encodeURIComponent(integrationId);
  const { data: dispatched } = await request(
    cfg,
    "POST",
    `/api/integrations/${encodedId}/ci/run`,
    payloadFrom(flags),
  );

  if (flags["no-wait"]) {
    if (flags.json) printJson(dispatched);
    else {
      console.log(`${green("dispatched")} ${bold(dispatched.workflow)} on ${dispatched.ref}`);
      console.log(`${dim("job")} ${dispatched.job_id}`);
    }
    return 0;
  }

  const deadline = Date.now() + timeoutSeconds * 1000;
  let lastStatus = null;
  while (Date.now() <= deadline) {
    const { data: job } = await request(
      cfg,
      "GET",
      `/api/integrations/${encodedId}/ci/jobs/${encodeURIComponent(dispatched.job_id)}`,
    );

    if (!flags.json && job.status !== lastStatus) {
      const label = String(job.status || "queued").replaceAll("_", " ");
      process.stderr.write(`${dim("ci")} ${label}\n`);
      lastStatus = job.status;
    }

    if (TERMINAL.has(job.status)) {
      const result = resultShape(dispatched, job);
      if (flags.json) {
        printJson(result);
      } else if (job.status === "error") {
        console.error(red(`CI job failed: ${job.error || "unknown provider error"}`));
      } else {
        const stats = result.imported;
        const summary = `${stats.tests || 0} tests · ${stats.runs || 0} runs imported`;
        const pipeline = result.pipeline_status === "fail" ? red("failed") : green("passed");
        console.log(`${pipeline} ${summary}`);
        if (result.external_url) console.log(dim(result.external_url));
      }
      if (job.status === "error") return 3;
      return result.pipeline_status === "fail" ? 1 : 0;
    }

    if (intervalSeconds > 0) await sleep(intervalSeconds * 1000);
  }

  const message = `timed out after ${timeoutSeconds}s waiting for CI job ${dispatched.job_id}`;
  if (flags.json) printJson({ job_id: dispatched.job_id, status: "timeout", error: message });
  else console.error(yellow(message));
  return 3;
}

module.exports = { run, positiveNumber, payloadFrom, resultShape };
