"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Zap,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ChevronDown,
  Wrench,
} from "lucide-react";
import type { DisplayFinding } from "./types";
import type { SimulationResult } from "@/lib/types";
import { simulateFix } from "@/lib/api";

export function FindingInline({
  finding,
  bundleId,
}: {
  finding: DisplayFinding;
  bundleId?: string;
}) {
  const [simResult, setSimResult] = useState<SimulationResult | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);
  const [simOpen, setSimOpen] = useState(false);

  const hasFix = finding.fixes.length > 0;

  const handleSimulate = useCallback(async () => {
    if (!bundleId || simLoading) return;
    setSimError(null);
    setSimLoading(true);
    setSimOpen(true);
    try {
      const result = await simulateFix(bundleId, finding.id);
      setSimResult(result);
    } catch (err) {
      setSimError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setSimLoading(false);
    }
  }, [bundleId, finding.id, simLoading]);

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2 }}
      className="overflow-hidden"
    >
      <div
        className="mx-3 mb-3 mt-1 rounded-xl p-4 flex flex-col gap-3"
        style={{ backgroundColor: "rgba(10, 14, 23, 0.6)", border: "1px solid var(--border-subtle)" }}
      >
        <div className="flex items-center gap-2">
          <Brain size={12} style={{ color: "var(--accent-light)" }} />
          <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: "var(--accent-light)" }}>
            AI Insight
          </span>
          <div className="flex items-center gap-1 ml-auto">
            <div className="h-1.5 w-16 rounded-full overflow-hidden" style={{ background: "var(--border-subtle)" }}>
              <div className="h-full rounded-full" style={{ width: `${finding.confidence * 100}%`, background: "var(--accent-light)" }} />
            </div>
            <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
              {Math.round(finding.confidence * 100)}%
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--muted)" }}>Symptom</p>
            <p className="text-xs" style={{ color: "var(--foreground)" }}>{finding.symptom}</p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--muted)" }}>Root Cause</p>
            <p className="text-xs" style={{ color: "var(--foreground)" }}>{finding.root_cause}</p>
          </div>
        </div>

        {finding.fixes.length > 0 && (
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--muted)" }}>Fixes</p>
            {finding.fixes.map((fix, i) => (
              <div key={i} className="rounded-lg p-2.5 mb-1" style={{ backgroundColor: "rgba(10, 14, 23, 0.4)", border: "1px solid var(--border-subtle)" }}>
                <p className="text-xs" style={{ color: "var(--foreground)" }}>{(fix.description as string) ?? ""}</p>
                {Array.isArray(fix.commands) && fix.commands.length > 0 && (
                  <pre className="mt-1.5 text-[11px] font-mono p-2 rounded" style={{ color: "var(--accent-light)", background: "rgba(0,0,0,0.3)" }}>
                    {fix.commands.join("\n")}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Simulate Fix Button */}
        {hasFix && bundleId && (
          <div>
            <button
              onClick={handleSimulate}
              disabled={simLoading}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer"
              style={{
                background: simResult ? "rgba(16, 185, 129, 0.1)" : "rgba(99, 102, 241, 0.1)",
                border: simResult
                  ? "1px solid rgba(16, 185, 129, 0.3)"
                  : "1px solid rgba(99, 102, 241, 0.3)",
                color: simResult ? "var(--success)" : "var(--accent-light)",
                opacity: simLoading ? 0.7 : 1,
              }}
            >
              {simLoading ? (
                <Loader2 size={12} className="animate-spin" />
              ) : simResult ? (
                <CheckCircle2 size={12} />
              ) : (
                <Zap size={12} />
              )}
              {simLoading ? "Simulating..." : simResult ? "Re-simulate Fix" : "Simulate Fix"}
            </button>

            {/* Simulation Error */}
            {simError && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-2 flex items-center gap-2 px-3 py-2 rounded-lg text-xs"
                style={{
                  background: "var(--critical-glow)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  color: "var(--critical)",
                }}
              >
                <XCircle size={12} />
                {simError}
              </motion.div>
            )}

            {/* Simulation Results */}
            <AnimatePresence>
              {simOpen && simResult && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div
                    className="mt-2 rounded-lg p-3 flex flex-col gap-2.5"
                    style={{ backgroundColor: "rgba(10, 14, 23, 0.5)", border: "1px solid var(--border-subtle)" }}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Zap size={11} style={{ color: "var(--accent-light)" }} />
                        <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: "var(--accent-light)" }}>
                          Simulation Results
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex items-center gap-1">
                          <div className="h-1.5 w-10 rounded-full overflow-hidden" style={{ background: "var(--border-subtle)" }}>
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${simResult.confidence * 100}%`,
                                background: simResult.confidence >= 0.7 ? "var(--success)" : simResult.confidence >= 0.4 ? "var(--warning)" : "var(--critical)",
                              }}
                            />
                          </div>
                          <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                            {Math.round(simResult.confidence * 100)}%
                          </span>
                        </div>
                        <button
                          onClick={() => setSimOpen(false)}
                          className="hover:opacity-80 cursor-pointer"
                        >
                          <ChevronDown size={12} style={{ color: "var(--muted)", transform: "rotate(180deg)" }} />
                        </button>
                      </div>
                    </div>

                    {/* What resolves (green) */}
                    {simResult.fix_resolves.length > 0 && (
                      <div>
                        <p className="text-[10px] font-medium uppercase tracking-wider mb-1 flex items-center gap-1" style={{ color: "var(--success)" }}>
                          <CheckCircle2 size={10} />
                          Resolves
                        </p>
                        {simResult.fix_resolves.map((item, i) => (
                          <div
                            key={i}
                            className="text-xs px-2.5 py-1.5 rounded mb-0.5"
                            style={{ background: "rgba(16, 185, 129, 0.08)", color: "var(--success)" }}
                          >
                            {item}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* What might break (red) */}
                    {simResult.fix_creates.length > 0 && (
                      <div>
                        <p className="text-[10px] font-medium uppercase tracking-wider mb-1 flex items-center gap-1" style={{ color: "var(--critical)" }}>
                          <XCircle size={10} />
                          Potential Side Effects
                        </p>
                        {simResult.fix_creates.map((item, i) => (
                          <div
                            key={i}
                            className="text-xs px-2.5 py-1.5 rounded mb-0.5"
                            style={{ background: "rgba(239, 68, 68, 0.08)", color: "var(--critical)" }}
                          >
                            {item}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Residual issues (yellow) */}
                    {simResult.residual_issues.length > 0 && (
                      <div>
                        <p className="text-[10px] font-medium uppercase tracking-wider mb-1 flex items-center gap-1" style={{ color: "var(--warning)" }}>
                          <AlertTriangle size={10} />
                          Residual Issues
                        </p>
                        {simResult.residual_issues.map((item, i) => (
                          <div
                            key={i}
                            className="text-xs px-2.5 py-1.5 rounded mb-0.5"
                            style={{ background: "rgba(245, 158, 11, 0.08)", color: "var(--warning)" }}
                          >
                            {item}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Recovery timeline */}
                    <div className="flex items-center gap-2 px-2.5 py-1.5 rounded" style={{ background: "rgba(99, 102, 241, 0.06)" }}>
                      <Clock size={11} style={{ color: "var(--accent-light)" }} />
                      <div>
                        <p className="text-[10px] font-medium uppercase tracking-wider" style={{ color: "var(--muted)" }}>Recovery Timeline</p>
                        <p className="text-xs" style={{ color: "var(--foreground)" }}>{simResult.recovery_timeline}</p>
                      </div>
                    </div>

                    {/* Manual steps */}
                    {simResult.manual_steps_after.length > 0 && (
                      <div>
                        <p className="text-[10px] font-medium uppercase tracking-wider mb-1 flex items-center gap-1" style={{ color: "var(--foreground)" }}>
                          <Wrench size={10} style={{ color: "var(--muted)" }} />
                          Manual Steps Required
                        </p>
                        <ol className="list-decimal list-inside">
                          {simResult.manual_steps_after.map((step, i) => (
                            <li
                              key={i}
                              className="text-xs py-0.5"
                              style={{ color: "var(--foreground)" }}
                            >
                              {step}
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {finding.evidence.length > 0 && (
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--muted)" }}>Evidence</p>
            {finding.evidence.map((ev, i) => (
              <div key={i} className="mb-2">
                <p className="text-[10px] font-mono" style={{ color: "var(--accent-light)" }}>
                  {ev.file}{ev.line_start != null && `:${ev.line_start}`}{ev.line_end != null && `-${ev.line_end}`}
                </p>
                <pre
                  className="mt-0.5 overflow-auto rounded-lg p-2.5 text-[11px] leading-relaxed"
                  style={{ backgroundColor: "rgba(10, 14, 23, 0.6)", border: "1px solid var(--border-subtle)", color: "var(--foreground)" }}
                >
                  {ev.content}
                </pre>
                {ev.relevance && <p className="mt-0.5 text-[10px]" style={{ color: "var(--muted)" }}>{ev.relevance}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}
