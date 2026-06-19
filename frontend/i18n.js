// ThoroTest i18n — lightweight translation engine
// Adding a new language: create frontend/locales/XX.js and add a <script> tag in index.html

window.TH_LOCALES = window.TH_LOCALES || {};

window.TH_I18N = (() => {
  const STORAGE_KEY = "th_lang";
  const DEFAULT_LANG = "en";

  let _lang = localStorage.getItem(STORAGE_KEY) || DEFAULT_LANG;
  const _listeners = new Set();

  function _resolve(lang, key) {
    const keys = key.split(".");
    let node = window.TH_LOCALES[lang];
    for (const k of keys) {
      if (!node || typeof node !== "object") return undefined;
      node = node[k];
    }
    return typeof node === "string" ? node : undefined;
  }

  function t(key, params) {
    let val = _resolve(_lang, key);
    if (val === undefined) val = _resolve(DEFAULT_LANG, key);
    if (val === undefined) return key;
    if (params) {
      val = val.replace(/\{\{(\w+)\}\}/g, (_, p) => (params[p] !== undefined ? params[p] : `{{${p}}}`));
    }
    return val;
  }

  function setLanguage(lang) {
    if (!window.TH_LOCALES[lang]) {
      console.warn(`[i18n] locale "${lang}" not loaded, falling back to "${DEFAULT_LANG}"`);
      lang = DEFAULT_LANG;
    }
    _lang = lang;
    localStorage.setItem(STORAGE_KEY, lang);
    _listeners.forEach(fn => fn(lang));
  }

  function getLanguage() {
    return _lang;
  }

  function subscribe(fn) {
    _listeners.add(fn);
    return () => _listeners.delete(fn);
  }

  function getSupportedLanguages() {
    return Object.keys(window.TH_LOCALES);
  }

  return { t, setLanguage, getLanguage, subscribe, getSupportedLanguages };
})();
