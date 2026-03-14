"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ExternalLink, ChevronDown, Brain } from "lucide-react";
import type { TroubleshootAnalyzerResult } from "@/lib/types";
import type { DisplayFinding } from "../../shared/types";
import { StatusIcon, StatusBadge, FindingInline } from "../../shared";

export function AnalyzerResultRow({
  result,
  finding,
  isExpanded,
  onToggle,
  index,
}: {
  result: TroubleshootAnalyzerResult;
  finding?: DisplayFinding;
  isExpanded: boolean;
  onToggle: () => void;
  index: number;
}) {
  const clickable = !!finding;
  return (
    <div>
      <motion.div
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: index * 0.03 }}
        className={`flex items-start gap-3 rounded-xl px-4 py-3 mb-1 transition-all ${clickable ? "cursor-pointer hover:bg-white/[0.03]" : ""}`}
        style={{ border: "1px solid transparent", borderBottomColor: "var(--border-subtle)" }}
        onClick={clickable ? onToggle : undefined}
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
            {result.analyzer_type && (
              <span className="badge badge-muted text-[10px]">{result.analyzer_type}</span>
            )}
            {finding && (
              <span
                className="text-[10px] font-medium rounded-full px-2 py-0.5"
                style={{ backgroundColor: "rgba(99, 102, 241, 0.12)", color: "var(--accent-light)" }}
              >
                <Brain size={9} className="inline mr-0.5 -mt-px" />
                AI insight
              </span>
            )}
          </div>
          {result.message && (
            <p className="mt-1 text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
              {result.message}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {result.uri && (
            <a
              href={result.uri}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="p-1.5 rounded-lg transition-colors hover:bg-white/[0.05]"
              style={{ color: "var(--accent-light)" }}
            >
              <ExternalLink size={12} />
            </a>
          )}
          {finding && (
            <ChevronDown
              size={14}
              style={{
                color: "var(--muted)",
                transition: "transform 0.2s",
                transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
              }}
            />
          )}
        </div>
      </motion.div>
      <AnimatePresence>
        {isExpanded && finding && <FindingInline finding={finding} />}
      </AnimatePresence>
    </div>
  );
}
