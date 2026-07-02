// Expose common React APIs as globals.
//
// Historically the .jsx files ran through Babel standalone, which turned
// top-level `const { useState } = React` into a global `var` — so files could
// use hooks bare without importing or destructuring them. The esbuild build
// wraps each file in an IIFE (file-local scope), so this shim provides those
// names globally for files that reference them without destructuring.
(function () {
  var names = [
    "useState", "useEffect", "useMemo", "useCallback", "useRef", "useContext",
    "useReducer", "useLayoutEffect", "useTransition", "useDeferredValue",
    "useId", "useSyncExternalStore",
    "createContext", "createElement", "cloneElement", "Fragment",
    "memo", "forwardRef", "lazy", "Suspense", "StrictMode",
  ];
  for (var i = 0; i < names.length; i++) {
    var n = names[i];
    if (React[n] !== undefined && window[n] === undefined) window[n] = React[n];
  }
})();
