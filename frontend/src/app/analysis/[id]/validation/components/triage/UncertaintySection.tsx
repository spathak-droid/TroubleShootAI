"use client";

import { motion } from "framer-motion";
import { Search } from "lucide-react";
import type { UncertaintyGap } from "@/lib/types";

export function UncertaintySection({ gaps }: { gaps: UncertaintyGap[] }) {
  if (gaps.length === 0) return null;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <Search size={16} style={{ color: "var(--muted)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>Uncertainty &amp; Gaps</h2>
        <span className="badge badge-muted text-[10px] ml-1">{gaps.length}</span>
      </div>
      <p className="text-xs mb-3" style={{ color: "var(--muted)" }}>
        Areas where the analysis is uncertain or missing data would improve confidence.
      </p>
      <div className="flex flex-col gap-1">
        {gaps.map((gap, i) => {
          const title = gap.area || gap.question || "Unknown gap";
          const desc = gap.description || gap.reason || "";
          const help = gap.what_would_help || gap.to_investigate || gap.collect_command || "";
          const impactColor = gap.impact === "HIGH" ? "var(--critical)" : gap.impact === "MEDIUM" ? "var(--warning)" : "var(--muted)";
          return (
            <div key={`unc-${i}`} className="rounded-lg px-3 py-3" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>{title}</span>
                <span className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
                  style={{ backgroundColor: `color-mix(in srgb, ${impactColor} 15%, transparent)`, color: impactColor }}>
                  {gap.impact}
                </span>
              </div>
              {desc && <p className="text-xs mt-1" style={{ color: "var(--foreground)" }}>{desc}</p>}
              {help && (
                <div className="mt-2 rounded px-3 py-2" style={{ backgroundColor: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.2)" }}>
                  <p className="text-xs font-mono" style={{ color: "var(--accent-light)" }}>{help}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
