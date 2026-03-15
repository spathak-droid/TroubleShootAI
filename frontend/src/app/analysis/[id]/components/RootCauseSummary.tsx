"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Target, ChevronDown, CheckCircle, AlertTriangle, Shield } from "lucide-react";
import { useState } from "react";
import type { Hypothesis } from "@/lib/types";

function confidenceColor(confidence: number): string {
  if (confidence >= 0.8) return "var(--critical)";
  if (confidence >= 0.5) return "var(--warning)";
  return "var(--muted)";
}

function categoryLabel(category: string): string {
  const labels: Record<string, string> = {
    resource_exhaustion: "Resource Exhaustion",
    config_error: "Configuration Error",
    image_error: "Image Error",
    dependency_failure: "Dependency Failure",
    scheduling: "Scheduling",
    dns: "DNS",
    tls: "TLS/Certificate",
    unknown: "Unknown",
  };
  return labels[category] || category;
}

export function RootCauseSummary({ hypotheses }: { hypotheses: Hypothesis[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!hypotheses || hypotheses.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <Target size={16} style={{ color: "var(--accent-light)" }} />
        <h2
          className="text-base font-semibold"
          style={{ color: "var(--foreground-bright)" }}
        >
          Root Cause Hypotheses
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">
          {hypotheses.length}
        </span>
      </div>

      <div className="flex flex-col gap-1">
        {hypotheses.map((h, i) => {
          const isOpen = expandedId === h.id;
          return (
            <div key={h.id}>
              <div
                className="flex items-start gap-3 rounded-lg px-3 py-2.5 cursor-pointer transition-colors hover:bg-white/[0.02]"
                style={{
                  borderBottom: "1px solid var(--border-subtle)",
                }}
                onClick={() =>
                  setExpandedId(isOpen ? null : h.id)
                }
              >
                <span
                  className="text-sm font-mono font-bold mt-0.5"
                  style={{ color: confidenceColor(h.confidence), minWidth: "2rem" }}
                >
                  #{i + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                      {h.title}
                    </span>
                    <span className="badge badge-muted text-[10px]">
                      {categoryLabel(h.category)}
                    </span>
                    {h.is_validated && (
                      <span className="flex items-center gap-0.5 text-[10px]" style={{ color: "var(--success, #22c55e)" }}>
                        <CheckCircle size={10} /> Validated
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <div
                      className="h-1.5 w-20 rounded-full overflow-hidden"
                      style={{ background: "var(--border-subtle)" }}
                    >
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${h.confidence * 100}%`,
                          background: confidenceColor(h.confidence),
                        }}
                      />
                    </div>
                    <span
                      className="text-[10px] font-mono"
                      style={{ color: "var(--muted)" }}
                    >
                      {Math.round(h.confidence * 100)}% confidence
                    </span>
                    <span
                      className="text-[10px]"
                      style={{ color: "var(--muted)" }}
                    >
                      {h.supporting_evidence.length} supporting
                      {h.contradicting_evidence.length > 0 &&
                        ` / ${h.contradicting_evidence.length} contradicting`}
                    </span>
                  </div>
                </div>
                <ChevronDown
                  size={14}
                  style={{
                    color: "var(--muted)",
                    transition: "transform 0.2s",
                    transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
                    flexShrink: 0,
                  }}
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
                      className="mx-3 mb-3 mt-1 rounded-xl p-4 flex flex-col gap-3"
                      style={{
                        backgroundColor: "rgba(10, 14, 23, 0.6)",
                        border: "1px solid var(--border-subtle)",
                      }}
                    >
                      <p
                        className="text-xs"
                        style={{ color: "var(--foreground)" }}
                      >
                        {h.description}
                      </p>

                      {h.supporting_evidence.length > 0 && (
                        <div>
                          <p
                            className="text-[10px] font-medium uppercase tracking-wider mb-1"
                            style={{ color: "var(--muted)" }}
                          >
                            Supporting Evidence
                          </p>
                          {h.supporting_evidence.map((ev, j) => (
                            <div
                              key={j}
                              className="flex items-start gap-1.5 mb-1"
                            >
                              <CheckCircle
                                size={10}
                                className="mt-0.5 flex-shrink-0"
                                style={{ color: "var(--success, #22c55e)" }}
                              />
                              <span
                                className="text-xs"
                                style={{ color: "var(--foreground)" }}
                              >
                                {ev}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                      {h.contradicting_evidence.length > 0 && (
                        <div>
                          <p
                            className="text-[10px] font-medium uppercase tracking-wider mb-1"
                            style={{ color: "var(--muted)" }}
                          >
                            Contradicting Evidence
                          </p>
                          {h.contradicting_evidence.map((ev, j) => (
                            <div
                              key={j}
                              className="flex items-start gap-1.5 mb-1"
                            >
                              <AlertTriangle
                                size={10}
                                className="mt-0.5 flex-shrink-0"
                                style={{ color: "var(--warning)" }}
                              />
                              <span
                                className="text-xs"
                                style={{ color: "var(--foreground)" }}
                              >
                                {ev}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                      {h.affected_resources.length > 0 && (
                        <div>
                          <p
                            className="text-[10px] font-medium uppercase tracking-wider mb-1"
                            style={{ color: "var(--muted)" }}
                          >
                            Affected Resources
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {h.affected_resources.map((r, j) => (
                              <span
                                key={j}
                                className="badge badge-muted text-[10px]"
                              >
                                {r}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {h.suggested_fixes.length > 0 && (
                        <div>
                          <p
                            className="text-[10px] font-medium uppercase tracking-wider mb-1"
                            style={{ color: "var(--muted)" }}
                          >
                            Suggested Fixes
                          </p>
                          {h.suggested_fixes.map((fix, j) => (
                            <div
                              key={j}
                              className="flex items-start gap-1.5 mb-1"
                            >
                              <Shield
                                size={10}
                                className="mt-0.5 flex-shrink-0"
                                style={{ color: "var(--accent-light)" }}
                              />
                              <span
                                className="text-xs"
                                style={{ color: "var(--foreground)" }}
                              >
                                {fix}
                              </span>
                            </div>
                          ))}
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
