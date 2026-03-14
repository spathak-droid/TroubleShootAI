"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Shield, ExternalLink, ChevronDown } from "lucide-react";
import type { ExternalAnalyzerIssue } from "@/lib/types";

export function ExternalAsAnalyzerRow({
  issue,
  isExpanded,
  onToggle,
  index,
}: {
  issue: ExternalAnalyzerIssue;
  isExpanded: boolean;
  onToggle: () => void;
  index: number;
}) {
  const isFail = issue.severity === "critical";
  const isWarn = issue.severity === "warning";
  return (
    <div>
      <motion.div
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: index * 0.03 }}
        className="flex items-start gap-3 rounded-xl px-4 py-3 mb-1 cursor-pointer transition-all hover:bg-white/[0.03]"
        style={{ border: "1px solid transparent", borderBottomColor: "var(--border-subtle)" }}
        onClick={onToggle}
      >
        <div
          className="flex h-8 w-8 items-center justify-center rounded-lg flex-shrink-0 mt-0.5"
          style={{
            background: isFail
              ? "rgba(239, 68, 68, 0.12)"
              : isWarn
                ? "rgba(245, 158, 11, 0.12)"
                : "rgba(99, 102, 241, 0.12)",
          }}
        >
          <Shield size={14} style={{ color: isFail ? "var(--critical)" : isWarn ? "var(--warning)" : "var(--info)" }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {isFail && <span className="badge badge-critical">FAIL</span>}
            {isWarn && <span className="badge badge-warning">WARN</span>}
            {!isFail && !isWarn && <span className="badge badge-info">INFO</span>}
            <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
              {issue.title || issue.name}
            </span>
            <span className="badge badge-muted text-[10px]">{issue.analyzer_type}</span>
            {issue.corroborates ? (
              <span className="text-[10px] font-medium rounded-full px-2 py-0.5" style={{ backgroundColor: "rgba(99, 102, 241, 0.12)", color: "var(--accent-light)" }}>
                corroborates
              </span>
            ) : (
              <span className="text-[10px] font-medium rounded-full px-2 py-0.5" style={{ backgroundColor: "rgba(234, 179, 8, 0.1)", color: "var(--warning)" }}>
                gap-fill
              </span>
            )}
          </div>
          <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{issue.message}</p>
          {issue.corroborates && (
            <p className="mt-0.5 text-[10px]" style={{ color: "var(--accent-light)" }}>
              Corroborates: {issue.corroborates}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {issue.uri && (
            <a href={issue.uri} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="p-1.5 rounded-lg transition-colors hover:bg-white/[0.05]" style={{ color: "var(--accent-light)" }}>
              <ExternalLink size={12} />
            </a>
          )}
          <ChevronDown
            size={14}
            style={{ color: "var(--muted)", transition: "transform 0.2s", transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)" }}
          />
        </div>
      </motion.div>
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div
              className="mx-3 mb-3 mt-1 rounded-xl p-4"
              style={{ backgroundColor: "rgba(10, 14, 23, 0.6)", border: "1px solid var(--border-subtle)" }}
            >
              {issue.contradicts && (
                <p className="text-xs mb-2" style={{ color: "var(--critical)" }}>
                  Contradicts native finding: {issue.contradicts}
                </p>
              )}
              <p className="text-xs" style={{ color: "var(--foreground)" }}>{issue.message}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
