import { useCallback, useEffect, useState } from "react";
import { api, auth, onUnauthorized } from "./api/client";
import type { Me } from "./api/types";
import { Login } from "./pages/Login";
import { Workspace } from "./pages/Workspace";
import { StoreProvider } from "./state/context";
import { disconnect } from "./state/realtime";

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [ontology, setOntology] = useState<any>(null);
  const [checking, setChecking] = useState(true);

  const load = useCallback(async () => {
    if (!auth.token) { setChecking(false); return; }
    try {
      const [m, o] = await Promise.all([api.me(), api.ontology()]);
      setMe(m);
      setOntology(o);
    } catch {
      auth.token = null;
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => onUnauthorized(() => { setMe(null); disconnect(); }), []);

  const logout = async () => {
    try { await api.logout(); } catch { /* already expired */ }
    auth.token = null;
    disconnect();
    setMe(null);
  };

  if (checking) return <div className="p-4 text-xs text-ink-400">Loading…</div>;
  if (!me) return <Login onLogin={load} />;
  return (
    <StoreProvider me={me} ontology={ontology}>
      <Workspace onLogout={logout} />
    </StoreProvider>
  );
}
