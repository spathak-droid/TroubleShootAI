"use client";

import { motion } from "framer-motion";
import { Globe } from "lucide-react";
import type { DNSIssue } from "@/lib/types";
import { SummaryBar } from "../SummaryBar";
import { SeverityBadge } from "./helpers";

const issueTypeLabels: Record<string, string> = {
  coredns_pod_failure: "CoreDNS Failure",
  dns_resolution_error: "DNS Resolution Error",
  missing_endpoints: "Missing Endpoints",
  coredns_config_error: "CoreDNS Config",
};

export function DNSIssuesSection({ issues }: { issues: DNSIssue[] }) {
  if (!issues || issues.length === 0) return null;
  const critical = issues.filter(i => i.severity === "critical");
  const warning = issues.filter(i => i.severity === "warning");
  const info = issues.filter(i => i.severity === "info");
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <Globe size={16} style={{ color: "var(--warning)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>DNS Issues</h2>
        <span className="badge badge-muted text-[10px] ml-1">{issues.length}</span>
      </div>
      <SummaryBar pass_count={info.length} warn_count={warning.length} fail_count={critical.length} />
      <div className="flex flex-col gap-1">
        {issues.map((issue, i) => (
          <div key={`dns-${i}`} className="flex items-start gap-3 rounded-lg px-3 py-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityBadge severity={issue.severity} />
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                  {issue.namespace}/{issue.resource_name}
                </span>
                <span className="text-[10px] font-mono rounded px-1.5 py-0.5"
                  style={{ backgroundColor: "rgba(99, 102, 241, 0.1)", color: "var(--accent-light)" }}>
                  {issueTypeLabels[issue.issue_type] || issue.issue_type}
                </span>
              </div>
              {issue.message && (
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{issue.message}</p>
              )}
              {issue.confidence != null && issue.confidence < 1.0 && (
                <div className="flex items-center gap-1 mt-1">
                  <div className="h-1 w-12 rounded-full overflow-hidden" style={{ background: "var(--border-subtle)" }}>
                    <div className="h-full rounded-full" style={{ width: `${issue.confidence * 100}%`, background: "var(--accent-light)" }} />
                  </div>
                  <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>{Math.round(issue.confidence * 100)}%</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
