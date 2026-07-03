// ThoroTest API client — loads live data from backend, falls back to static data.js
(function () {
  const BASE = "";  // served from same origin

  function getToken() { return localStorage.getItem("th_token"); }
  function setToken(t) { localStorage.setItem("th_token", t); }
  function clearToken() { localStorage.removeItem("th_token"); }

  function authHeaders(extra) {
    const h = { "Content-Type": "application/json", ...extra };
    const t = getToken();
    if (t) h["Authorization"] = `Bearer ${t}`;
    return h;
  }

  async function loadInitialData() {
    const res = await fetch(BASE + "/api/initial-data", { headers: authHeaders() });
    if (!res.ok) throw new Error("API unavailable");
    return res.json();
  }

  // Exposed so views making raw fetch() calls can attach the bearer token
  // without each one re-reading localStorage. GET endpoints now require auth.
  window.authHeaders = authHeaders;

  window.TH_API = {
    setToken,
    authHeaders,

    async confirmOAuthLink(pendingToken, password) {
      const res = await fetch(BASE + "/api/auth/oauth/confirm-link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pending_token: pendingToken, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Link failed");
      }
      const data = await res.json();
      if (data.status === "2fa_required") {
        return { __2fa_required: true, partialToken: data.partial_token };
      }
      setToken(data.access_token);
      return data.user;
    },

    async init() {
      try {
        const data = await loadInitialData();
        window.TH_DATA = data;
      } catch (e) {
        console.warn("[ThoroTest] API unavailable, using static data", e.message);
      }
    },

    async forgotPassword(email) {
      const res = await fetch(BASE + "/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Request failed");
      }
      return res.json();
    },

    async resetPassword(token, newPassword) {
      const res = await fetch(BASE + "/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Reset failed");
      }
    },

    async login(email, password) {
      const res = await fetch(BASE + "/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Login failed");
      }
      const data = await res.json();
      if (data.status === "2fa_required") {
        return { __2fa_required: true, partialToken: data.partial_token };
      }
      setToken(data.access_token);
      return data.user;
    },

    async verify2FA(partialToken, code) {
      const res = await fetch(BASE + "/api/auth/login/2fa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ partial_token: partialToken, code }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const e = new Error(err.detail || "Invalid code");
        e.httpStatus = res.status;
        throw e;
      }
      const data = await res.json();
      setToken(data.access_token);
      return data.user;
    },

    async get2FASetup() {
      const res = await fetch(BASE + "/api/me/2fa/setup", { headers: authHeaders() });
      if (!res.ok) { throw new Error((await res.json().catch(() => ({}))).detail || "Request failed"); }
      return res.json();
    },

    async enable2FA(pendingSecret, totpCode) {
      const res = await fetch(BASE + "/api/me/2fa/enable", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ pending_secret: pendingSecret, totp_code: totpCode }),
      });
      if (!res.ok) { throw new Error((await res.json().catch(() => ({}))).detail || "Request failed"); }
      return res.json();
    },

    async disable2FA(totpCode) {
      const res = await fetch(BASE + "/api/me/2fa/disable", {
        method: "DELETE",
        headers: authHeaders(),
        body: JSON.stringify({ totp_code: totpCode }),
      });
      if (!res.ok) { throw new Error((await res.json().catch(() => ({}))).detail || "Request failed"); }
    },

    async regenerate2FACodes(totpCode) {
      const res = await fetch(BASE + "/api/me/2fa/recovery-codes/regenerate", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ totp_code: totpCode }),
      });
      if (!res.ok) { throw new Error((await res.json().catch(() => ({}))).detail || "Request failed"); }
      return res.json();
    },

    async get2FACount() {
      const res = await fetch(BASE + "/api/me/2fa/recovery-codes/count", { headers: authHeaders() });
      if (!res.ok) { throw new Error((await res.json().catch(() => ({}))).detail || "Request failed"); }
      return res.json();
    },

    async logout() {
      // Capture auth headers before clearing so the audit logout event still
      // identifies the actor, then clear the token synchronously so callers
      // (and the UI) never observe a stale token after logout is invoked.
      const headers = authHeaders();
      clearToken();
      try {
        await fetch(BASE + "/api/auth/logout", {
          method: "POST",
          headers,
        });
      } catch (_) {
        // fire-and-forget — token already cleared regardless of server response
      }
    },

    async getCurrentUser() {
      const t = getToken();
      if (!t) return null;
      const res = await fetch(BASE + "/api/me", { headers: authHeaders() });
      if (!res.ok) { clearToken(); return null; }
      return res.json();
    },

    async getTest(id) {
      const res = await fetch(BASE + `/api/tests/${id}`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Test not found");
      const t = await res.json();
      return { ...t, folder: t.folder_id, updated: t.updated_at, lastRun: t.last_run_at };
    },

    async updateTestStatus(id, status) {
      const res = await fetch(BASE + `/api/tests/${id}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error("Update failed");
      return res.json();
    },

    async createTest(payload) {
      const res = await fetch(BASE + "/api/tests", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Create failed");
      return res.json();
    },

    async getRun(id) {
      const res = await fetch(BASE + `/api/runs/${id}`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Run not found");
      return res.json();
    },

    async createRun(payload) {
      const res = await fetch(BASE + "/api/runs", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Create run failed");
      return res.json();
    },

    async updateRunStatus(id, status) {
      const res = await fetch(BASE + `/api/runs/${id}/status?status=${encodeURIComponent(status)}`, {
        method: "PATCH",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Status update failed");
      return res.json();
    },

    async deleteTest(id) {
      const res = await fetch(BASE + `/api/tests/${id}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok && res.status !== 204) throw new Error("Delete failed");
    },

    async bulkTests(action, ids, payload) {
      const res = await fetch(BASE + "/api/tests/bulk", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ action, ids, payload }),
      });
      if (!res.ok) throw new Error("Bulk action failed");
      return res.json();
    },

    connectRunWS(runId) {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      return new WebSocket(`${proto}://${location.host}/ws/runs/${runId}`);
    },

    async getTestHistory(id) {
      const res = await fetch(BASE + `/api/tests/${id}/history`, { headers: authHeaders() });
      if (!res.ok) throw new Error("History fetch failed");
      return res.json();
    },

    async getRuns() {
      const res = await fetch(BASE + "/api/runs", { headers: authHeaders() });
      if (!res.ok) throw new Error("Runs fetch failed");
      return res.json();
    },

    async getTestDefects(id) {
      const res = await fetch(BASE + `/api/tests/${id}/defects`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Defects fetch failed");
      return res.json();
    },

    async getDefects(filters = {}) {
      const params = new URLSearchParams();
      if (filters.status && filters.status !== "all") params.set("status", filters.status);
      if (filters.severity && filters.severity !== "all") params.set("severity", filters.severity);
      if (filters.test_id) params.set("test_id", filters.test_id);
      if (filters.search) params.set("search", filters.search);
      const qs = params.toString() ? `?${params}` : "";
      const res = await fetch(BASE + `/api/defects${qs}`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Defects fetch failed");
      return res.json();
    },

    async getDefect(id) {
      const res = await fetch(BASE + `/api/defects/${id}`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Defect not found");
      return res.json();
    },

    async createDefect(payload) {
      const res = await fetch(BASE + "/api/defects", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Create defect failed");
      return res.json();
    },

    async updateDefect(id, payload) {
      const res = await fetch(BASE + `/api/defects/${id}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Update defect failed");
      return res.json();
    },

    async deleteDefect(id) {
      const res = await fetch(BASE + `/api/defects/${id}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok && res.status !== 204) throw new Error("Delete defect failed");
    },

    async getRunDefects(runId) {
      const res = await fetch(BASE + `/api/runs/${runId}/defects`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Run defects fetch failed");
      return res.json();
    },

    async getTestComments(id) {
      const res = await fetch(BASE + `/api/tests/${id}/comments`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Comments fetch failed");
      return res.json();
    },

    async addComment(id, who, text) {
      const res = await fetch(BASE + `/api/tests/${id}/comments`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ who, text }),
      });
      if (!res.ok) throw new Error("Add comment failed");
      return res.json();
    },

    async getUsers() {
      const res = await fetch(BASE + "/api/users", { headers: authHeaders() });
      if (!res.ok) throw new Error("Users fetch failed");
      return res.json();
    },

    async gql(query, variables = {}) {
      const res = await fetch(BASE + "/graphql", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ query, variables }),
      });
      const json = await res.json();
      if (json.errors) throw new Error(json.errors[0].message);
      return json.data;
    },

    async updateProfile(data) {
      const res = await fetch(BASE + "/api/me", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify(data),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Update failed"); }
      return res.json();
    },

    async changePassword(current_password, new_password) {
      const res = await fetch(BASE + "/api/me/password", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ current_password, new_password }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Password change failed"); }
    },

    async getProjects() {
      const res = await fetch(BASE + "/api/projects", { headers: authHeaders() });
      if (!res.ok) throw new Error(`Failed to load projects (${res.status})`);
      return res.json();
    },

    async createProject(payload) {
      const res = await fetch(BASE + "/api/projects", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Create failed"); }
      return res.json();
    },

    async updateProject(id, payload) {
      const res = await fetch(BASE + `/api/projects/${id}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Update failed"); }
      return res.json();
    },

    async deleteProject(id) {
      const res = await fetch(BASE + `/api/projects/${id}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok && res.status !== 204) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Delete failed"); }
    },

    async getCategories() {
      const res = await fetch(BASE + "/api/categories", { headers: authHeaders() });
      if (!res.ok) throw new Error(`Failed to load categories (${res.status})`);
      return res.json();
    },

    async createCategory(payload) {
      const res = await fetch(BASE + "/api/categories", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Create failed"); }
      return res.json();
    },

    async updateCategory(id, payload) {
      const res = await fetch(BASE + `/api/categories/${id}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Update failed"); }
      return res.json();
    },

    async deleteCategory(id) {
      const res = await fetch(BASE + `/api/categories/${id}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok && res.status !== 204) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Delete failed"); }
    },

    async getFolders() {
      const res = await fetch(BASE + "/api/folders", { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load folders");
      return res.json();
    },

    async createFolder(payload) {
      const res = await fetch(BASE + "/api/folders", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Create failed"); }
      return res.json();
    },

    async updateFolder(id, payload) {
      const res = await fetch(BASE + `/api/folders/${id}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Update failed"); }
      return res.json();
    },

    async deleteFolder(id) {
      const res = await fetch(BASE + `/api/folders/${id}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok && res.status !== 204) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Delete failed"); }
    },

    async getIntegrations() {
      const res = await fetch(BASE + "/api/integrations", { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load integrations");
      return res.json();
    },

    async createIntegration(payload) {
      const res = await fetch(BASE + "/api/integrations", {
        method: "POST", headers: authHeaders(), body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Create failed"); }
      return res.json();
    },

    async updateIntegration(id, payload) {
      const res = await fetch(BASE + `/api/integrations/${id}`, {
        method: "PATCH", headers: authHeaders(), body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Update failed"); }
      return res.json();
    },

    async deleteIntegration(id) {
      const res = await fetch(BASE + `/api/integrations/${id}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok && res.status !== 204) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Delete failed"); }
    },

    async syncIntegration(id) {
      const res = await fetch(BASE + `/api/integrations/${id}/sync`, { method: "POST", headers: authHeaders() });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Sync failed"); }
      return res.json();
    },

    async getTokens() {
      const res = await fetch(BASE + "/api/tokens", { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load tokens");
      return res.json();
    },

    async createToken(payload) {
      const res = await fetch(BASE + "/api/tokens", {
        method: "POST", headers: authHeaders(), body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Create failed"); }
      return res.json();
    },

    async revokeToken(id) {
      const res = await fetch(BASE + `/api/tokens/${id}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok && res.status !== 204) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Revoke failed"); }
    },

    async getWebhooks() {
      const res = await fetch(BASE + "/api/webhooks", { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load webhooks");
      return res.json();
    },

    async createWebhook(payload) {
      const res = await fetch(BASE + "/api/webhooks", {
        method: "POST", headers: authHeaders(), body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Create failed"); }
      return res.json();
    },

    async updateWebhook(id, payload) {
      const res = await fetch(BASE + `/api/webhooks/${id}`, {
        method: "PATCH", headers: authHeaders(), body: JSON.stringify(payload),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Update failed"); }
      return res.json();
    },

    async deleteWebhook(id) {
      const res = await fetch(BASE + `/api/webhooks/${id}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok && res.status !== 204) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Delete failed"); }
    },

    async testWebhook(id) {
      const res = await fetch(BASE + `/api/webhooks/${id}/test`, {
        method: "POST", headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Test request failed");
      return res.json();
    },

    async getFavorites() {
      const res = await fetch(BASE + "/api/favorites", { headers: authHeaders() });
      if (!res.ok) return [];
      return res.json();
    },

    async addFavorite(folderId) {
      const res = await fetch(BASE + "/api/favorites", {
        method: "POST", headers: authHeaders(), body: JSON.stringify({ folder_id: folderId }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Failed"); }
      return res.json();
    },

    async removeFavorite(folderId) {
      const res = await fetch(BASE + `/api/favorites/${folderId}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok && res.status !== 204) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Failed"); }
    },

    async getTestSteps(testId) {
      const res = await fetch(BASE + `/api/tests/${testId}/steps`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Steps fetch failed");
      return res.json();
    },

    async replaceTestSteps(testId, steps) {
      // steps: [{action: string, expected_result: string|null}]
      const res = await fetch(BASE + `/api/tests/${testId}/steps`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify(steps),
      });
      if (!res.ok) throw new Error("Steps save failed");
      return res.json();
    },

    async getStepResults(runId, caseId) {
      const res = await fetch(BASE + `/api/runs/${runId}/cases/${caseId}/steps`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Step results fetch failed");
      return res.json();
    },

    async updateStepResult(runId, caseId, stepId, payload) {
      // payload: { status: string, actual_result?: string }
      const res = await fetch(BASE + `/api/runs/${runId}/cases/${caseId}/steps/${stepId}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Step result update failed");
      return res.json();
    },

    async getAttachments(entityType, entityId) {
      const params = new URLSearchParams({ entity_type: entityType, entity_id: String(entityId) });
      const res = await fetch(BASE + `/api/attachments?${params}`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Attachments fetch failed");
      return res.json();
    },

    async uploadAttachment(entityType, entityId, file) {
      // IMPORTANT: Do NOT set Content-Type — browser must set multipart boundary automatically
      const fd = new FormData();
      fd.append("entity_type", entityType);
      fd.append("entity_id", String(entityId));
      fd.append("file", file);
      const token = localStorage.getItem("th_token");
      const res = await fetch(BASE + "/api/attachments", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) throw new Error("Upload failed");
      return res.json();
    },

    async deleteAttachment(attId) {
      const res = await fetch(BASE + `/api/attachments/${attId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok && res.status !== 204) throw new Error("Delete attachment failed");
    },

    async listAdminUsers() {
      const resp = await fetch(BASE + "/api/admin/users", { headers: authHeaders() });
      if (!resp.ok) throw new Error(await resp.text());
      return resp.json();
    },

    async createAdminUser(payload) {
      const resp = await fetch(BASE + "/api/admin/users", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(await resp.text());
      return resp.json();
    },

    async updateUserRole(userId, role) {
      const resp = await fetch(BASE + `/api/admin/users/${userId}/role`, {
        method: "PATCH",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      return resp.json();
    },

    async deleteAdminUser(userId) {
      const resp = await fetch(BASE + `/api/admin/users/${userId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!resp.ok) throw new Error(await resp.text());
    },

    async retestRun(runId) {
      const res = await fetch(BASE + `/api/runs/${runId}/retest`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Retest failed");
      return res.json();
    },

    async assignCase(runId, caseId, assignedTo) {
      const res = await fetch(BASE + `/api/runs/${runId}/cases/${caseId}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify({ assigned_to: assignedTo }),
      });
      if (!res.ok) throw new Error("Assign failed");
      return res.json();
    },

    async getMyCases() {
      const res = await fetch(BASE + "/api/runs/my-cases", { headers: authHeaders() });
      if (!res.ok) throw new Error("My cases fetch failed");
      return res.json();
    },

    async generateTests(payload) {
      const res = await fetch(BASE + "/api/ai/generate-tests", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (res.status === 429) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Rate limit exceeded: try again in an hour"); }
      if (res.status === 503) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "AI not configured"); }
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "AI request failed"); }
      return res.json();
    },

    async suggestEdgeCases(payload) {
      const res = await fetch(BASE + "/api/ai/suggest-edge-cases", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (res.status === 429) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Rate limit exceeded: try again in an hour"); }
      if (res.status === 503) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "AI not configured"); }
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "AI request failed"); }
      return res.json();
    },

    async analyzeFlaky(payload) {
      const res = await fetch(BASE + "/api/ai/analyze-flaky", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (res.status === 429) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "Rate limit exceeded: try again in an hour"); }
      if (res.status === 503) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "AI not configured"); }
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "AI request failed"); }
      return res.json();
    },

    async exportRunCSV(runId) {
      const res = await fetch(BASE + `/api/runs/${runId}/export?format=csv`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `run-${runId}-export.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },

    async exportRunPDF(runId) {
      const res = await fetch(BASE + `/api/runs/${runId}/export?format=pdf`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `run-${runId}-report.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },

    async exportTestsCSV(folderId) {
      const params = new URLSearchParams({ format: "csv" });
      if (folderId) params.set("folder_id", folderId);
      const res = await fetch(BASE + `/api/tests/export?${params}`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "tests-export.csv";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },

    async getNotifications(limit = 20) {
      const res = await fetch(`${BASE}/api/notifications?limit=${limit}`, { headers: authHeaders() });
      if (!res.ok) return [];
      return res.json();
    },

    async markNotificationRead(id) {
      const res = await fetch(`${BASE}/api/notifications/${id}/read`, {
        method: "PATCH",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Mark read failed");
      return res.json();
    },

    async markAllNotificationsRead() {
      const res = await fetch(`${BASE}/api/notifications/mark-all-read`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Mark all read failed");
      return res.json();
    },

    async deleteNotification(id) {
      const res = await fetch(`${BASE}/api/notifications/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok && res.status !== 204) throw new Error("Delete notification failed");
    },

    async getNotificationConfig() {
      const res = await fetch(`${BASE}/api/notifications/config`, { headers: authHeaders() });
      if (!res.ok) return {};
      return res.json();
    },

    async putNotificationConfig(payload) {
      const res = await fetch(`${BASE}/api/notifications/config`, {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Config update failed");
      return res.json();
    },

    connectNotifWS(token) {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      return new WebSocket(`${proto}://${location.host}/ws/notifications?token=${encodeURIComponent(token)}`);
    },

    async getAuditLog({ start_date, end_date, page = 1, page_size = 50 } = {}) {
      const params = new URLSearchParams();
      if (start_date) params.set("start_date", start_date);
      if (end_date)   params.set("end_date", end_date);
      params.set("page", page);
      params.set("page_size", page_size);
      const res = await fetch(BASE + "/api/audit-log?" + params, { headers: authHeaders() });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail || "Audit log fetch failed");
      }
      return res.json();
    },
  };
})();
