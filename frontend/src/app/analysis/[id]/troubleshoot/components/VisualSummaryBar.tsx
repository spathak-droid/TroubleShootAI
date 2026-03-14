"use client";

import { motion } from "framer-motion";

export function VisualSummaryBar({
  pass_count,
  warn_count,
  fail_count,
}: {
  pass_count: number;
  warn_count: number;
  fail_count: number;
}) {
  const total = pass_count + warn_count + fail_count;
  if (total === 0) return null;
  const passPct = (pass_count / total) * 100;
  const warnPct = (warn_count / total) * 100;
  const failPct = (fail_count / total) * 100;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-3 overflow-hidden rounded-full" style={{ background: "var(--border-subtle)" }}>
        {pass_count > 0 && (
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${passPct}%` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            style={{ background: "var(--success)" }}
          />
        )}
        {warn_count > 0 && (
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${warnPct}%` }}
            transition={{ duration: 0.6, ease: "easeOut", delay: 0.1 }}
            style={{ background: "var(--warning)" }}
          />
        )}
        {fail_count > 0 && (
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${failPct}%` }}
            transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 }}
            style={{ background: "var(--critical)" }}
          />
        )}
      </div>
      <div className="flex gap-4 text-xs">
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full" style={{ background: "var(--success)" }} />
          <span style={{ color: "var(--success)" }}>{pass_count} passed</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full" style={{ background: "var(--warning)" }} />
          <span style={{ color: "var(--warning)" }}>{warn_count} warnings</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full" style={{ background: "var(--critical)" }} />
          <span style={{ color: "var(--critical)" }}>{fail_count} failures</span>
        </div>
      </div>
    </div>
  );
}
