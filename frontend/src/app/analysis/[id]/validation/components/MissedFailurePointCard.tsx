"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Lightbulb, ChevronDown } from "lucide-react";
import type { MissedFailurePoint } from "@/lib/types";
import { DependencyChainView } from "./DependencyChainView";
import { CorrelatedSignalsView } from "./CorrelatedSignalsView";

export function MissedFailurePointCard({
  missed,
  isExpanded,
  onToggle,
}: {
  missed: MissedFailurePoint;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div>
      <div
        className="flex items-start gap-3 rounded-lg px-4 py-3 cursor-pointer transition-colors hover:bg-white/[0.02]"
        style={{ borderBottom: "1px solid var(--border-subtle)" }}
        onClick={onToggle}
      >
        <Lightbulb size={14} style={{ color: "var(--warning)", marginTop: 2 }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
              style={{ backgroundColor: "rgba(234, 179, 8, 0.12)", color: "var(--warning)" }}
            >
              {missed.severity}
            </span>
            <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
              {missed.failure_point}
            </span>
            {missed.resource && (
              <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                {missed.resource}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
            {missed.evidence_summary}
          </p>
        </div>
        <ChevronDown
          size={14}
          style={{ color: "var(--muted)", transition: "transform 0.2s", transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)" }}
        />
      </div>
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
              className="mx-4 mb-3 mt-1 rounded-lg p-4 flex flex-col gap-3"
              style={{ backgroundColor: "rgba(10, 14, 23, 0.5)", border: "1px solid var(--border-subtle)" }}
            >
              <DependencyChainView chain={missed.dependency_chain || []} />
              <CorrelatedSignalsView signals={missed.correlated_signals || []} />
              {missed.recommended_action && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--accent-light)" }}>
                    Recommended Action
                  </p>
                  <p className="text-xs" style={{ color: "var(--foreground)" }}>{missed.recommended_action}</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
