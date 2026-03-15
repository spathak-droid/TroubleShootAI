"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { CheckCircle, XCircle, Eye, Target, Lightbulb, Loader2 } from "lucide-react";
import type { EvaluationResult } from "@/lib/types";
import { startEvaluation, getEvaluation, getEvaluationStatus } from "@/lib/api";
import { correctnessColor, correctnessBg } from "../utils";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { EvaluationVerdictCard } from "./EvaluationVerdictCard";
import { MissedFailurePointCard } from "./MissedFailurePointCard";

export function EvaluationSection({
  bundleId,
  expandedId,
  onToggle,
}: {
  bundleId: string;
  expandedId: string | null;
  onToggle: (id: string) => void;
}) {
  const [evalStatus, setEvalStatus] = useState<string>("not_started");
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  // Check initial status
  useEffect(() => {
    getEvaluationStatus(bundleId)
      .then((res) => {
        setEvalStatus(res.status);
        if (res.status === "complete") {
          getEvaluation(bundleId).then(setEvaluation).catch(() => {});
        }
      })
      .catch(() => {});
  }, [bundleId]);

  // Poll when evaluating
  useEffect(() => {
    if (evalStatus !== "evaluating") return;
    const interval = setInterval(async () => {
      try {
        const res = await getEvaluationStatus(bundleId);
        setEvalStatus(res.status);
        if (res.status === "complete") {
          const evalResult = await getEvaluation(bundleId);
          setEvaluation(evalResult);
        }
      } catch {
        // ignore polling errors
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [evalStatus, bundleId]);

  const handleStart = useCallback(async () => {
    setIsStarting(true);
    setErrorDetail(null);
    try {
      const res = await startEvaluation(bundleId);
      setEvalStatus(res.status);
    } catch (err: unknown) {
      setEvalStatus("error");
      // Extract error detail from API response
      if (err && typeof err === "object" && "message" in err) {
        setErrorDetail((err as { message: string }).message);
      } else if (err instanceof Error) {
        setErrorDetail(err.message);
      }
    } finally {
      setIsStarting(false);
    }
  }, [bundleId]);

  // Not started state
  if (evalStatus === "not_started") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-6"
      >
        <div className="flex items-center gap-3 mb-4">
          <div
            className="flex h-10 w-10 items-center justify-center rounded-xl flex-shrink-0"
            style={{ background: "rgba(99, 102, 241, 0.12)" }}
          >
            <Eye size={18} style={{ color: "var(--accent-light)" }} />
          </div>
          <div>
            <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
              Analysis Validation
            </h2>
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              Verify AI findings against hard evidence — purely deterministic
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {[
            "Verifies evidence citations exist & match",
            "Cross-references 11 triage scanner signals",
            "Checks deterministic root cause vs AI",
            "Finds critical signals no finding covers",
            "Recalculates confidence from evidence",
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded-lg" style={{ background: "rgba(0,0,0,0.2)", color: "var(--muted)" }}>
              <CheckCircle size={10} style={{ color: "var(--accent-light)", flexShrink: 0 }} />
              {item}
            </div>
          ))}
        </div>
        <button
          onClick={handleStart}
          disabled={isStarting}
          className="btn-primary text-sm"
          style={{ opacity: isStarting ? 0.6 : 1 }}
        >
          {isStarting ? "Validating..." : "Run Validation"}
        </button>
      </motion.div>
    );
  }

  // Evaluating state
  if (evalStatus === "evaluating") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-6"
      >
        <div className="flex items-center gap-3 mb-3">
          <Loader2 size={18} className="animate-spin" style={{ color: "var(--accent-light)" }} />
          <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
            Validating findings...
          </h2>
        </div>
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Verifying evidence citations, cross-referencing triage signals, and checking causal chain consistency.
        </p>
      </motion.div>
    );
  }

  // Error state
  if (evalStatus === "error") {
    const isBundleGone = errorDetail?.includes("no longer on disk") || errorDetail?.includes("re-upload");
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-6"
      >
        <div className="flex items-center gap-3 mb-3">
          <XCircle size={18} style={{ color: "var(--critical)" }} />
          <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
            {isBundleGone ? "Bundle No Longer Available" : "Validation Failed"}
          </h2>
        </div>
        <p className="text-sm mb-3" style={{ color: "var(--muted)" }}>
          {isBundleGone
            ? "The original bundle files are no longer on disk (server was restarted). Validation needs the raw bundle to verify evidence citations. Re-upload the bundle to run validation."
            : "The evaluation encountered an error. You can try again."}
        </p>
        {!isBundleGone && (
          <button
            onClick={handleStart}
            disabled={isStarting}
            className="px-4 py-2 rounded-lg text-sm font-medium transition-all hover:brightness-110 cursor-pointer"
            style={{ background: "var(--border-subtle)", color: "var(--foreground-bright)" }}
          >
            Retry Validation
          </button>
        )}
      </motion.div>
    );
  }

  // Complete state — show results
  if (!evaluation) return null;

  return (
    <div className="flex flex-col gap-4">
      {/* Overall Verdict Banner */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-5"
        style={{ borderLeft: `3px solid ${correctnessColor(evaluation.overall_correctness)}` }}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div
              className="flex h-10 w-10 items-center justify-center rounded-xl flex-shrink-0"
              style={{ background: `${correctnessColor(evaluation.overall_correctness)}18` }}
            >
              <Eye size={18} style={{ color: correctnessColor(evaluation.overall_correctness) }} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
                  Analysis Validation
                </h2>
                <span
                  className="text-xs font-semibold uppercase rounded-full px-2.5 py-0.5"
                  style={{
                    backgroundColor: correctnessBg(evaluation.overall_correctness),
                    color: correctnessColor(evaluation.overall_correctness),
                  }}
                >
                  {evaluation.overall_correctness}
                </span>
              </div>
            </div>
          </div>
          <ConfidenceMeter value={evaluation.overall_confidence} />
        </div>
        {evaluation.evaluation_summary && (
          <p className="text-sm" style={{ color: "var(--foreground)" }}>
            {evaluation.evaluation_summary}
          </p>
        )}
        {evaluation.cross_cutting_concerns?.length > 0 && (
          <div className="mt-2">
            <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--warning)" }}>
              Cross-Cutting Concerns
            </p>
            <ul className="list-disc list-inside">
              {evaluation.cross_cutting_concerns.map((c: string, i: number) => (
                <li key={i} className="text-xs" style={{ color: "var(--foreground)" }}>{c}</li>
              ))}
            </ul>
          </div>
        )}
        {evaluation.evaluation_duration_seconds > 0 && (
          <p className="mt-2 text-[10px]" style={{ color: "var(--muted)" }}>
            Evaluated in {evaluation.evaluation_duration_seconds.toFixed(1)}s
          </p>
        )}
      </motion.div>

      {/* Verdict Cards */}
      {evaluation.verdicts.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="glass-card p-5"
        >
          <div className="flex items-center gap-2 mb-3">
            <Target size={16} style={{ color: "var(--accent-light)" }} />
            <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
              Per-Finding Verdicts
            </h2>
            <span className="badge badge-muted text-[10px] ml-1">{evaluation.verdicts.length}</span>
          </div>
          <div className="flex flex-col">
            {evaluation.verdicts.map((v, i) => {
              const rowKey = `verdict-${i}`;
              return (
                <EvaluationVerdictCard
                  key={rowKey}
                  verdict={v}
                  isExpanded={expandedId === rowKey}
                  onToggle={() => onToggle(rowKey)}
                />
              );
            })}
          </div>
        </motion.div>
      )}

      {/* Missed Failure Points */}
      {evaluation.missed_failure_points.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card p-5"
          style={{ borderLeft: "3px solid var(--warning)" }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Lightbulb size={16} style={{ color: "var(--warning)" }} />
            <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
              Missed Failure Points
            </h2>
            <span className="badge badge-muted text-[10px] ml-1">{evaluation.missed_failure_points.length}</span>
          </div>
          <p className="text-xs mb-2" style={{ color: "var(--muted)" }}>
            Failure points found in the raw evidence that the main pipeline did not report:
          </p>
          <div className="flex flex-col">
            {evaluation.missed_failure_points.map((fp, i) => {
              const rowKey = `missed-${i}`;
              return (
                <MissedFailurePointCard
                  key={rowKey}
                  missed={fp}
                  isExpanded={expandedId === rowKey}
                  onToggle={() => onToggle(rowKey)}
                />
              );
            })}
          </div>
        </motion.div>
      )}
    </div>
  );
}
