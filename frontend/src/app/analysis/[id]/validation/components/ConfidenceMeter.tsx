"use client";

export function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.7 ? "var(--success)" : value >= 0.4 ? "var(--warning)" : "var(--critical)";
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-20 rounded-full overflow-hidden" style={{ background: "var(--border-subtle)" }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>{pct}%</span>
    </div>
  );
}
