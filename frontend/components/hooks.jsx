// Shared React hooks for ThoroTest

function useInitialData(refreshKey = 0) {
  const [state, setState] = React.useState({ data: null, loading: true, error: null });

  React.useEffect(() => {
    fetch('/api/initial-data')
      .then(r => { if (!r.ok) throw new Error('API unavailable'); return r.json(); })
      .then(data => setState({ data, loading: false, error: null }))
      .catch(err => {
        setState({ data: window.TH_DATA || null, loading: false, error: err.message });
      });
  }, [refreshKey]);

  return state;
}

window.useInitialData = useInitialData;
