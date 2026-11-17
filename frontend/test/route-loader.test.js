"use strict";

const { afterEach, test } = require("node:test");
const assert = require("node:assert/strict");

const MODULE = require.resolve("../route-loader.js");

function loadRouteLoader() {
  const appended = [];
  const currentScript = {
    src: "https://thorotest.example/assets/route-loader.js?v=release-hash",
  };

  global.window = { location: { href: "https://thorotest.example/#/overview" } };
  global.document = {
    currentScript,
    createElement(tag) {
      assert.equal(tag, "script");
      return {
        dataset: {},
        removed: false,
        remove() { this.removed = true; },
      };
    },
    head: {
      appendChild(script) { appended.push(script); },
    },
  };

  delete require.cache[MODULE];
  require(MODULE);
  return { loader: window.TH_ROUTE_LOADER, appended };
}

afterEach(() => {
  delete require.cache[MODULE];
  delete global.window;
  delete global.document;
});

test("exposes immutable routes and treats unknown views as overview", async () => {
  const { loader, appended } = loadRouteLoader();
  assert(Object.isFrozen(loader));
  assert(Object.isFrozen(loader.routes));
  assert.deepEqual(loader.routes.library, ["views/view-library.js"]);
  await loader.load("overview");
  await loader.load("unknown-view");
  assert.equal(appended.length, 0);
});

test("deduplicates pending and loaded route scripts", async () => {
  const { loader, appended } = loadRouteLoader();
  const first = loader.load("library");
  const second = loader.load("library");

  assert.equal(appended.length, 1);
  assert.equal(appended[0].async, true);
  assert.equal(appended[0].dataset.routeModule, "views/view-library.js");
  assert.equal(
    appended[0].src,
    "https://thorotest.example/assets/views/view-library.js?v=release-hash",
  );
  appended[0].onload();
  await Promise.all([first, second]);

  await loader.load("library");
  assert.equal(appended.length, 1);
});

test("removes failed scripts and permits a retry", async () => {
  const { loader, appended } = loadRouteLoader();
  const failed = loader.load("defects");
  assert.equal(appended.length, 1);
  appended[0].onerror();
  await assert.rejects(failed, /Could not load views\/view-defects\.js/);
  assert.equal(appended[0].removed, true);

  const retry = loader.load("defects");
  assert.equal(appended.length, 2);
  appended[1].onload();
  await retry;
});

test("loads multi-script routes in dependency order", async () => {
  const { loader, appended } = loadRouteLoader();
  const loading = loader.load("admin");
  assert.equal(appended.length, 1);
  assert.equal(appended[0].dataset.routeModule, "views/view-audit-log.js");

  appended[0].onload();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(appended.length, 2);
  assert.equal(appended[1].dataset.routeModule, "views/view-admin.js");
  appended[1].onload();
  await loading;
});
