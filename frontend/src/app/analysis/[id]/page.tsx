"use client";

import { use } from "react";
import { motion } from "framer-motion";
import {
  Loader2,
  CheckCircle,
  XCircle,
  Sparkles,
  Activity,
  Database,
} from "lucide-react";
import { STAGES } from "./constants";
import { FlowVisualization, PipelineStepper, SummaryCards } from "./components";
import { useAnalysisWebSocket } from "./hooks";

export default function AnalysisPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const bundleId = typeof id === "string" ? id : null;

  const {
    pageState,
    stages,
    progress,
    message,
    findingsCount,
    summary,
    handleStart,
  } = useAnalysisWebSocket(bundleId);

  if (!bundleId) return null;

  // Loading state
  if (pageState === "loading") {
    return (
      <div className="flex items-center justify-center pt-32">
        <Loader2
          size={24}
          className="animate-spin"
          style={{ color: "var(--accent-light)" }}
        />
      </div>
    );
  }

  // Ready to start
  if (pageState === "ready") {
    return (
      <div className="flex flex-col items-center justify-center gap-6 pt-32">
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ease: [0.22, 1, 0.36, 1] }}
          className="flex flex-col items-center gap-5"
        >
          <div
            className="flex h-14 w-14 items-center justify-center rounded-2xl"
            style={{ background: "var(--accent-gradient)", boxShadow: "0 0 30px rgba(99, 102, 241, 0.25)" }}
          >
            <Sparkles size={24} color="white" />
          </div>
          <h2
            className="text-2xl font-bold"
            style={{ color: "var(--foreground-bright)" }}
          >
            Ready to Analyze
          </h2>
          <p className="text-xs font-mono" style={{ color: "var(--muted)" }}>
            {bundleId}
          </p>
          <button
            onClick={handleStart}
            className="btn-primary flex items-center gap-2"
          >
            <Sparkles size={16} />
            Start Analysis
          </button>
        </motion.div>
      </div>
    );
  }

  // Running / Complete / Failed
  const isDone = pageState === "complete";
  const isFailed = pageState === "failed";
  const isRunning = pageState === "running";

  return (
    <div className="flex flex-col gap-6">
      {/* Header with filter pills */}
      <motion.div
        className="dashboard-header"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        <h1
          className="text-lg font-semibold mr-auto"
          style={{ color: "var(--foreground-bright)" }}
        >
          Dashboard
        </h1>
        <div className="filter-pill">
          <Activity size={12} />
          {isDone ? "Complete" : isFailed ? "Failed" : "Analyzing"}
        </div>
        <div className="filter-pill">
          <Database size={12} />
          Bundle: {bundleId.slice(0, 8)}
        </div>
      </motion.div>

      {/* Progress bar (compact) */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="glass-card p-4"
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {isRunning && <Loader2 size={14} className="animate-spin" style={{ color: "var(--accent-light)" }} />}
            {isDone && <CheckCircle size={14} style={{ color: "var(--success)" }} />}
            {isFailed && <XCircle size={14} style={{ color: "var(--critical)" }} />}
            <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
              {isDone ? "Analysis Complete" : isFailed ? "Analysis Failed" : "Analyzing Bundle..."}
            </span>
          </div>
          <span
            className="text-sm font-mono font-medium"
            style={{ color: isDone ? "var(--success)" : isFailed ? "var(--critical)" : "var(--accent-light)" }}
          >
            {Math.round(progress)}%
          </span>
        </div>
        <div className="progress-bar">
          <motion.div
            className="progress-fill"
            style={{
              background: isFailed ? "var(--critical)" : "var(--accent-gradient)",
            }}
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      </motion.div>

      {/* Flow visualization */}
      <motion.div
        className="glass-card p-6"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <FlowVisualization
          isDone={isDone}
          isRunning={isRunning}
          progress={progress}
          summary={summary}
          findingsCount={findingsCount}
          message={message}
        />
      </motion.div>

      {/* Pipeline stepper */}
      <PipelineStepper stages={stages} />

      {/* Summary cards (only when complete) */}
      {isDone && summary && (
        <SummaryCards summary={summary} bundleId={bundleId} />
      )}

      {/* Failed retry */}
      {isFailed && (
        <motion.div
          className="glass-card p-5 flex items-center gap-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <XCircle size={20} style={{ color: "var(--critical)" }} />
          <div className="flex-1">
            <p className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
              Analysis failed
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>{message}</p>
          </div>
          <button onClick={handleStart} className="btn-primary text-sm py-2 px-4">
            Retry
          </button>
        </motion.div>
      )}
    </div>
  );
}
