"use strict";
/**
 * Thin HTTP client over the ThoroTest REST API (global fetch, Node 18+).
 * All commands go through request(); it maps transport and HTTP failures to
 * typed errors so bin/thorotest.js can translate them into exit codes.
 */

class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

class NetworkError extends Error {}

/** Extract a human message from a FastAPI error body ({detail: ...}). */
function detailOf(body) {
  if (body && typeof body === "object" && body.detail) {
    if (typeof body.detail === "string") return body.detail;
    try { return JSON.stringify(body.detail); } catch { /* fall through */ }
  }
  return null;
}

/**
 * Perform one API request. Returns { data, headers }.
 * Throws ApiError on non-2xx, NetworkError when the server is unreachable.
 */
async function request(cfg, method, apiPath, body = undefined) {
  const url = cfg.url + apiPath;
  const headers = { Accept: "application/json" };
  if (cfg.token) headers.Authorization = `Bearer ${cfg.token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    throw new NetworkError(`cannot reach ${cfg.url} — ${e.cause?.code || e.message}`);
  }

  let data = null;
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }

  if (!res.ok) {
    const msg = detailOf(data) || `${method} ${apiPath} failed with HTTP ${res.status}`;
    throw new ApiError(res.status, msg, data);
  }
  return { data, headers: res.headers };
}

module.exports = { request, ApiError, NetworkError };
