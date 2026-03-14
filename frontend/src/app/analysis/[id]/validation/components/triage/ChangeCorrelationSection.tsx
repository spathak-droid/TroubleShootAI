"use client";

import { motion } from "framer-motion";
import { Clock } from "lucide-react";
import type { ChangeCorrelation } from "@/lib/types";
import { SeverityBadge, correlationStrengthColors, formatTimeDelta } from "./helpers";

export function ChangeCorrelationSection({
  correlations,
}: {
  correlations: ChangeCorrelation[];
}) {
  if (correlations.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <Clock size={16} style={{ color: "var(--warning)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          What Changed Before Failures
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{correlations.length}</span>
      </div>
      <div className="flex flex-col">
        {correlations.map((corr, i) => {
          const strengthStyle = correlationStrengthColors[corr.correlation_strength] ?? correlationStrengthColors.weak;
          return (
            <motion.div
              key={`change-${i}`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3 rounded-lg px-3 py-2.5"
              style={{ borderBottom: "1px solid var(--border-subtle)" }}
            >
              <Clock size={14} style={{ color: strengthStyle.color, marginTop: 2 }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <SeverityBadge severity={corr.severity} />
                  <span
                    className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
                    style={{ backgroundColor: strengthStyle.bg, color: strengthStyle.color }}
                  >
                    {corr.correlation_strength}
                  </span>
                  <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                    {corr.change.resource_type}/{corr.change.resource_name}
                  </span>
                  <span
                    className="text-[10px] font-mono rounded px-1.5 py-0.5"
                    style={{ backgroundColor: "rgba(99, 102, 241, 0.1)", color: "var(--accent-light)" }}
                  >
                    {corr.change.change_type}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs" style={{ color: "var(--warning)" }}>
                    {formatTimeDelta(corr.time_delta_seconds)}
                  </span>
                  {corr.change.timestamp && (
                    <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                      {new Date(corr.change.timestamp).toLocaleString()}
                    </span>
                  )}
                </div>
                {corr.explanation && (
                  <p className="mt-1 text-xs" style={{ color: "var(--foreground)" }}>{corr.explanation}</p>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
