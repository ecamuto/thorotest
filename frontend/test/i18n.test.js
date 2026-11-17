"use strict";

const { afterEach, test } = require("node:test");
const assert = require("node:assert/strict");

const MODULE = require.resolve("../i18n.js");
const ORIGINAL_CONSOLE = global.console;

function loadI18n(storedLanguage = null) {
  const storage = new Map();
  if (storedLanguage) storage.set("th_lang", storedLanguage);
  const warnings = [];

  global.localStorage = {
    getItem: (key) => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
  };
  global.window = {
    TH_LOCALES: {
      en: {
        greeting: "Hello {{name}}",
        fallback: "English fallback",
        nested: { label: "Nested" },
      },
      it: { greeting: "Ciao {{name}}" },
    },
  };
  global.console = {
    ...ORIGINAL_CONSOLE,
    warn: (message) => warnings.push(message),
  };

  delete require.cache[MODULE];
  require(MODULE);
  return { i18n: window.TH_I18N, storage, warnings };
}

afterEach(() => {
  delete require.cache[MODULE];
  delete global.window;
  delete global.localStorage;
  global.console = ORIGINAL_CONSOLE;
});

test("translates nested keys, parameters, fallbacks, and missing keys", () => {
  const { i18n } = loadI18n("it");
  assert.equal(i18n.getLanguage(), "it");
  assert.equal(i18n.t("greeting", { name: "Ada" }), "Ciao Ada");
  assert.equal(i18n.t("greeting", {}), "Ciao {{name}}");
  assert.equal(i18n.t("fallback"), "English fallback");
  assert.equal(i18n.t("nested.label"), "Nested");
  assert.equal(i18n.t("nested"), "nested");
  assert.equal(i18n.t("missing.key"), "missing.key");
});

test("changes language, persists it, and notifies active subscribers", () => {
  const { i18n, storage } = loadI18n();
  const changes = [];
  const unsubscribe = i18n.subscribe((language) => changes.push(language));

  i18n.setLanguage("it");
  unsubscribe();
  i18n.setLanguage("en");

  assert.deepEqual(changes, ["it"]);
  assert.equal(storage.get("th_lang"), "en");
  assert.deepEqual(i18n.getSupportedLanguages().sort(), ["en", "it"]);
});

test("unknown locale warns and falls back to English", () => {
  const { i18n, warnings } = loadI18n();
  i18n.setLanguage("fr");
  assert.equal(i18n.getLanguage(), "en");
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /locale "fr" not loaded/);
});
