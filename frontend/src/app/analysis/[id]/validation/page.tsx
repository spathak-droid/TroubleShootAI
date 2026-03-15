"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  Brain,
  RotateCcw,
  TrendingUp,
  BarChart3,
  GitCompare,
  ShieldCheck,
  Layers,
} from "lucide-react";
import { getAnalysis } from "@/lib/api";
import { buildAIFindings } from "../shared";
import type {
  CrashLoopContext,
  EventEscalation,
  RBACIssue,
  QuotaIssue,
  NetworkPolicyIssue,
  CoverageGap,
  LogDiagnosis,
  PodAnomaly,
  DependencyMap,
  ChangeReport,
  PodIssue,
  NodeIssue,
  DeploymentIssue,
  ConfigIssue,
  DriftIssue,
  SilenceSignal,
  K8sEvent,
  UncertaintyGap,
  DNSIssue,
  TLSIssue,
  SchedulingIssue,
  Hypothesis,
} from "@/lib/types";
import {
  AIFindingsCard,
  EvaluationSection,
  CrashLoopSection,
  EventEscalationSection,
  RBACIssuesSection,
  QuotaIssuesSection,
  NetworkPolicySection,
  CoverageGapsSection,
  LogDiagnosesSection,
  AnomalySection,
  DependencySection,
  ChangeCorrelationSection,
  PodIssuesSection,
  NodeIssuesSection,
  DeploymentIssuesSection,
  ConfigIssuesSection,
  DriftIssuesSection,
  SilenceSignalsSection,
  K8sEventsSection,
  UncertaintySection,
  DNSIssuesSection,
  TLSIssuesSection,
  SchedulingIssuesSection,
} from "./components";
import { RootCauseSummary } from "../components/RootCauseSummary";

export default function ValidationPage({
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
    retry: false,
  });

  if (!bundleId) return null;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center pt-32">
        <div className="flex items-center gap-3">
          <div className="h-5 w-5 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--accent-light)", borderTopColor: "transparent" }} />
          <p className="text-sm" style={{ color: "var(--muted)" }}>Loading validation data...</p>
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
            This bundle&apos;s analysis data is no longer in memory. This happens when the server restarts.
            Please go back and re-run the analysis.
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

  const crashContexts = (triage.crash_contexts ?? []) as CrashLoopContext[];
  const eventEscalations = (triage.event_escalations ?? []) as EventEscalation[];
  const rbacIssues = (triage.rbac_issues ?? []) as RBACIssue[];
  const quotaIssues = (triage.quota_issues ?? []) as QuotaIssue[];
  const networkPolicyIssues = (triage.network_policy_issues ?? []) as NetworkPolicyIssue[];
  const coverageGaps = (triage.coverage_gaps ?? []) as CoverageGap[];
  const podAnomalies = (triage.pod_anomalies ?? []) as PodAnomaly[];
  const dependencyMap = (triage.dependency_map ?? null) as DependencyMap | null;
  const changeReport = (triage.change_report ?? null) as ChangeReport | null;
  const logDiagnoses = ((raw.log_diagnoses ?? []) as LogDiagnosis[]);
  const aiFindings = data ? buildAIFindings(raw) : [];

  // Core triage data (backend uses critical_pods + warning_pods, not pod_issues)
  const criticalPods = ((triage.critical_pods ?? []) as PodIssue[]).map(p => ({ ...p, severity: (p.severity ?? "critical") as PodIssue["severity"] }));
  const warningPods = ((triage.warning_pods ?? []) as PodIssue[]).map(p => ({ ...p, severity: (p.severity ?? "warning") as PodIssue["severity"] }));
  const podIssues = [...criticalPods, ...warningPods];
  const nodeIssues = (triage.node_issues ?? []) as NodeIssue[];
  const deploymentIssues = (triage.deployment_issues ?? []) as DeploymentIssue[];
  const configIssues = (triage.config_issues ?? []) as ConfigIssue[];
  const driftIssues = (triage.drift_issues ?? []) as DriftIssue[];
  const silenceSignals = (triage.silence_signals ?? []) as SilenceSignal[];
  const k8sEvents = (triage.warning_events ?? triage.events ?? []) as K8sEvent[];

  // New scanner data
  const dnsIssues = (triage.dns_issues ?? []) as DNSIssue[];
  const tlsIssues = (triage.tls_issues ?? []) as TLSIssue[];
  const schedulingIssues = (triage.scheduling_issues ?? []) as SchedulingIssue[];

  // AI analysis data
  const uncertaintyGaps = (raw.uncertainty_gaps ?? raw.uncertainty ?? []) as UncertaintyGap[];
  const hypotheses = (raw.hypotheses ?? []) as Hypothesis[];

  // Count active sections for the overview
  const sectionCounts = [
    { label: "AI Findings", count: aiFindings.length, icon: Brain, color: "var(--accent-light)" },
    { label: "Pod Issues", count: podIssues.length, icon: AlertTriangle, color: "var(--critical)" },
    { label: "Crash Loops", count: crashContexts.length, icon: RotateCcw, color: "var(--critical)" },
    { label: "Escalations", count: eventEscalations.length, icon: TrendingUp, color: "var(--warning)" },
    { label: "Node Issues", count: nodeIssues.length, icon: BarChart3, color: "var(--warning)" },
    { label: "Drift Issues", count: driftIssues.length, icon: GitCompare, color: "#e879f9" },
  ].filter(s => s.count > 0);

  const totalSections = [
    podIssues, crashContexts, eventEscalations, nodeIssues,
    deploymentIssues, configIssues, driftIssues, rbacIssues,
    quotaIssues, networkPolicyIssues, logDiagnoses, podAnomalies,
    silenceSignals, coverageGaps, uncertaintyGaps, k8sEvents,
  ].filter(arr => arr.length > 0).length
    + (dependencyMap && dependencyMap.broken_dependencies.length > 0 ? 1 : 0)
    + (changeReport && changeReport.correlations.length > 0 ? 1 : 0);

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
          Validation
        </h1>
        <div className="filter-pill">
          <ShieldCheck size={12} />
          Evidence-Based
        </div>
        <div className="filter-pill">
          <Layers size={12} />
          {totalSections + (aiFindings.length > 0 ? 1 : 0)} Sections
        </div>
      </motion.div>

      {/* Quick Stats Overview */}
      {sectionCounts.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid gap-3"
          style={{ gridTemplateColumns: `repeat(${Math.min(sectionCounts.length, 4)}, 1fr)` }}
        >
          {sectionCounts.slice(0, 4).map((stat) => (
            <div key={stat.label} className="glass-card p-4 flex items-center gap-3">
              <div
                className="flex h-9 w-9 items-center justify-center rounded-xl flex-shrink-0"
                style={{ background: `${stat.color}18` }}
              >
                <stat.icon size={16} style={{ color: stat.color }} />
              </div>
              <div>
                <p className="text-xl font-bold" style={{ color: stat.color }}>{stat.count}</p>
                <p className="text-[10px] uppercase tracking-wider" style={{ color: "var(--muted)" }}>{stat.label}</p>
              </div>
            </div>
          ))}
        </motion.div>
      )}

      {/* Independent Evaluation */}
      <EvaluationSection bundleId={bundleId} expandedId={expandedId} onToggle={toggle} />

      {/* Root Cause Hypotheses */}
      <RootCauseSummary hypotheses={hypotheses} />

      {/* AI Findings */}
      <AIFindingsCard findings={aiFindings} expandedId={expandedId} onToggle={toggle} />

      {/* Pod Issues (core triage) */}
      <PodIssuesSection issues={podIssues} />

      {/* Crash Loop Analysis */}
      <CrashLoopSection crashes={crashContexts} expandedId={expandedId} onToggle={toggle} />

      {/* Event Escalation Patterns */}
      <EventEscalationSection escalations={eventEscalations} expandedId={expandedId} onToggle={toggle} />

      {/* Node Issues */}
      <NodeIssuesSection issues={nodeIssues} />

      {/* Deployment Issues */}
      <DeploymentIssuesSection issues={deploymentIssues} />

      {/* What Changed Before Failures */}
      {changeReport && changeReport.correlations.length > 0 && (
        <ChangeCorrelationSection correlations={changeReport.correlations} />
      )}

      {/* Config Issues */}
      <ConfigIssuesSection issues={configIssues} />

      {/* Drift Issues */}
      <DriftIssuesSection issues={driftIssues} />

      {/* RBAC / Permission Issues */}
      <RBACIssuesSection issues={rbacIssues} />

      {/* Resource Quota Issues */}
      <QuotaIssuesSection issues={quotaIssues} />

      {/* Network Policy Issues */}
      <NetworkPolicySection issues={networkPolicyIssues} />

      {/* DNS Issues */}
      <DNSIssuesSection issues={dnsIssues} />

      {/* TLS / Certificate Issues */}
      <TLSIssuesSection issues={tlsIssues} />

      {/* Scheduling Issues */}
      <SchedulingIssuesSection issues={schedulingIssues} />

      {/* AI Log Diagnoses */}
      {logDiagnoses.length > 0 && (
        <LogDiagnosesSection diagnoses={logDiagnoses} expandedId={expandedId} onToggle={toggle} />
      )}

      {/* Pod Anomaly Detection */}
      {podAnomalies.length > 0 && (
        <AnomalySection anomalies={podAnomalies} />
      )}

      {/* Broken Service Dependencies */}
      {dependencyMap && dependencyMap.broken_dependencies.length > 0 && (
        <DependencySection dependencyMap={dependencyMap} />
      )}

      {/* Warning Events */}
      <K8sEventsSection events={k8sEvents} />

      {/* Silence Signals */}
      <SilenceSignalsSection signals={silenceSignals} />

      {/* Uncertainty & Gaps */}
      <UncertaintySection gaps={uncertaintyGaps} />

      {/* Coverage Gaps */}
      <CoverageGapsSection gaps={coverageGaps} />
    </div>
  );
}
