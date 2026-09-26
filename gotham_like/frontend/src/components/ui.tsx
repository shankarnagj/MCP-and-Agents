import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { EpistemicStatus } from "../api/types";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function Button({ variant = "default", className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "ghost" | "danger" }) {
  return (
    <button
      {...p}
      className={cx(
        "inline-flex items-center gap-1 rounded-sm px-2 py-[3px] text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed",
        variant === "default" && "bg-ink-700 hover:bg-ink-600 text-ink-100 border border-ink-600",
        variant === "primary" && "bg-accent-dim hover:bg-accent text-white border border-accent-dim",
        variant === "ghost" && "hover:bg-ink-700 text-ink-300",
        variant === "danger" && "bg-danger/20 hover:bg-danger/40 text-danger border border-danger/40",
        className,
      )}
    />
  );
}

export function PanelHeader({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex h-7 shrink-0 items-center justify-between border-b border-ink-700 bg-ink-850 px-2">
      <div className="truncate whitespace-nowrap text-2xs font-semibold uppercase tracking-wider text-ink-300">{title}</div>
      <div className="flex items-center gap-1">{children}</div>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange, right }: { tabs: { id: T; label: ReactNode }[]; value: T; onChange: (t: T) => void; right?: ReactNode }) {
  return (
    <div className="flex h-7 shrink-0 items-stretch border-b border-ink-700 bg-ink-850">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cx("px-3 text-2xs font-semibold uppercase tracking-wider", value === t.id ? "border-b-2 border-accent text-ink-100" : "text-ink-400 hover:text-ink-200")}
        >
          {t.label}
        </button>
      ))}
      <div className="ml-auto flex items-center gap-1 pr-2">{right}</div>
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  RAW: "border-ink-500 text-ink-300",
  DERIVED: "border-accent-dim text-accent",
  SYSTEM_INFERENCE: "border-signal/60 text-signal",
  ANALYST_ASSERTION: "border-hypo/60 text-hypo",
  VERIFIED: "border-verified/60 text-verified",
};
const STATUS_LABEL: Record<string, string> = {
  RAW: "RAW", DERIVED: "DERIVED", SYSTEM_INFERENCE: "INFERENCE", ANALYST_ASSERTION: "ASSERTION", VERIFIED: "VERIFIED",
};
const STATUS_HELP: Record<string, string> = {
  RAW: "Unmodified source record",
  DERIVED: "Deterministically derived from source records",
  SYSTEM_INFERENCE: "Produced by an algorithm — not an established fact",
  ANALYST_ASSERTION: "Claim made by an analyst — a hypothesis",
  VERIFIED: "Derived fact explicitly verified by an authorised analyst",
};

export function StatusBadge({ status }: { status: EpistemicStatus | string }) {
  return (
    <span title={STATUS_HELP[status] ?? status} className={cx("rounded-sm border px-1 text-2xs font-semibold tracking-wide", STATUS_STYLE[status] ?? "border-ink-500 text-ink-300")}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function SignalTag() {
  return <span className="rounded-sm border border-signal/60 bg-signal/10 px-1 text-2xs font-bold tracking-wide text-signal">ANALYTICAL SIGNAL</span>;
}

export function TypeDot({ color }: { color: string }) {
  return <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />;
}

export function KV({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <table className="w-full text-xs">
      <tbody>
        {rows.map(([k, v], i) => (
          <tr key={i} className="border-b border-ink-800 align-top">
            <td className="w-1/3 py-[3px] pr-2 text-ink-400">{k}</td>
            <td className="break-all py-[3px] font-mono text-2xs text-ink-100">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="p-3 text-xs text-ink-400">{children}</div>;
}

export function Section({ title, children, right }: { title: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <div className="border-b border-ink-800 px-2 py-2">
      <div className="mb-1 flex items-center justify-between">
        <div className="text-2xs font-semibold uppercase tracking-wider text-ink-400">{title}</div>
        {right}
      </div>
      {children}
    </div>
  );
}

export const fmtTime = (s: string | null | undefined) => (s ? s.replace("T", " ").replace(/\+00:00$|Z$/, "").slice(0, 19) : "—");
export const fmtPct = (x: number) => `${Math.round(x * 100)}%`;
