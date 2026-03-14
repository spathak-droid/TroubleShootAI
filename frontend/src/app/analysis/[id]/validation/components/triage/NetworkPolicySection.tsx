"use client";

import { motion } from "framer-motion";
import { Network } from "lucide-react";
import type { NetworkPolicyIssue } from "@/lib/types";
import { SeverityBadge } from "./helpers";

export function NetworkPolicySection({ issues }: { issues: NetworkPolicyIssue[] }) {
  if (issues.length === 0) return null;

  const issueTypeStyle = (type: string) => {
    const colors: Record<string, { bg: string; color: string }> = {
      deny_all_ingress: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--critical)" },
      deny_all_egress: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--critical)" },
      no_policies: { bg: "rgba(234, 179, 8, 0.15)", color: "var(--warning)" },
      orphaned_policy: { bg: "rgba(107, 114, 128, 0.15)", color: "var(--muted)" },
    };
    return colors[type] ?? colors.orphaned_policy;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <Network size={16} style={{ color: "var(--info)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          Network Policy Issues
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{issues.length}</span>
      </div>
      <div className="flex flex-col">
        {issues.map((issue, i) => {
          const style = issueTypeStyle(issue.issue_type);
          return (
            <motion.div
              key={`netpol-${i}`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3 rounded-lg px-3 py-2.5"
              style={{ borderBottom: "1px solid var(--border-subtle)" }}
            >
              <Network size={14} style={{ color: style.color, marginTop: 2 }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <SeverityBadge severity={issue.severity} />
                  <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                    {issue.namespace}/{issue.policy_name}
                  </span>
                  <span
                    className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
                    style={{ backgroundColor: style.bg, color: style.color }}
                  >
                    {issue.issue_type.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{issue.message}</p>
                {issue.affected_pods.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {issue.affected_pods.map((pod, j) => (
                      <span
                        key={j}
                        className="text-[10px] font-mono rounded px-1.5 py-0.5"
                        style={{ backgroundColor: "rgba(99, 102, 241, 0.1)", color: "var(--accent-light)" }}
                      >
                        {pod}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
