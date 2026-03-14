"use client";

import { motion } from "framer-motion";
import { BarChart3 } from "lucide-react";
import type { QuotaIssue } from "@/lib/types";
import { SeverityBadge } from "./helpers";

export function QuotaIssuesSection({ issues }: { issues: QuotaIssue[] }) {
  if (issues.length === 0) return null;

  const issueTypeBadge = (type: string) => {
    const colors: Record<string, { bg: string; color: string }> = {
      quota_exceeded: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--critical)" },
      quota_near_limit: { bg: "rgba(234, 179, 8, 0.15)", color: "var(--warning)" },
      limit_range_conflict: { bg: "rgba(249, 115, 22, 0.15)", color: "#f97316" },
      no_quota: { bg: "rgba(107, 114, 128, 0.15)", color: "var(--muted)" },
    };
    const style = colors[type] ?? colors.no_quota;
    return (
      <span
        className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
        style={{ backgroundColor: style.bg, color: style.color }}
      >
        {type.replace(/_/g, " ")}
      </span>
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <BarChart3 size={16} style={{ color: "var(--warning)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          Resource Quota Issues
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{issues.length}</span>
      </div>
      <div className="flex flex-col">
        {issues.map((issue, i) => (
          <motion.div
            key={`quota-${i}`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start gap-3 rounded-lg px-3 py-2.5"
            style={{ borderBottom: "1px solid var(--border-subtle)" }}
          >
            <BarChart3 size={14} style={{ color: issue.severity === "critical" ? "var(--critical)" : "var(--warning)", marginTop: 2 }} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityBadge severity={issue.severity} />
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                  {issue.namespace}/{issue.resource_name}
                </span>
                {issueTypeBadge(issue.issue_type)}
                <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                  {issue.resource_type}
                </span>
              </div>
              <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{issue.message}</p>
              {issue.current_usage && issue.limit && (
                <div className="mt-1.5 flex items-center gap-2">
                  <span className="text-[10px]" style={{ color: "var(--muted)" }}>
                    {issue.current_usage} / {issue.limit}
                  </span>
                  {issue.issue_type === "quota_near_limit" && (() => {
                    const current = parseFloat(issue.current_usage);
                    const limit = parseFloat(issue.limit);
                    const pct = limit > 0 ? Math.min((current / limit) * 100, 100) : 0;
                    return (
                      <div className="flex items-center gap-1.5 flex-1 max-w-[200px]">
                        <div className="h-1.5 flex-1 rounded-full overflow-hidden" style={{ background: "var(--border-subtle)" }}>
                          <div
                            className="h-full rounded-full"
                            style={{ width: `${pct}%`, background: pct >= 90 ? "var(--critical)" : "var(--warning)" }}
                          />
                        </div>
                        <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>{Math.round(pct)}%</span>
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
