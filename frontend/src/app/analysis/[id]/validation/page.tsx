"use client";

import { use, useState, useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  Brain,
  RotateCcw,
  TrendingUp,
  BarChart3,
  ShieldCheck,
  Search,
  X,
  Server,
  Settings,
  Globe,
  Clock,
  Eye,
  type LucideIcon,
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

type TabId = "root-cause" | "pods" | "infra" | "config" | "network" | "events" | "trust";

interface TabDef {
  id: TabId;
  label: string;
  icon: LucideIcon;
  color: string;
}

const TABS: TabDef[] = [
  { id: "root-cause", label: "Root Cause", icon: Brain, color: "#818cf8" },
  { id: "pods", label: "Pods", icon: AlertTriangle, color: "#f87171" },
  { id: "infra", label: "Infrastructure", icon: Server, color: "#fbbf24" },
  { id: "config", label: "Configuration", icon: Settings, color: "#e879f9" },
  { id: "network", label: "Network", icon: Globe, color: "#22d3ee" },
  { id: "events", label: "Events", icon: Clock, color: "#f59e0b" },
  { id: "trust", label: "Trust & Gaps", icon: Eye, color: "#6ee7b7" },
];

export default function ValidationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const bundleId = typeof id === "string" ? id : null;
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("root-cause");
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

  // Extract all data from the response
  const {
    raw, triage, crashContexts, eventEscalations, rbacIssues, quotaIssues,
    networkPolicyIssues, coverageGaps, podAnomalies, dependencyMap, changeReport,
    logDiagnoses, aiFindings, podIssues, nodeIssues, deploymentIssues, configIssues,
    driftIssues, silenceSignals, k8sEvents, dnsIssues, tlsIssues, schedulingIssues,
    uncertaintyGaps, hypotheses,
  } = useMemo(() => {
    if (!data) return {
      raw: {} as Record<string, unknown>, triage: {} as Record<string, unknown>,
      crashContexts: [], eventEscalations: [], rbacIssues: [], quotaIssues: [],
      networkPolicyIssues: [], coverageGaps: [], podAnomalies: [],
      dependencyMap: null, changeReport: null, logDiagnoses: [], aiFindings: [],
      podIssues: [], nodeIssues: [], deploymentIssues: [], configIssues: [],
      driftIssues: [], silenceSignals: [], k8sEvents: [], dnsIssues: [],
      tlsIssues: [], schedulingIssues: [], uncertaintyGaps: [], hypotheses: [],
    };

    const raw = data as unknown as Record<string, unknown>;
    const triage = (raw?.triage ?? {}) as Record<string, unknown>;

    const criticalPods = ((triage.critical_pods ?? []) as PodIssue[]).map(p => ({
      ...p, severity: (p.severity ?? "critical") as PodIssue["severity"],
    }));
    const warningPods = ((triage.warning_pods ?? []) as PodIssue[]).map(p => ({
      ...p, severity: (p.severity ?? "warning") as PodIssue["severity"],
    }));

    return {
      raw,
      triage,
      crashContexts: (triage.crash_contexts ?? []) as CrashLoopContext[],
      eventEscalations: (triage.event_escalations ?? []) as EventEscalation[],
      rbacIssues: (triage.rbac_issues ?? []) as RBACIssue[],
      quotaIssues: (triage.quota_issues ?? []) as QuotaIssue[],
      networkPolicyIssues: (triage.network_policy_issues ?? []) as NetworkPolicyIssue[],
      coverageGaps: (triage.coverage_gaps ?? []) as CoverageGap[],
      podAnomalies: (triage.pod_anomalies ?? []) as PodAnomaly[],
      dependencyMap: (triage.dependency_map ?? null) as DependencyMap | null,
      changeReport: (triage.change_report ?? null) as ChangeReport | null,
      logDiagnoses: (raw.log_diagnoses ?? []) as LogDiagnosis[],
      aiFindings: buildAIFindings(raw),
      podIssues: [...criticalPods, ...warningPods] as PodIssue[],
      nodeIssues: (triage.node_issues ?? []) as NodeIssue[],
      deploymentIssues: (triage.deployment_issues ?? []) as DeploymentIssue[],
      configIssues: (triage.config_issues ?? []) as ConfigIssue[],
      driftIssues: (triage.drift_issues ?? []) as DriftIssue[],
      silenceSignals: (triage.silence_signals ?? []) as SilenceSignal[],
      k8sEvents: (triage.warning_events ?? triage.events ?? []) as K8sEvent[],
      dnsIssues: (triage.dns_issues ?? []) as DNSIssue[],
      tlsIssues: (triage.tls_issues ?? []) as TLSIssue[],
      schedulingIssues: (triage.scheduling_issues ?? []) as SchedulingIssue[],
      uncertaintyGaps: (raw.uncertainty_gaps ?? raw.uncertainty ?? []) as UncertaintyGap[],
      hypotheses: (raw.hypotheses ?? []) as Hypothesis[],
    };
  }, [data]);

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

  // Tab counts
  const tabCounts: Record<TabId, number> = useMemo(() => ({
    "root-cause": aiFindings.length + hypotheses.length,
    "pods": podIssues.length + crashContexts.length + logDiagnoses.length + podAnomalies.length,
    "infra": nodeIssues.length + deploymentIssues.length + schedulingIssues.length + quotaIssues.length,
    "config": configIssues.length + driftIssues.length + rbacIssues.length,
    "network": networkPolicyIssues.length + dnsIssues.length + tlsIssues.length
      + (dependencyMap?.broken_dependencies?.length ?? 0),
    "events": k8sEvents.length + eventEscalations.length
      + (changeReport?.correlations?.length ?? 0),
    "trust": uncertaintyGaps.length + coverageGaps.length + silenceSignals.length,
  }), [
    aiFindings, hypotheses, podIssues, crashContexts, logDiagnoses, podAnomalies,
    nodeIssues, deploymentIssues, schedulingIssues, quotaIssues, configIssues,
    driftIssues, rbacIssues, networkPolicyIssues, dnsIssues, tlsIssues,
    dependencyMap, k8sEvents, eventEscalations, changeReport, uncertaintyGaps,
    coverageGaps, silenceSignals,
  ]);

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
          <Link href="/" className="btn-primary inline-block text-sm">
            Back to Home
          </Link>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Header with search */}
      <motion.div
        className="dashboard-header"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        <h1 className="text-lg font-semibold" style={{ color: "var(--foreground-bright)" }}>
          Validation
        </h1>
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 z-10 -translate-y-1/2" style={{ color: "var(--foreground)", opacity: 0.5 }} />
          <input
            type="text"
            placeholder="Search findings, logs, events..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-8 py-2 text-sm rounded-lg transition-colors focus:border-[var(--accent-light)]"
            style={{
              background: "var(--glass-bg)",
              border: "1px solid rgba(99, 102, 241, 0.35)",
              color: "var(--foreground-bright)",
              outline: "none",
            }}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 z-10 -translate-y-1/2 hover:opacity-80"
            >
              <X size={14} style={{ color: "var(--foreground)", opacity: 0.5 }} />
            </button>
          )}
        </div>
        <div className="filter-pill">
          <ShieldCheck size={12} />
          Evidence-Based
        </div>
      </motion.div>

      {/* Tab Navigation — hidden when searching */}
      {!debouncedQuery && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide"
          style={{ WebkitOverflowScrolling: "touch" }}
        >
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            const count = tabCounts[tab.id];
            return (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id); setExpandedId(null); }}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all whitespace-nowrap cursor-pointer"
                style={{
                  background: isActive ? `${tab.color}18` : "var(--glass-bg)",
                  border: isActive ? `1px solid ${tab.color}40` : "1px solid rgba(255,255,255,0.08)",
                  color: isActive ? tab.color : "var(--muted)",
                }}
              >
                <tab.icon size={14} />
                {tab.label}
                {count > 0 && (
                  <span
                    className="text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1"
                    style={{
                      background: isActive ? `${tab.color}30` : "rgba(255,255,255,0.08)",
                      color: isActive ? tab.color : "var(--muted)",
                    }}
                  >
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </motion.div>
      )}

      {/* When searching: show ALL matching results across all tabs */}
      {debouncedQuery ? (
        <motion.div
          key="search-results"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col gap-5"
        >
          {/* Check if anything matches */}
          {[fAiFindings, fPodIssues, fCrashContexts, fEventEscalations, fNodeIssues,
            fDeploymentIssues, fConfigIssues, fDriftIssues, fRbacIssues,
            fQuotaIssues, fNetworkPolicyIssues, fDnsIssues, fTlsIssues,
            fSchedulingIssues, fLogDiagnoses, fK8sEvents, fSilenceSignals,
            fPodAnomalies, fCoverageGaps, fUncertaintyGaps,
          ].every(arr => arr.length === 0) ? (
            <div className="glass-card p-8 text-center">
              <Search size={24} style={{ color: "var(--muted)", margin: "0 auto 8px" }} />
              <p className="text-sm" style={{ color: "var(--muted)" }}>
                No findings match &ldquo;{debouncedQuery}&rdquo;
              </p>
            </div>
          ) : (
            <>
              <AIFindingsCard findings={fAiFindings} expandedId={expandedId} onToggle={toggle} />
              <PodIssuesSection issues={fPodIssues} />
              <CrashLoopSection crashes={fCrashContexts} expandedId={expandedId} onToggle={toggle} />
              <NodeIssuesSection issues={fNodeIssues} />
              <DeploymentIssuesSection issues={fDeploymentIssues} />
              <ConfigIssuesSection issues={fConfigIssues} />
              <DriftIssuesSection issues={fDriftIssues} />
              <RBACIssuesSection issues={fRbacIssues} />
              <QuotaIssuesSection issues={fQuotaIssues} />
              <NetworkPolicySection issues={fNetworkPolicyIssues} />
              <DNSIssuesSection issues={fDnsIssues} />
              <TLSIssuesSection issues={fTlsIssues} />
              <SchedulingIssuesSection issues={fSchedulingIssues} />
              <EventEscalationSection escalations={fEventEscalations} expandedId={expandedId} onToggle={toggle} />
              <K8sEventsSection events={fK8sEvents} />
              {fLogDiagnoses.length > 0 && (
                <LogDiagnosesSection diagnoses={fLogDiagnoses} expandedId={expandedId} onToggle={toggle} />
              )}
              {fPodAnomalies.length > 0 && (
                <AnomalySection anomalies={fPodAnomalies} />
              )}
              <SilenceSignalsSection signals={fSilenceSignals} />
              <UncertaintySection gaps={fUncertaintyGaps} />
              <CoverageGapsSection gaps={fCoverageGaps} />
            </>
          )}
        </motion.div>
      ) : (
        /* When NOT searching: show only active tab content */
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col gap-5"
          >
            {/* ROOT CAUSE TAB */}
            {activeTab === "root-cause" && (
              <>
                <EvaluationSection bundleId={bundleId} expandedId={expandedId} onToggle={toggle} />
                <RootCauseSummary hypotheses={hypotheses} />
                <AIFindingsCard findings={fAiFindings} expandedId={expandedId} onToggle={toggle} />
                {fAiFindings.length === 0 && hypotheses.length === 0 && (
                  <EmptyTabMessage message="No AI findings or hypotheses generated for this bundle." />
                )}
              </>
            )}

            {/* PODS TAB */}
            {activeTab === "pods" && (
              <>
                <PodIssuesSection issues={fPodIssues} />
                <CrashLoopSection crashes={fCrashContexts} expandedId={expandedId} onToggle={toggle} />
                {fLogDiagnoses.length > 0 && (
                  <LogDiagnosesSection diagnoses={fLogDiagnoses} expandedId={expandedId} onToggle={toggle} />
                )}
                {fPodAnomalies.length > 0 && (
                  <AnomalySection anomalies={fPodAnomalies} />
                )}
                {fPodIssues.length === 0 && fCrashContexts.length === 0 && fLogDiagnoses.length === 0 && fPodAnomalies.length === 0 && (
                  <EmptyTabMessage message="No pod issues detected in this bundle." />
                )}
              </>
            )}

            {/* INFRASTRUCTURE TAB */}
            {activeTab === "infra" && (
              <>
                <NodeIssuesSection issues={fNodeIssues} />
                <DeploymentIssuesSection issues={fDeploymentIssues} />
                <SchedulingIssuesSection issues={fSchedulingIssues} />
                <QuotaIssuesSection issues={fQuotaIssues} />
                {fNodeIssues.length === 0 && fDeploymentIssues.length === 0 && fSchedulingIssues.length === 0 && fQuotaIssues.length === 0 && (
                  <EmptyTabMessage message="No infrastructure issues detected." />
                )}
              </>
            )}

            {/* CONFIGURATION TAB */}
            {activeTab === "config" && (
              <>
                <ConfigIssuesSection issues={fConfigIssues} />
                <DriftIssuesSection issues={fDriftIssues} />
                <RBACIssuesSection issues={fRbacIssues} />
                {fConfigIssues.length === 0 && fDriftIssues.length === 0 && fRbacIssues.length === 0 && (
                  <EmptyTabMessage message="No configuration issues detected." />
                )}
              </>
            )}

            {/* NETWORK TAB */}
            {activeTab === "network" && (
              <>
                <NetworkPolicySection issues={fNetworkPolicyIssues} />
                <DNSIssuesSection issues={fDnsIssues} />
                <TLSIssuesSection issues={fTlsIssues} />
                {dependencyMap && dependencyMap.broken_dependencies.length > 0 && (
                  <DependencySection dependencyMap={dependencyMap} />
                )}
                {fNetworkPolicyIssues.length === 0 && fDnsIssues.length === 0 && fTlsIssues.length === 0 && !(dependencyMap && dependencyMap.broken_dependencies.length > 0) && (
                  <EmptyTabMessage message="No network issues detected." />
                )}
              </>
            )}

            {/* EVENTS TAB */}
            {activeTab === "events" && (
              <>
                <EventEscalationSection escalations={fEventEscalations} expandedId={expandedId} onToggle={toggle} />
                {changeReport && changeReport.correlations.length > 0 && (
                  <ChangeCorrelationSection correlations={changeReport.correlations} />
                )}
                <K8sEventsSection events={fK8sEvents} />
                {fEventEscalations.length === 0 && fK8sEvents.length === 0 && !(changeReport && changeReport.correlations.length > 0) && (
                  <EmptyTabMessage message="No warning events or escalation patterns found." />
                )}
              </>
            )}

            {/* TRUST & GAPS TAB */}
            {activeTab === "trust" && (
              <>
                <UncertaintySection gaps={fUncertaintyGaps} />
                <CoverageGapsSection gaps={fCoverageGaps} />
                <SilenceSignalsSection signals={fSilenceSignals} />
                {fUncertaintyGaps.length === 0 && fCoverageGaps.length === 0 && fSilenceSignals.length === 0 && (
                  <EmptyTabMessage message="No gaps or uncertainty signals detected." />
                )}
              </>
            )}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}

function EmptyTabMessage({ message }: { message: string }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="glass-card p-10 text-center"
    >
      <ShieldCheck size={28} style={{ color: "var(--success, #6ee7b7)", margin: "0 auto 10px" }} />
      <p className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
        {message}
      </p>
      <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
        This is good news — nothing to investigate here.
      </p>
    </motion.div>
  );
}
