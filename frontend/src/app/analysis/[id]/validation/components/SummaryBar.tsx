"use client";

export function SummaryBar({ pass_count, warn_count, fail_count }: { pass_count: number; warn_count: number; fail_count: number }) {
  const total = pass_count + warn_count + fail_count;
  if (total === 0) return null;
  return (
    <div className="flex items-center gap-3 mb-4">
      <div className="flex h-2 flex-1 overflow-hidden rounded-full" style={{ background: "var(--border-subtle)" }}>
        {pass_count > 0 && <div style={{ width: `${(pass_count / total) * 100}%`, background: "var(--success)" }} />}
        {warn_count > 0 && <div style={{ width: `${(warn_count / total) * 100}%`, background: "var(--warning)" }} />}
        {fail_count > 0 && <div style={{ width: `${(fail_count / total) * 100}%`, background: "var(--critical)" }} />}
      </div>
      <div className="flex gap-3 text-xs" style={{ color: "var(--muted)" }}>
        <span style={{ color: "var(--success)" }}>{pass_count} pass</span>
        <span style={{ color: "var(--warning)" }}>{warn_count} warn</span>
        <span style={{ color: "var(--critical)" }}>{fail_count} fail</span>
      </div>
    </div>
  );
}
