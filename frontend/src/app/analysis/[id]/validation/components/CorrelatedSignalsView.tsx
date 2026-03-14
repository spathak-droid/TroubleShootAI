"use client";

import type { CorrelatedSignal } from "@/lib/types";
import { scannerTypeColors } from "../constants";

export function CorrelatedSignalsView({ signals }: { signals: CorrelatedSignal[] }) {
  if (signals.length === 0) return null;
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-wider mb-1.5" style={{ color: "var(--accent-light)" }}>
        Cross-Referenced Signals ({signals.length} scanners)
      </p>
      <div className="flex flex-col gap-1">
        {signals.map((sig, i) => (
          <div
            key={i}
            className="flex items-start gap-2 rounded px-2 py-1.5"
            style={{ backgroundColor: "rgba(10, 14, 23, 0.4)" }}
          >
            <span
              className="text-[9px] font-semibold uppercase rounded px-1.5 py-px flex-shrink-0 mt-0.5"
              style={{
                backgroundColor: `${scannerTypeColors[sig.scanner_type] || "var(--muted)"}20`,
                color: scannerTypeColors[sig.scanner_type] || "var(--muted)",
              }}
            >
              {sig.scanner_type}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-xs" style={{ color: "var(--foreground)" }}>{sig.signal}</p>
              <p className="text-[10px]" style={{ color: "var(--muted)" }}>&#8594; {sig.relates_to}</p>
            </div>
            <span
              className="text-[9px] uppercase flex-shrink-0"
              style={{ color: sig.severity === "critical" ? "var(--critical)" : sig.severity === "warning" ? "var(--warning)" : "var(--muted)" }}
            >
              {sig.severity}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
