import { STAGES } from "./constants";
import type { StageState, AnalysisSummary } from "./types";

export function buildStagesFromIndex(activeIdx: number, isComplete: boolean): StageState[] {
  return STAGES.map((_, i) => {
    if (isComplete || i < activeIdx) return { status: "complete" as const };
    if (i === activeIdx) return { status: "running" as const };
    return { status: "pending" as const };
  });
}

export function computeSummary(result: Record<string, unknown>): { summary: AnalysisSummary; total: number } {
  const findings = (result.findings ?? []) as Array<{ severity?: string }>;
  const triage = (result.triage ?? {}) as Record<string, unknown[]>;
  const criticalFindings = findings.filter((f) => f.severity === "critical").length;
  const warningFindings = findings.filter((f) => f.severity === "warning").length;
  const infoFindings = findings.filter((f) => f.severity === "info").length;
  const criticalPods = ((triage.critical_pods as unknown[]) ?? []).length;
  const warningPods = ((triage.warning_pods as unknown[]) ?? []).length;
  const nodeIssues = ((triage.node_issues as unknown[]) ?? []).length;
  const deployIssues = ((triage.deployment_issues as unknown[]) ?? []).length;
  const configIssues = ((triage.config_issues as unknown[]) ?? []).length;
  const crashLoops = ((triage.crash_contexts as unknown[]) ?? []).length;
  const escalations = ((triage.event_escalations as unknown[]) ?? []).length;
  const coverageGaps = ((triage.coverage_gaps as unknown[]) ?? []).length;
  const anomalies = ((triage.pod_anomalies as unknown[]) ?? []).length;
  const depMap = triage.dependency_map as unknown as Record<string, unknown> | undefined;
  const brokenDeps = ((depMap?.broken_dependencies as unknown[]) ?? []).length;
  const chgReport = triage.change_report as unknown as Record<string, unknown> | undefined;
  const changeCorrelations = ((chgReport?.correlations as unknown[]) ?? []).length;
  const logDiagnoses = ((result.log_diagnoses as unknown[]) ?? []).length;
  const summary = {
    critical: criticalFindings + criticalPods,
    warning: warningFindings + warningPods + nodeIssues,
    info: infoFindings + deployIssues + configIssues,
    crashLoops,
    escalations,
    coverageGaps,
    anomalies,
    brokenDeps,
    changeCorrelations,
    logDiagnoses,
  };
  return { summary, total: summary.critical + summary.warning + summary.info };
}
