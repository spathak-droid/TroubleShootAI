"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  Activity,
  Wrench,
  Zap,
  Target,
} from "lucide-react";
import { getAnalysis } from "@/lib/api";
import type {
  TroubleshootAnalyzerResult,
  PreflightCheckResult,
  ExternalAnalyzerIssue,
} from "@/lib/types";

import { buildAIFindings } from "../shared";
import type { DisplayFinding } from "../shared";
import {
  StatCard,
  VisualSummaryBar,
  AnalyzerResultRow,
  ExternalAsAnalyzerRow,
  PreflightResultRow,
} from "./components";

/* ── page ─────────────────────────────────────────────── */

export default function TroubleshootPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const bundleId = typeof id === "string" ? id : null;
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const toggle = (id: string) => setExpandedId((prev) => (prev === id ? null : id));

  const { data, isLoading, isError } = useQuery({
    queryKey: ["analysis", bundleId],
    queryFn: () => getAnalysis(bundleId!),
    enabled: !!bundleId,
    retry: 2,
  });

  if (!bundleId) return null;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center pt-32">
        <div className="flex items-center gap-3">
          <div className="h-5 w-5 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--accent-light)", borderTopColor: "transparent" }} />
          <p className="text-sm" style={{ color: "var(--muted)" }}>Loading troubleshoot data...</p>
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center justify-center pt-32">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card p-8 max-w-md text-center"
        >
          <AlertTriangle size={32} style={{ color: "var(--warning)", margin: "0 auto 12px" }} />
          <h2 className="text-lg font-semibold mb-2" style={{ color: "var(--foreground-bright)" }}>
            Analysis Not Available
          </h2>
          <p className="text-sm mb-4" style={{ color: "var(--muted)" }}>
            Could not load analysis data. The analysis may still be in progress, or you can re-upload the bundle to run a fresh analysis.
          </p>
          <Link
            href="/"
            className="btn-primary inline-block text-sm"
          >
            Back to Home
          </Link>
        </motion.div>
      </div>
    );
  }

  const raw = data as unknown as Record<string, unknown>;
  const triage = (raw?.triage ?? {}) as Record<string, unknown>;

  const tsAnalysis = triage.troubleshoot_analysis as {
    results: TroubleshootAnalyzerResult[];
    pass_count: number;
    warn_count: number;
    fail_count: number;
    has_results: boolean;
  } | undefined;

  const preflight = triage.preflight_report as {
    results: PreflightCheckResult[];
    pass_count: number;
    warn_count: number;
    fail_count: number;
  } | undefined | null;

  const externalIssues = (triage.external_analyzer_issues ?? []) as ExternalAnalyzerIssue[];
  const aiFindings = data ? buildAIFindings(raw) : [];

  const tsNames = new Set((tsAnalysis?.results ?? []).map((r) => (r.name ?? "").toLowerCase()));
  const unmatchedExternals = externalIssues.filter((ext) => !tsNames.has((ext.name ?? "").toLowerCase()));

  const extFail = unmatchedExternals.filter((e) => e.severity === "critical").length;
  const extWarn = unmatchedExternals.filter((e) => e.severity === "warning").length;
  const extInfo = unmatchedExternals.length - extFail - extWarn;
  const mergedPassCount = (tsAnalysis?.pass_count ?? 0) + extInfo;
  const mergedWarnCount = (tsAnalysis?.warn_count ?? 0) + extWarn;
  const mergedFailCount = (tsAnalysis?.fail_count ?? 0) + extFail;
  const totalChecks = mergedPassCount + mergedWarnCount + mergedFailCount;

  const usedFindingIds = new Set<string>();
  const findingForResult = (r: TroubleshootAnalyzerResult, _idx: number): DisplayFinding | undefined => {
    const words = `${r.title ?? ""} ${r.message ?? ""} ${r.name ?? ""}`.toLowerCase().split(/\s+/);
    let bestMatch: DisplayFinding | undefined;
    let bestScore = 0;
    for (const f of aiFindings) {
      if (usedFindingIds.has(f.id)) continue;
      const fWords = `${f.title} ${f.symptom} ${f.root_cause}`.toLowerCase().split(/\s+/);
      let score = 0;
      for (const w of words) {
        if (w.length > 3 && fWords.some((fw) => fw.includes(w))) score++;
      }
      if (score > bestScore) {
        bestScore = score;
        bestMatch = f;
      }
    }
    if (bestMatch && bestScore >= 2) {
      usedFindingIds.add(bestMatch.id);
      return bestMatch;
    }
    return undefined;
  };

  const hasTsOrExternal = tsAnalysis?.has_results || unmatchedExternals.length > 0;
  const hasAnything = hasTsOrExternal || (preflight && preflight.results.length > 0);

  return (
    <div className="flex flex-col gap-6">
      {/* Dashboard Header */}
      <motion.div
        className="dashboard-header"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        <h1
          className="text-lg font-semibold mr-auto"
          style={{ color: "var(--foreground-bright)" }}
        >
          Troubleshoot Findings
        </h1>
        <div className="filter-pill">
          <Wrench size={12} />
          Analyzers
        </div>
        {totalChecks > 0 && (
          <div className="filter-pill">
            <Activity size={12} />
            {totalChecks} Checks
          </div>
        )}
      </motion.div>

      {/* Stats Cards Row */}
      {hasAnything && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard label="Passed" value={mergedPassCount} color="var(--success)" icon={CheckCircle} />
          <StatCard label="Warnings" value={mergedWarnCount} color="var(--warning)" icon={AlertTriangle} />
          <StatCard label="Failures" value={mergedFailCount} color="var(--critical)" icon={XCircle} />
        </div>
      )}

      {!hasAnything && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card p-8 text-center"
        >
          <div
            className="flex h-14 w-14 items-center justify-center rounded-2xl mx-auto mb-4"
            style={{ background: "rgba(16, 185, 129, 0.1)" }}
          >
            <CheckCircle size={24} style={{ color: "var(--success)" }} />
          </div>
          <h2 className="text-base font-semibold mb-1" style={{ color: "var(--foreground-bright)" }}>
            No Troubleshoot Findings
          </h2>
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            This bundle does not contain troubleshoot.sh analyzer or preflight data.
          </p>
        </motion.div>
      )}

      {/* Analyzer Results */}
      {hasTsOrExternal && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card p-5"
        >
          <div className="flex items-center gap-2 mb-4">
            <Target size={16} style={{ color: "var(--accent-light)" }} />
            <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
              Analyzer Results
            </h2>
            <span className="badge badge-muted text-[10px] ml-1">
              {(tsAnalysis?.results?.length ?? 0) + unmatchedExternals.length}
            </span>
          </div>

          <div className="mb-4">
            <VisualSummaryBar
              pass_count={mergedPassCount}
              warn_count={mergedWarnCount}
              fail_count={mergedFailCount}
            />
          </div>

          <div className="flex flex-col">
            {tsAnalysis?.results.map((r, i) => {
              const rowKey = `ts-${i}`;
              return (
                <AnalyzerResultRow
                  key={rowKey}
                  result={r}
                  finding={findingForResult(r, i)}
                  isExpanded={expandedId === rowKey}
                  onToggle={() => toggle(rowKey)}
                  index={i}
                />
              );
            })}
            {unmatchedExternals.map((issue, i) => {
              const rowKey = `ext-${i}`;
              return (
                <ExternalAsAnalyzerRow
                  key={rowKey}
                  issue={issue}
                  isExpanded={expandedId === rowKey}
                  onToggle={() => toggle(rowKey)}
                  index={(tsAnalysis?.results?.length ?? 0) + i}
                />
              );
            })}
          </div>
        </motion.div>
      )}

      {/* Preflight Check Results */}
      {preflight && preflight.results.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card p-5"
        >
          <div className="flex items-center gap-2 mb-4">
            <Zap size={16} style={{ color: "var(--accent-light)" }} />
            <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
              Preflight Checks
            </h2>
            <span className="badge badge-muted text-[10px] ml-1">{preflight.results.length}</span>
          </div>

          <div className="mb-4">
            <VisualSummaryBar
              pass_count={preflight.pass_count}
              warn_count={preflight.warn_count}
              fail_count={preflight.fail_count}
            />
          </div>

          <div className="flex flex-col">
            {preflight.results.map((r, i) => (
              <PreflightResultRow key={`${r.name}-${i}`} result={r} index={i} />
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
