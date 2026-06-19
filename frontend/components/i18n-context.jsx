// ThoroTest i18n React context + hook
// Usage in any component: const { t, lang, setLanguage } = useI18n();

const { useState, useEffect, useContext, createContext, useCallback } = React;

const I18nContext = createContext({
  t: k => k,
  lang: "en",
  setLanguage: () => {},
});

function I18nProvider({ children }) {
  const [lang, setLangState] = useState(window.TH_I18N.getLanguage());

  useEffect(() => {
    const unsub = window.TH_I18N.subscribe(setLangState);
    return unsub;
  }, []);

  const t = useCallback(
    (key, params) => window.TH_I18N.t(key, params),
    [lang]
  );

  const setLanguage = useCallback(
    (l) => window.TH_I18N.setLanguage(l),
    []
  );

  return (
    <I18nContext.Provider value={{ t, lang, setLanguage }}>
      {children}
    </I18nContext.Provider>
  );
}

function useI18n() {
  return useContext(I18nContext);
}

window.I18nProvider = I18nProvider;
window.useI18n = useI18n;
