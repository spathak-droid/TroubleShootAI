"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  RotateCcw,
  TrendingUp,
  EyeOff,
  AlertTriangle,
  GitBranch,
  Sparkles,
  FileText,
  Download,
} from "lucide-react";
import { exportJson, exportHtml } from "@/lib/api";
import type { AnalysisSummary } from "../types";

export function SummaryCards({ summary, bundleId }: { summary: AnalysisSummary; bundleId: string }) {
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExport = async (fn: (id: string) => Promise<void>) => {
    setExportError(null);
    try {
      await fn(bundleId);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    }
  };

  const cards = [
    { label: "Crash Loops", count: summary.crashLoops, icon: RotateCcw, color: "var(--critical)" },
    { label: "Escalations", count: summary.escalations, icon: TrendingUp, color: "var(--warning)" },
    { label: "Coverage Gaps", count: summary.coverageGaps, icon: EyeOff, color: "#f59e0b" },
    { label: "Broken Deps", count: summary.brokenDeps, icon: AlertTriangle, color: "var(--critical)" },
    { label: "Change Correlations", count: summary.changeCorrelations, icon: GitBranch, color: "var(--accent-light)" },
    { label: "AI Log Diagnoses", count: summary.logDiagnoses, icon: Sparkles, color: "#a78bfa" },
  ].filter((c) => c.count > 0);

  return (
    <motion.div
      className="grid grid-cols-12 gap-4"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.5 }}
    >
      {/* Severity breakdown */}
      <div className="col-span-8 glass-card p-5">
        <h3
          className="mb-4 text-xs font-medium uppercase tracking-wider"
          style={{ color: "var(--muted)" }}
        >
          Findings Breakdown
        </h3>
        <div className="severity-bar mb-5">
          <div className="severity-item">
            <div className="severity-dot" style={{ background: "var(--critical)" }} />
            <span className="count" style={{ color: "var(--critical)" }}>{summary.critical}</span>
            <span className="sev-label">Critical</span>
          </div>
          <div className="severity-item">
            <div className="severity-dot" style={{ background: "var(--warning)" }} />
            <span className="count" style={{ color: "var(--warning)" }}>{summary.warning}</span>
            <span className="sev-label">Warning</span>
          </div>
          <div className="severity-item">
            <div className="severity-dot" style={{ background: "var(--info)" }} />
            <span className="count">{summary.info}</span>
            <span className="sev-label">Info</span>
          </div>
        </div>

        {cards.length > 0 && (
          <div className="findings-grid">
            {cards.map((card) => (
              <div key={card.label} className="finding-card">
                <card.icon size={16} style={{ color: card.color, flexShrink: 0 }} />
                <div>
                  <span className="fc-count" style={{ color: card.color }}>{card.count}</span>
                  <span className="fc-label ml-2">{card.label}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Export */}
      <div className="col-span-4 glass-card p-5 flex flex-col">
        <h3
          className="mb-3 text-xs font-medium uppercase tracking-wider"
          style={{ color: "var(--muted)" }}
        >
          Export Report
        </h3>
        {exportError && (
          <p className="mb-2 text-xs" style={{ color: "var(--critical)" }}>
            {exportError}
          </p>
        )}
        <div className="flex flex-col gap-2 mt-auto">
          <button
            onClick={() => handleExport(exportHtml)}
            className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium transition-all"
            style={{
              background: "var(--accent-gradient)",
              color: "white",
              boxShadow: "0 0 20px rgba(99, 102, 241, 0.2)",
            }}
          >
            <FileText size={14} />
            HTML Report
          </button>
          <button
            onClick={() => handleExport(exportJson)}
            className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm transition-all"
            style={{
              background: "transparent",
              color: "var(--foreground)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <Download size={14} />
            JSON Data
          </button>
        </div>
      </div>
    </motion.div>
  );
}
