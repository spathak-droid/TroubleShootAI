"use client";

import { motion } from "framer-motion";
import { EyeOff } from "lucide-react";
import type { CoverageGap } from "@/lib/types";

export function CoverageGapsSection({ gaps }: { gaps: CoverageGap[] }) {
  if (gaps.length === 0) return null;

  const severityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };
  const sorted = [...gaps].sort((a, b) => (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9));

  const gapSeverityStyle = (sev: string) => {
    switch (sev) {
      case "high": return { bg: "rgba(234, 179, 8, 0.15)", color: "#f59e0b" };
      case "medium": return { bg: "rgba(251, 191, 36, 0.1)", color: "#fbbf24" };
      default: return { bg: "rgba(107, 114, 128, 0.1)", color: "var(--muted)" };
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
      style={{ borderLeft: "3px solid #f59e0b" }}
    >
      <div className="flex items-center gap-2 mb-3">
        <EyeOff size={16} style={{ color: "#f59e0b" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          Coverage Gaps
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{gaps.length}</span>
      </div>
      <p className="text-xs mb-3" style={{ color: "var(--muted)" }}>
        Areas of the bundle that are not examined by any scanner — blind spots in the analysis.
      </p>
      <div className="flex flex-col">
        {sorted.map((gap, i) => {
          const style = gapSeverityStyle(gap.severity);
          return (
            <motion.div
              key={`gap-${i}`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3 rounded-lg px-3 py-2.5"
              style={{ borderBottom: "1px solid var(--border-subtle)" }}
            >
              <EyeOff size={14} style={{ color: style.color, marginTop: 2 }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
                    style={{ backgroundColor: style.bg, color: style.color }}
                  >
                    {gap.severity}
                  </span>
                  <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                    {gap.area}
                  </span>
                  {gap.data_present && (
                    <span className="text-[10px] rounded px-1.5 py-0.5" style={{ backgroundColor: "rgba(34, 197, 94, 0.1)", color: "var(--success)" }}>
                      data present
                    </span>
                  )}
                  {!gap.data_present && (
                    <span className="text-[10px] rounded px-1.5 py-0.5" style={{ backgroundColor: "rgba(107, 114, 128, 0.1)", color: "var(--muted)" }}>
                      no data
                    </span>
                  )}
                </div>
                {gap.why_it_matters && (
                  <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{gap.why_it_matters}</p>
                )}
                {gap.data_path && (
                  <p className="mt-0.5 text-[10px] font-mono" style={{ color: "var(--muted)" }}>{gap.data_path}</p>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
