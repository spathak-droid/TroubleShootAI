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
  Search,
  X,
} from "lucide-react";
import { useDebounce } from "../hooks/useDebounce";
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
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedQuery = useDebounce(searchQuery, 300);

  const toggle = (id: string) => setExpandedId((prev) => (prev === id ? null : id));

  function matchesSearch(fields: (string | string[] | null | undefined)[]): boolean {
    if (!debouncedQuery) return true;
    const q = debouncedQuery.toLowerCase();
    return fields.some(f => {
      if (!f) return false;
      if (Array.isArray(f)) return f.some(line => line.toLowerCase().includes(q));
      return f.toLowerCase().includes(q);
    });
  }

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

  // Filtered data based on search query
  const fPodIssues = debouncedQuery ? podIssues.filter(p => matchesSearch([p.namespace, p.pod_name, p.issue_type, p.message, p.evidence_excerpt])) : podIssues;
  const fCrashContexts = debouncedQuery ? crashContexts.filter(c => matchesSearch([c.namespace, c.pod_name, c.crash_pattern, c.message, c.container_name, c.last_log_lines, c.previous_log_lines])) : crashContexts;
  const fEventEscalations = debouncedQuery ? eventEscalations.filter(e => matchesSearch([e.namespace, e.involved_object_name, e.message, e.event_reasons])) : eventEscalations;
  const fNodeIssues = debouncedQuery ? nodeIssues.filter(n => matchesSearch([n.node_name, n.condition, n.message])) : nodeIssues;
  const fDeploymentIssues = debouncedQuery ? deploymentIssues.filter(d => matchesSearch([d.namespace, d.name, d.issue])) : deploymentIssues;
  const fConfigIssues = debouncedQuery ? configIssues.filter(c => matchesSearch([c.namespace, c.resource_name, c.resource_type, c.referenced_by, c.issue])) : configIssues;
  const fDriftIssues = debouncedQuery ? driftIssues.filter(d => matchesSearch([d.namespace, d.resource_name, d.name, d.message, d.description, d.resource_type])) : driftIssues;
  const fRbacIssues = debouncedQuery ? rbacIssues.filter(r => matchesSearch([r.namespace, r.resource_type, r.error_message, r.suggested_permission])) : rbacIssues;
  const fQuotaIssues = debouncedQuery ? quotaIssues.filter(q => matchesSearch([q.namespace, q.resource_name, q.issue_type, q.message, q.resource_type])) : quotaIssues;
  const fNetworkPolicyIssues = debouncedQuery ? networkPolicyIssues.filter(n => matchesSearch([n.namespace, n.policy_name, n.issue_type, n.message])) : networkPolicyIssues;
  const fDnsIssues = debouncedQuery ? dnsIssues.filter(d => matchesSearch([d.namespace, d.resource_name, d.issue_type, d.message])) : dnsIssues;
  const fTlsIssues = debouncedQuery ? tlsIssues.filter(t => matchesSearch([t.namespace, t.resource_name, t.issue_type, t.message])) : tlsIssues;
  const fSchedulingIssues = debouncedQuery ? schedulingIssues.filter(s => matchesSearch([s.namespace, s.pod_name, s.issue_type, s.message])) : schedulingIssues;
  const fLogDiagnoses = debouncedQuery ? logDiagnoses.filter(l => matchesSearch([l.namespace, l.pod_name, l.diagnosis, l.key_log_line, l.root_cause_category])) : logDiagnoses;
  const fK8sEvents = debouncedQuery ? k8sEvents.filter(e => matchesSearch([e.namespace, e.reason, e.message, e.involved_object_name])) : k8sEvents;
  const fSilenceSignals = debouncedQuery ? silenceSignals.filter(s => matchesSearch([s.namespace, s.pod_name, s.signal_type, s.message, s.resource])) : silenceSignals;
  const fAiFindings = debouncedQuery ? aiFindings.filter(f => matchesSearch([f.title, f.root_cause, f.severity, f.symptom, f.category, ...f.evidence.map(e => e.content)])) : aiFindings;
  const fPodAnomalies = debouncedQuery ? podAnomalies.filter(a => matchesSearch([a.failing_pod, a.anomaly_type, a.description, a.comparison_group])) : podAnomalies;
  const fCoverageGaps = debouncedQuery ? coverageGaps.filter(g => matchesSearch([g.area, g.why_it_matters, g.data_path])) : coverageGaps;
  const fUncertaintyGaps = debouncedQuery ? uncertaintyGaps.filter(u => matchesSearch([u.area, u.question, u.description, u.reason, u.impact])) : uncertaintyGaps;

  const allFilteredEmpty = debouncedQuery && [
    fPodIssues, fCrashContexts, fEventEscalations, fNodeIssues,
    fDeploymentIssues, fConfigIssues, fDriftIssues, fRbacIssues,
    fQuotaIssues, fNetworkPolicyIssues, fDnsIssues, fTlsIssues,
    fSchedulingIssues, fLogDiagnoses, fK8sEvents, fSilenceSignals,
    fAiFindings, fPodAnomalies, fCoverageGaps, fUncertaintyGaps,
  ].every(arr => arr.length === 0);

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
          className="text-lg font-semibold"
          style={{ color: "var(--foreground-bright)" }}
        >
          Validation
        </h1>
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--muted)" }} />
          <input
            type="text"
            placeholder="Search findings, logs, events..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input-modern w-full pl-9 pr-8 py-2 text-sm rounded-lg"
            style={{
              background: "var(--glass-bg)",
              border: "1px solid var(--glass-border)",
              color: "var(--foreground-bright)",
              outline: "none",
            }}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 hover:opacity-80"
            >
              <X size={14} style={{ color: "var(--muted)" }} />
            </button>
          )}
        </div>
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

      {/* No results message */}
      {allFilteredEmpty && (
        <div className="glass-card p-8 text-center">
          <Search size={24} style={{ color: "var(--muted)", margin: "0 auto 8px" }} />
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            No findings match &ldquo;{debouncedQuery}&rdquo;
          </p>
        </div>
      )}

      {/* AI Findings */}
      <AIFindingsCard findings={fAiFindings} expandedId={expandedId} onToggle={toggle} />

      {/* Pod Issues (core triage) */}
      <PodIssuesSection issues={fPodIssues} />

      {/* Crash Loop Analysis */}
      <CrashLoopSection crashes={fCrashContexts} expandedId={expandedId} onToggle={toggle} />

      {/* Event Escalation Patterns */}
      <EventEscalationSection escalations={fEventEscalations} expandedId={expandedId} onToggle={toggle} />

      {/* Node Issues */}
      <NodeIssuesSection issues={fNodeIssues} />

      {/* Deployment Issues */}
      <DeploymentIssuesSection issues={fDeploymentIssues} />

      {/* What Changed Before Failures */}
      {changeReport && changeReport.correlations.length > 0 && (
        <ChangeCorrelationSection correlations={changeReport.correlations} />
      )}

      {/* Config Issues */}
      <ConfigIssuesSection issues={fConfigIssues} />

      {/* Drift Issues */}
      <DriftIssuesSection issues={fDriftIssues} />

      {/* RBAC / Permission Issues */}
      <RBACIssuesSection issues={fRbacIssues} />

      {/* Resource Quota Issues */}
      <QuotaIssuesSection issues={fQuotaIssues} />

      {/* Network Policy Issues */}
      <NetworkPolicySection issues={fNetworkPolicyIssues} />

      {/* DNS Issues */}
      <DNSIssuesSection issues={fDnsIssues} />

      {/* TLS / Certificate Issues */}
      <TLSIssuesSection issues={fTlsIssues} />

      {/* Scheduling Issues */}
      <SchedulingIssuesSection issues={fSchedulingIssues} />

      {/* AI Log Diagnoses */}
      {fLogDiagnoses.length > 0 && (
        <LogDiagnosesSection diagnoses={fLogDiagnoses} expandedId={expandedId} onToggle={toggle} />
      )}

      {/* Pod Anomaly Detection */}
      {fPodAnomalies.length > 0 && (
        <AnomalySection anomalies={fPodAnomalies} />
      )}

      {/* Broken Service Dependencies */}
      {dependencyMap && dependencyMap.broken_dependencies.length > 0 && (
        <DependencySection dependencyMap={dependencyMap} />
      )}

      {/* Warning Events */}
      <K8sEventsSection events={fK8sEvents} />

      {/* Silence Signals */}
      <SilenceSignalsSection signals={fSilenceSignals} />

      {/* Uncertainty & Gaps */}
      <UncertaintySection gaps={fUncertaintyGaps} />

      {/* Coverage Gaps */}
      <CoverageGapsSection gaps={fCoverageGaps} />
    </div>
  );
}
