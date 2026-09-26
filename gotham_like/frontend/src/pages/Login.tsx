import { useState } from "react";
import { api, auth } from "../api/client";
import { Button } from "../components/ui";

export function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      const r = await api.login(username, password);
      auth.token = r.access_token;
      onLogin();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Login failed");
    }
  };
  return (
    <div className="flex h-full items-center justify-center bg-ink-950">
      <form onSubmit={submit} className="w-80 rounded-sm border border-ink-700 bg-ink-900 p-5">
        <div className="mb-4 flex items-center gap-2">
          <div className="h-4 w-4 rotate-45 border-2 border-accent" />
          <span className="text-sm font-semibold tracking-wide">TESSERA WORKBENCH</span>
        </div>
        <label className="mb-1 block text-2xs uppercase tracking-wider text-ink-400" htmlFor="u">Username</label>
        <input id="u" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} className="mb-3 h-7 w-full rounded-sm border border-ink-600 bg-ink-950 px-2 text-xs" />
        <label className="mb-1 block text-2xs uppercase tracking-wider text-ink-400" htmlFor="p">Password</label>
        <input id="p" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="mb-3 h-7 w-full rounded-sm border border-ink-600 bg-ink-950 px-2 text-xs" />
        {err && <div className="mb-2 text-xs text-danger" role="alert">{err}</div>}
        <Button variant="primary" type="submit" className="w-full justify-center py-1">Sign in</Button>
        <p className="mt-4 text-2xs leading-4 text-ink-500">
          Decision-support system. Access is logged. All demonstration content is SYNTHETIC / DEMONSTRATION DATA.
        </p>
      </form>
    </div>
  );
}
