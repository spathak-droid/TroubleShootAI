"use client";

import { motion } from "framer-motion";
import type { PreflightCheckResult } from "@/lib/types";
import { StatusIcon, StatusBadge } from "../../shared";

export function PreflightResultRow({ result, index }: { result: PreflightCheckResult; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.03 }}
      className="flex items-start gap-3 rounded-xl px-4 py-3 mb-1"
      style={{ border: "1px solid transparent", borderBottomColor: "var(--border-subtle)" }}
    >
      <div
        className="flex h-8 w-8 items-center justify-center rounded-lg flex-shrink-0 mt-0.5"
        style={{
          background: result.is_fail
            ? "rgba(239, 68, 68, 0.12)"
            : result.is_warn
              ? "rgba(245, 158, 11, 0.12)"
              : "rgba(16, 185, 129, 0.12)",
        }}
      >
        <StatusIcon result={result} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusBadge result={result} />
          <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
            {result.title || result.name}
          </span>
        </div>
        {result.message && (
          <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{result.message}</p>
        )}
      </div>
    </motion.div>
  );
}
