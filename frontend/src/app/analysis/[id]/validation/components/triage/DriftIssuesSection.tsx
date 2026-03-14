"use client";

import { motion } from "framer-motion";
import { GitCompare } from "lucide-react";
import type { DriftIssue } from "@/lib/types";
import { SeverityBadge } from "./helpers";

export function DriftIssuesSection({ issues }: { issues: DriftIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <GitCompare size={16} style={{ color: "var(--accent-light)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>Drift Issues</h2>
        <span className="badge badge-muted text-[10px] ml-1">{issues.length}</span>
      </div>
      <div className="flex flex-col gap-1">
        {issues.map((issue, i) => (
          <div key={`drift-${i}`} className="flex items-start gap-3 rounded-lg px-3 py-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityBadge severity={issue.severity ?? "warning"} />
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                  {issue.namespace}/{issue.resource_name ?? issue.name ?? "unknown-resource"}
                </span>
                <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>{issue.resource_type}</span>
                <span className="text-[10px] font-mono rounded px-1.5 py-0.5"
                  style={{ backgroundColor: "rgba(99, 102, 241, 0.1)", color: "var(--accent-light)" }}>
                  {issue.drift_type ?? issue.field ?? "status_drift"}
                </span>
              </div>
              {(issue.expected || issue.actual || issue.spec_value !== undefined || issue.status_value !== undefined) && (
                <div className="flex items-center gap-3 mt-1 text-xs">
                  {(issue.expected ?? issue.spec_value) && <span style={{ color: "var(--success)" }}>expected: {String(issue.expected ?? issue.spec_value)}</span>}
                  {(issue.actual ?? issue.status_value) && <span style={{ color: "var(--critical)" }}>actual: {String(issue.actual ?? issue.status_value)}</span>}
                </div>
              )}
              {(issue.message ?? issue.description) && (
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{issue.message ?? issue.description}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
