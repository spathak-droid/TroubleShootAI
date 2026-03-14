"use client";

import { motion } from "framer-motion";
import { GitCompare } from "lucide-react";
import type { DeploymentIssue } from "@/lib/types";
import { SeverityBadge } from "./helpers";

export function DeploymentIssuesSection({ issues }: { issues: DeploymentIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <GitCompare size={16} style={{ color: "var(--warning)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>Deployment Issues</h2>
        <span className="badge badge-muted text-[10px] ml-1">{issues.length}</span>
      </div>
      <div className="flex flex-col gap-1">
        {issues.map((issue, i) => (
          <div key={`dep-${i}`} className="flex items-start gap-3 rounded-lg px-3 py-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityBadge severity={issue.severity ?? "warning"} />
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                  {issue.namespace}/{issue.deployment_name ?? issue.name ?? "unknown-deployment"}
                </span>
                <span className="text-[10px] font-mono rounded px-1.5 py-0.5"
                  style={{ backgroundColor: "rgba(234, 179, 8, 0.1)", color: "var(--warning)" }}>
                  {issue.issue_type ?? issue.issue ?? "replica_mismatch"}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-1">
                {issue.desired_replicas != null && (
                  <span className="text-xs" style={{ color: "var(--muted)" }}>
                    desired: {issue.desired_replicas} / available: {issue.available_replicas ?? issue.ready_replicas ?? 0}
                  </span>
                )}
              </div>
              {(issue.message ?? issue.issue) && (
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{issue.message ?? issue.issue}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
