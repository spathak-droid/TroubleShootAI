"use client";

import { motion } from "framer-motion";
import { Shield } from "lucide-react";
import type { ConfigIssue } from "@/lib/types";
import { SummaryBar } from "../SummaryBar";
import { SeverityBadge } from "./helpers";

export function ConfigIssuesSection({ issues }: { issues: ConfigIssue[] }) {
  if (issues.length === 0) return null;
  const critical = issues.filter(i => i.severity === "critical");
  const warning = issues.filter(i => i.severity === "warning");
  const info = issues.filter(i => i.severity === "info");
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <Shield size={16} style={{ color: "var(--warning)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>Config Issues</h2>
        <span className="badge badge-muted text-[10px] ml-1">{issues.length}</span>
      </div>
      <SummaryBar pass_count={info.length} warn_count={warning.length} fail_count={critical.length} />
      <div className="flex flex-col gap-1">
        {issues.map((issue, i) => (
          <div key={`cfg-${i}`} className="flex items-start gap-3 rounded-lg px-3 py-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityBadge severity={issue.severity ?? "warning"} />
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                  {issue.namespace}/{issue.resource_name}
                </span>
                <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>{issue.resource_type}</span>
                <span className="text-[10px] font-mono rounded px-1.5 py-0.5"
                  style={{ backgroundColor: "rgba(234, 179, 8, 0.1)", color: "var(--warning)" }}>
                  {issue.issue_type ?? issue.issue ?? "missing"}
                </span>
              </div>
              {(issue.message || issue.referenced_by || issue.missing_key) && (
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
                  {issue.message ?? `Referenced by ${issue.referenced_by}${issue.missing_key ? ` (missing key: ${issue.missing_key})` : ""}`}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
