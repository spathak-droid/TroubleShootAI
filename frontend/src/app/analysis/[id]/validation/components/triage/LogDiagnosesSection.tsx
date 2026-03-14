"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ChevronDown } from "lucide-react";
import type { LogDiagnosis } from "@/lib/types";
import { ConfidenceMeter } from "../ConfidenceMeter";
import { rootCauseCategoryColors } from "./helpers";

export function LogDiagnosesSection({
  diagnoses,
  expandedId,
  onToggle,
}: {
  diagnoses: LogDiagnosis[];
  expandedId: string | null;
  onToggle: (id: string) => void;
}) {
  if (diagnoses.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <Sparkles size={16} style={{ color: "var(--accent-light)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          AI Log Diagnoses
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{diagnoses.length}</span>
      </div>
      <div className="flex flex-col">
        {diagnoses.map((diag, i) => {
          const rowKey = `logdiag-${i}`;
          const isOpen = expandedId === rowKey;
          const catStyle = rootCauseCategoryColors[diag.root_cause_category] ?? rootCauseCategoryColors.unknown;
          return (
            <div key={rowKey}>
              <div
                className="flex items-start gap-3 rounded-lg px-3 py-2.5 cursor-pointer transition-colors hover:bg-white/[0.02]"
                style={{ borderBottom: "1px solid var(--border-subtle)" }}
                onClick={() => onToggle(rowKey)}
              >
                <Sparkles size={14} style={{ color: catStyle.color, marginTop: 2 }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                      {diag.namespace}/{diag.pod_name}
                    </span>
                    <span
                      className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
                      style={{ backgroundColor: catStyle.bg, color: catStyle.color }}
                    >
                      {diag.root_cause_category.replace(/_/g, " ")}
                    </span>
                    {diag.container_name && (
                      <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                        {diag.container_name}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{diag.diagnosis}</p>
                  <ConfidenceMeter value={diag.confidence} />
                </div>
                <ChevronDown
                  size={14}
                  style={{ color: "var(--muted)", transition: "transform 0.2s", transform: isOpen ? "rotate(180deg)" : "rotate(0deg)", flexShrink: 0 }}
                />
              </div>
              <AnimatePresence>
                {isOpen && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div
                      className="mx-3 mb-3 mt-1 rounded-lg p-4 flex flex-col gap-3"
                      style={{ backgroundColor: "rgba(10, 14, 23, 0.5)", border: "1px solid var(--border-subtle)" }}
                    >
                      {diag.key_log_line && (
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--accent-light)" }}>
                            Key Log Line
                          </p>
                          <pre
                            className="overflow-auto rounded p-3 text-[11px] leading-relaxed font-mono"
                            style={{ backgroundColor: "rgba(10, 14, 23, 0.8)", border: "1px solid var(--border-subtle)", color: "var(--foreground)" }}
                          >
                            {diag.key_log_line}
                          </pre>
                        </div>
                      )}
                      {diag.why && (
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--warning)" }}>
                            Why
                          </p>
                          <p className="text-xs" style={{ color: "var(--foreground)" }}>{diag.why}</p>
                        </div>
                      )}
                      {diag.fix_description && (
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--success)" }}>
                            Fix
                          </p>
                          <p className="text-xs" style={{ color: "var(--foreground)" }}>{diag.fix_description}</p>
                          {diag.fix_commands.length > 0 && (
                            <pre
                              className="mt-1 overflow-auto rounded p-2 text-[11px] leading-relaxed font-mono"
                              style={{ backgroundColor: "rgba(10, 14, 23, 0.6)", border: "1px solid var(--border-subtle)", color: "var(--accent-light)" }}
                            >
                              {diag.fix_commands.join("\n")}
                            </pre>
                          )}
                        </div>
                      )}
                      {diag.additional_context_needed.length > 0 && (
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--muted)" }}>
                            Additional Context Needed
                          </p>
                          <ul className="list-disc list-inside">
                            {diag.additional_context_needed.map((ctx, j) => (
                              <li key={j} className="text-xs" style={{ color: "var(--foreground)" }}>{ctx}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
