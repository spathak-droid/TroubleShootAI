"use client";

import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import type { PodIssue } from "@/lib/types";
import { SummaryBar } from "../SummaryBar";
import { SeverityBadge } from "./helpers";

export function PodIssuesSection({ issues }: { issues: PodIssue[] }) {
  if (issues.length === 0) return null;
  const critical = issues.filter(i => i.severity === "critical");
  const warning = issues.filter(i => i.severity === "warning");
  const info = issues.filter(i => i.severity === "info");
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle size={16} style={{ color: "var(--critical)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>Pod Issues</h2>
        <span className="badge badge-muted text-[10px] ml-1">{issues.length}</span>
      </div>
      <SummaryBar pass_count={info.length} warn_count={warning.length} fail_count={critical.length} />
      <div className="flex flex-col gap-1">
        {issues.map((issue, i) => (
          <div key={`pod-${i}`} className="flex items-start gap-3 rounded-lg px-3 py-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityBadge severity={issue.severity} />
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                  {issue.namespace}/{issue.pod_name}
                </span>
                <span className="text-[10px] font-mono rounded px-1.5 py-0.5"
                  style={{ backgroundColor: "rgba(99, 102, 241, 0.1)", color: "var(--accent-light)" }}>
                  {issue.issue_type}
                </span>
                {(issue.container_name || issue.container) && (
                  <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>{issue.container_name || issue.container}</span>
                )}
              </div>
              <div className="flex items-center gap-3 mt-1">
                {(issue.restart_count ?? 0) > 0 && (
                  <span className="text-xs" style={{ color: "var(--muted)" }}>{issue.restart_count} restarts</span>
                )}
                {issue.exit_code != null && (
                  <span className="text-xs" style={{ color: "var(--muted)" }}>exit code: {issue.exit_code}</span>
                )}
              </div>
              {issue.message && (
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{issue.message}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
