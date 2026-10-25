// Route-level asset loader for the classic-script frontend.
//
// Views still publish their public components on `window`, so they can be
// loaded incrementally without a risky all-at-once ESM migration.  The
// production build stamps this file with ?v=<hash>; that same immutable cache
// key is propagated to every dynamically inserted view script.
(function () {
  "use strict";

  const ownScript = document.currentScript;
  const baseUrl = new URL(".", ownScript?.src || window.location.href);
  const version = ownScript ? new URL(ownScript.src).search : "";
  const loaded = new Set();
  const pending = new Map();

  const routes = Object.freeze({
    overview: [],
    library: ["views/view-library.js"],
    "test-detail": ["views/view-requirements.js", "views/view-test-detail.js"],
    runs: ["views/view-runs.js"],
    "run-detail": ["views/view-runs.js"],
    pipelines: ["views/view-misc.js"],
    insights: ["views/view-misc.js"],
    defects: ["views/view-defects.js"],
    requirements: ["views/view-requirements.js"],
    ai: ["views/view-config.js"],
    integrations: ["views/view-config.js"],
    docs: ["views/view-docs.js"],
    import: ["views/view-import.js"],
    settings: ["views/view-settings.js"],
    admin: ["views/view-audit-log.js", "views/view-admin.js"],
    "my-work": ["views/view-my-work.js"],
  });

  function loadScript(path) {
    if (loaded.has(path)) return Promise.resolve();
    if (pending.has(path)) return pending.get(path);

    const promise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = new URL(path, baseUrl).href + version;
      script.async = true;
      script.dataset.routeModule = path;
      script.onload = () => {
        loaded.add(path);
        pending.delete(path);
        resolve();
      };
      script.onerror = () => {
        pending.delete(path);
        script.remove();
        reject(new Error(`Could not load ${path}`));
      };
      document.head.appendChild(script);
    });
    pending.set(path, promise);
    return promise;
  }

  async function load(view) {
    const scripts = routes[view] || routes.overview;
    // Preserve dependency order for routes such as test-detail and admin.
    for (const path of scripts) await loadScript(path);
  }

  window.TH_ROUTE_LOADER = Object.freeze({ load, routes });
})();
