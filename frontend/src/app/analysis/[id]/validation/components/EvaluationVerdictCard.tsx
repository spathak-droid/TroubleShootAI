"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Target, ChevronDown } from "lucide-react";
import type { EvaluationVerdict } from "@/lib/types";
import { correctnessColor, correctnessBg } from "../utils";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { DependencyChainView } from "./DependencyChainView";
import { CorrelatedSignalsView } from "./CorrelatedSignalsView";

export function EvaluationVerdictCard({
  verdict,
  isExpanded,
  onToggle,
}: {
  verdict: EvaluationVerdict;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const chainSteps = verdict.dependency_chain?.length ?? 0;
  const signalCount = verdict.correlated_signals?.length ?? 0;

  return (
    <div>
      <div
        className="flex items-start gap-3 rounded-lg px-4 py-3 cursor-pointer transition-colors hover:bg-white/[0.02]"
        style={{ borderBottom: "1px solid var(--border-subtle)" }}
        onClick={onToggle}
      >
        <Target size={14} style={{ color: correctnessColor(verdict.correctness), marginTop: 2 }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
              style={{ backgroundColor: correctnessBg(verdict.correctness), color: correctnessColor(verdict.correctness) }}
            >
              {verdict.correctness}
            </span>
            <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
              {verdict.failure_point}
            </span>
            {verdict.resource && (
              <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                {verdict.resource}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs" style={{ color: "var(--foreground)" }}>
            {verdict.true_likely_cause}
          </p>
          <div className="flex items-center gap-3 mt-1">
            {chainSteps > 0 && (
              <span className="text-[10px]" style={{ color: "var(--accent-light)" }}>
                {chainSteps}-step trace
              </span>
            )}
            {signalCount > 0 && (
              <span className="text-[10px]" style={{ color: "var(--accent-light)" }}>
                {signalCount} cross-referenced signals
              </span>
            )}
            {verdict.blast_radius?.length > 0 && (
              <span className="text-[10px]" style={{ color: "var(--warning)" }}>
                {verdict.blast_radius.length} affected resources
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <ConfidenceMeter value={verdict.confidence_score} />
          <ChevronDown
            size={14}
            style={{ color: "var(--muted)", transition: "transform 0.2s", transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)" }}
          />
        </div>
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
              className="mx-4 mb-3 mt-1 rounded-lg p-4 flex flex-col gap-4"
              style={{ backgroundColor: "rgba(10, 14, 23, 0.5)", border: "1px solid var(--border-subtle)" }}
            >
              {/* App's claim vs evaluator's assessment */}
              {verdict.app_claimed_cause && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--muted)" }}>
                      Pipeline Said
                    </p>
                    <p className="text-xs" style={{ color: "var(--foreground)" }}>{verdict.app_claimed_cause}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--accent-light)" }}>
                      Evaluator Found
                    </p>
                    <p className="text-xs" style={{ color: "var(--foreground-bright)" }}>{verdict.true_likely_cause}</p>
                  </div>
                </div>
              )}

              {/* Dependency chain */}
              <DependencyChainView chain={verdict.dependency_chain || []} />

              {/* Correlated signals */}
              <CorrelatedSignalsView signals={verdict.correlated_signals || []} />

              {/* Blast radius */}
              {verdict.blast_radius?.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--warning)" }}>
                    Blast Radius
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {verdict.blast_radius.map((r: string, i: number) => (
                      <span
                        key={i}
                        className="text-[10px] font-mono rounded px-1.5 py-0.5"
                        style={{ backgroundColor: "rgba(234, 179, 8, 0.1)", color: "var(--warning)" }}
                      >
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Evidence sections */}
              {verdict.supporting_evidence?.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--success)" }}>
                    Supporting Evidence
                  </p>
                  {verdict.supporting_evidence.map((ev: string, i: number) => (
                    <pre
                      key={i}
                      className="mb-1 overflow-auto rounded p-2 text-[10px] leading-relaxed"
                      style={{ backgroundColor: "rgba(10, 14, 23, 0.6)", border: "1px solid var(--border-subtle)", color: "var(--foreground)" }}
                    >
                      {ev}
                    </pre>
                  ))}
                </div>
              )}

              {verdict.contradicting_evidence?.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--critical)" }}>
                    Contradicting Evidence
                  </p>
                  {verdict.contradicting_evidence.map((ev: string, i: number) => (
                    <pre
                      key={i}
                      className="mb-1 overflow-auto rounded p-2 text-[10px] leading-relaxed"
                      style={{ backgroundColor: "rgba(239, 68, 68, 0.05)", border: "1px solid rgba(239, 68, 68, 0.2)", color: "var(--foreground)" }}
                    >
                      {ev}
                    </pre>
                  ))}
                </div>
              )}

              {/* Missed / Misinterpreted */}
              {verdict.missed?.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--warning)" }}>
                    Missed Signals
                  </p>
                  <ul className="list-disc list-inside">
                    {verdict.missed.map((m: string, i: number) => (
                      <li key={i} className="text-xs" style={{ color: "var(--foreground)" }}>{m}</li>
                    ))}
                  </ul>
                </div>
              )}

              {verdict.misinterpreted?.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--critical)" }}>
                    Misinterpreted
                  </p>
                  <ul className="list-disc list-inside">
                    {verdict.misinterpreted.map((m: string, i: number) => (
                      <li key={i} className="text-xs" style={{ color: "var(--foreground)" }}>{m}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Remediation assessment */}
              {verdict.remediation_assessment && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--muted)" }}>
                    Fix Assessment
                  </p>
                  <p className="text-xs" style={{ color: "var(--foreground)" }}>{verdict.remediation_assessment}</p>
                </div>
              )}

              {/* Alternatives */}
              {verdict.stronger_alternative && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--accent-light)" }}>
                    Stronger Alternative Hypothesis
                  </p>
                  <p className="text-xs" style={{ color: "var(--foreground-bright)" }}>{verdict.stronger_alternative}</p>
                </div>
              )}

              {verdict.alternative_hypotheses?.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--muted)" }}>
                    Other Hypotheses
                  </p>
                  <ul className="list-disc list-inside">
                    {verdict.alternative_hypotheses.map((h: string, i: number) => (
                      <li key={i} className="text-xs" style={{ color: "var(--foreground)" }}>{h}</li>
                    ))}
                  </ul>
                </div>
              )}

              {verdict.notes && (
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--muted)" }}>Notes</p>
                  <p className="text-xs" style={{ color: "var(--foreground)" }}>{verdict.notes}</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
