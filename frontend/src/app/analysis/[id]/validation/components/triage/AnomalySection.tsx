"use client";

import { motion } from "framer-motion";
import { GitCompare } from "lucide-react";
import type { PodAnomaly } from "@/lib/types";
import { SeverityBadge, anomalyTypeColors } from "./helpers";

export function AnomalySection({
  anomalies,
}: {
  anomalies: PodAnomaly[];
}) {
  if (anomalies.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <GitCompare size={16} style={{ color: "#f97316" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          Pod Anomaly Detection
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{anomalies.length}</span>
      </div>
      <div className="flex flex-col">
        {anomalies.map((anomaly, i) => {
          const typeStyle = anomalyTypeColors[anomaly.anomaly_type] ?? anomalyTypeColors.env_config;
          return (
            <motion.div
              key={`anomaly-${i}`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3 rounded-lg px-3 py-2.5"
              style={{ borderBottom: "1px solid var(--border-subtle)" }}
            >
              <GitCompare size={14} style={{ color: typeStyle.color, marginTop: 2 }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <SeverityBadge severity={anomaly.severity} />
                  <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                    {anomaly.failing_pod}
                  </span>
                  <span
                    className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
                    style={{ backgroundColor: typeStyle.bg, color: typeStyle.color }}
                  >
                    {anomaly.anomaly_type.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{anomaly.description}</p>
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <div
                    className="rounded p-2"
                    style={{ backgroundColor: "rgba(239, 68, 68, 0.05)", border: "1px solid rgba(239, 68, 68, 0.15)" }}
                  >
                    <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--critical)" }}>
                      Failing
                    </p>
                    <p className="text-xs font-mono" style={{ color: "var(--foreground)" }}>{anomaly.failing_value}</p>
                  </div>
                  <div
                    className="rounded p-2"
                    style={{ backgroundColor: "rgba(34, 197, 94, 0.05)", border: "1px solid rgba(34, 197, 94, 0.15)" }}
                  >
                    <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--success)" }}>
                      Healthy
                    </p>
                    <p className="text-xs font-mono" style={{ color: "var(--foreground)" }}>{anomaly.healthy_value}</p>
                  </div>
                </div>
                {anomaly.suggestion && (
                  <p className="mt-1.5 text-xs">
                    <span style={{ color: "var(--accent-light)" }}>Suggestion: </span>
                    <span style={{ color: "var(--foreground)" }}>{anomaly.suggestion}</span>
                  </p>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
