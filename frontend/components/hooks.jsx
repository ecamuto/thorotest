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

/**
 * Everything a dialog needs to be usable without a mouse.
 *
 * Returns props to spread onto the overlay and the dialog box:
 *
 *   const modal = useModal(onClose);
 *   <div style={MODAL_OVERLAY} {...modal.overlayProps}>
 *     <div style={MODAL_BOX} {...modal.dialogProps}>…</div>
 *   </div>
 *
 * What it handles, none of which the previous hand-rolled overlays did:
 *
 * - **Escape closes.** Listens in the capture phase and stops propagation, so
 *   with nested dialogs only the innermost one closes.
 * - **Focus moves into the dialog on open** — otherwise focus stays behind on
 *   the trigger, and a screen-reader user is never told anything happened.
 *   Prefers `[data-autofocus]`, then the first focusable control, then the
 *   dialog itself.
 * - **Focus returns to the trigger on close**, so keyboard position is not lost.
 * - **Tab is trapped** inside the dialog. Without this, tabbing walks into the
 *   page behind an overlay the user cannot see.
 * - **Backdrop click closes**, but only when the press *started* on the
 *   backdrop — a drag that begins inside the dialog and releases outside must
 *   not close it (text selection).
 * - Marks the dialog `role="dialog" aria-modal="true"`.
 *
 * `labelledBy` should be the id of the dialog's heading when there is one.
 *
 * Pass `open: false` for a dialog rendered conditionally by its parent
 * (`{editing && <div …>}`). The hook then does nothing, so the parent can call
 * it unconditionally at the top — required by the rules of hooks — without the
 * listeners or the focus move happening while the dialog is closed.
 */
const FOCUSABLE = [
  "a[href]", "button:not([disabled])", "input:not([disabled])",
  "select:not([disabled])", "textarea:not([disabled])", "[tabindex]:not([tabindex='-1'])",
].join(",");

function useModal(onClose, { labelledBy, open = true } = {}) {
  const dialogRef = React.useRef(null);
  const pressedBackdrop = React.useRef(false);
  const closeRef = React.useRef(onClose);
  closeRef.current = onClose;

  React.useEffect(() => {
    if (!open) return undefined;
    const previouslyFocused = document.activeElement;
    const node = dialogRef.current;
    if (node) {
      const target =
        node.querySelector("[data-autofocus]") || node.querySelector(FOCUSABLE) || node;
      // Let the browser finish painting before moving focus, otherwise the
      // element may not be focusable yet on first render.
      window.requestAnimationFrame(() => target && target.focus && target.focus());
    }
    return () => {
      if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
    };
  }, [open]);

  React.useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        closeRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const node = dialogRef.current;
      if (!node) return;
      const items = Array.from(node.querySelectorAll(FOCUSABLE))
        .filter(el => el.offsetParent !== null || el === document.activeElement);
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    // Capture phase so the innermost dialog wins when dialogs are stacked.
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [open]);

  return {
    overlayProps: {
      onMouseDown: (e) => { pressedBackdrop.current = e.target === e.currentTarget; },
      onClick: (e) => {
        if (e.target === e.currentTarget && pressedBackdrop.current) closeRef.current();
        pressedBackdrop.current = false;
      },
    },
    dialogProps: {
      ref: dialogRef,
      role: "dialog",
      "aria-modal": "true",
      ...(labelledBy ? { "aria-labelledby": labelledBy } : {}),
      tabIndex: -1,
      // The overlay's handler fires for clicks that reach it; stop bubbling so a
      // click inside the dialog is never treated as a backdrop click.
      onClick: (e) => e.stopPropagation(),
    },
  };
}

/**
 * Close a dropdown on Escape, and close it when focus leaves entirely.
 *
 * The existing dropdowns render a transparent full-screen div to catch the
 * outside click. That works for a mouse and is invisible to the keyboard: this
 * adds the missing half without adding a tab stop for the backdrop itself.
 *
 *   const dd = useDismissable(open, () => setOpen(false));
 *   <div className="dd-wrap" {...dd.containerProps}> … </div>
 */
function useDismissable(open, onDismiss) {
  const dismissRef = React.useRef(onDismiss);
  dismissRef.current = onDismiss;

  React.useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        dismissRef.current();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [open]);

  return {
    containerProps: {
      onBlur: (e) => {
        // relatedTarget is the element receiving focus; null means focus left
        // the document (alt-tab), which should not close the menu.
        if (e.relatedTarget && !e.currentTarget.contains(e.relatedTarget)) {
          dismissRef.current();
        }
      },
    },
  };
}

window.clickable = clickable;
window.useEscapeKey = useEscapeKey;
window.useModal = useModal;
window.useDismissable = useDismissable;
