// Shared React hooks for ThoroTest

function useInitialData(refreshKey = 0) {
  const [state, setState] = React.useState({ data: null, loading: true, error: null });

  React.useEffect(() => {
    fetch('/api/initial-data', { headers: window.authHeaders() })
      .then(r => { if (!r.ok) throw new Error('API unavailable'); return r.json(); })
      .then(data => setState({ data, loading: false, error: null }))
      .catch(err => {
        setState({ data: window.TH_DATA || null, loading: false, error: err.message });
      });
  }, [refreshKey]);

  return state;
}

window.useInitialData = useInitialData;


/**
 * Props that make a non-button element behave like a button for keyboard users.
 *
 * Much of this UI renders interactive controls as styled <div>s (tree rows,
 * filter chips, cards). A plain onClick handler is mouse-only: no tab stop, no
 * Enter/Space activation, and no role announced to assistive technology.
 * Spreading these props fixes all three without disturbing the styling.
 *
 *   <div className="tree-row" {...clickable(() => select(id))}>
 *
 * Prefer a real <button className="as-button"> for new code — this exists so
 * existing markup can be made operable without restructuring it.
 */
function clickable(onActivate, { disabled = false } = {}) {
  if (disabled) return { "aria-disabled": true };
  return {
    role: "button",
    tabIndex: 0,
    onClick: onActivate,
    onKeyDown: (e) => {
      // Space scrolls the page by default; Enter may submit a wrapping form.
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onActivate(e);
      }
    },
  };
}

/** Run `handler` when Escape is pressed, while `active` is true. */
function useEscapeKey(active, handler) {
  React.useEffect(() => {
    if (!active) return undefined;
    const onKey = (e) => { if (e.key === "Escape") handler(e); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, handler]);
}

window.clickable = clickable;
window.useEscapeKey = useEscapeKey;
