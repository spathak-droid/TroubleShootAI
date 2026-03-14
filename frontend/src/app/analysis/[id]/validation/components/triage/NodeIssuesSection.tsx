"use client";

import { motion } from "framer-motion";
import { Target } from "lucide-react";
import type { NodeIssue } from "@/lib/types";
import { SeverityBadge } from "./helpers";

export function NodeIssuesSection({ issues }: { issues: NodeIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <Target size={16} style={{ color: "var(--warning)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>Node Issues</h2>
        <span className="badge badge-muted text-[10px] ml-1">{issues.length}</span>
      </div>
      <div className="flex flex-col gap-1">
        {issues.map((issue, i) => (
          <div key={`node-${i}`} className="flex items-start gap-3 rounded-lg px-3 py-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityBadge severity={issue.severity} />
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>{issue.node_name}</span>
                {issue.condition && (
                  <span className="text-[10px] font-mono rounded px-1.5 py-0.5"
                    style={{ backgroundColor: "rgba(239, 68, 68, 0.1)", color: "var(--critical)" }}>
                    {issue.condition}
                  </span>
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
