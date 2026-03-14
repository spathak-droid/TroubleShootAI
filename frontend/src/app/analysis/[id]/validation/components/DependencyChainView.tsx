"use client";

import type { DependencyLink } from "@/lib/types";
import { significanceColors } from "../constants";

export function DependencyChainView({ chain }: { chain: DependencyLink[] }) {
  if (chain.length === 0) return null;
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-wider mb-2" style={{ color: "var(--accent-light)" }}>
        Dependency Trace ({chain.length} steps)
      </p>
      <div className="relative ml-3">
        {/* vertical connector line */}
        <div
          className="absolute left-[5px] top-2 bottom-2 w-px"
          style={{ background: "var(--border-subtle)" }}
        />
        {chain.map((link, i) => (
          <div key={i} className="relative pl-6 pb-3 last:pb-0">
            {/* dot */}
            <div
              className="absolute left-0 top-1.5 w-[11px] h-[11px] rounded-full border-2"
              style={{
                borderColor: significanceColors[link.significance] || "var(--muted)",
                backgroundColor: link.significance === "root_cause" ? significanceColors.root_cause : "transparent",
              }}
            />
            <div className="flex flex-col gap-0.5">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-mono font-bold" style={{ color: "var(--accent-light)" }}>
                  Step {link.step_number}
                </span>
                <span
                  className="text-[9px] uppercase font-semibold rounded px-1 py-px"
                  style={{
                    backgroundColor: `${significanceColors[link.significance] || "var(--muted)"}20`,
                    color: significanceColors[link.significance] || "var(--muted)",
                  }}
                >
                  {link.significance}
                </span>
                <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                  {link.resource}
                </span>
              </div>
              <p className="text-xs font-medium" style={{ color: "var(--foreground-bright)" }}>
                {link.observation}
              </p>
              <div
                className="rounded p-1.5 mt-0.5"
                style={{ backgroundColor: "rgba(10, 14, 23, 0.6)", border: "1px solid var(--border-subtle)" }}
              >
                <p className="text-[10px] font-mono" style={{ color: "var(--accent-light)" }}>
                  {link.evidence_source}
                </p>
                <pre className="text-[10px] font-mono mt-0.5 whitespace-pre-wrap" style={{ color: "var(--foreground)" }}>
                  {link.evidence_excerpt}
                </pre>
              </div>
              {link.leads_to && (
                <p className="text-[10px] mt-0.5" style={{ color: "var(--muted)" }}>
                  &#8594; {link.leads_to}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
