"use client";

import { motion } from "framer-motion";
import { Lock } from "lucide-react";
import type { RBACIssue } from "@/lib/types";
import { SeverityBadge } from "./helpers";

export function RBACIssuesSection({ issues }: { issues: RBACIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <Lock size={16} style={{ color: "var(--warning)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          RBAC / Permission Issues
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{issues.length}</span>
      </div>
      <div className="flex flex-col">
        {issues.map((issue, i) => (
          <motion.div
            key={`rbac-${i}`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start gap-3 rounded-lg px-3 py-2.5"
            style={{ borderBottom: "1px solid var(--border-subtle)" }}
          >
            <Lock size={14} style={{ color: issue.severity === "critical" ? "var(--critical)" : "var(--warning)", marginTop: 2 }} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityBadge severity={issue.severity} />
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                  {issue.namespace} / {issue.resource_type}
                </span>
              </div>
              <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{issue.error_message}</p>
              {issue.suggested_permission && (
                <p className="mt-1 text-xs">
                  <span style={{ color: "var(--accent-light)" }}>Suggested: </span>
                  <span className="font-mono text-[11px]" style={{ color: "var(--foreground)" }}>{issue.suggested_permission}</span>
                </p>
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
