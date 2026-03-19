// ─── Triage models ───────────────────────────────────────────────

export interface PodIssue {
  pod_name: string;
  namespace: string;
  issue_type: string;
  severity: "critical" | "warning" | "info";
  message: string;
  container?: string;
  container_name?: string;  // backend field name
  restart_count?: number;
  exit_code?: number;
  timestamp?: string;
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface NodeIssue {
  node_name: string;
  issue_type: string;
  severity: "critical" | "warning" | "info";
  message: string;
  condition?: string;
  value?: string;
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface DeploymentIssue {
  deployment_name?: string; // legacy frontend alias
  name?: string; // backend field name
  namespace: string;
  issue_type?: string; // legacy frontend alias
  issue?: string; // backend field name
  severity: "critical" | "warning" | "info";
  message?: string;
  desired_replicas?: number;
  available_replicas?: number;
  ready_replicas?: number; // backend field name
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface ConfigIssue {
  resource_type: string;
  resource_name: string;
  namespace: string;
  issue_type?: string; // legacy frontend alias
  issue?: string; // backend field name
  severity: "critical" | "warning" | "info";
  message?: string;
  referenced_by?: string; // backend field name
  missing_key?: string; // backend field name
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface DriftIssue {
  resource_type: string;
  resource_name?: string; // legacy frontend alias
  name?: string; // backend field name
  namespace: string;
  drift_type?: string; // legacy frontend alias
  field?: string; // backend field name
  severity: "critical" | "warning" | "info";
  message?: string;
  expected?: string;
  actual?: string;
  description?: string; // backend field name
  spec_value?: string | number | boolean | null;
  status_value?: string | number | boolean | null;
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface SilenceSignal {
  signal_type: string;
  resource?: string;
  namespace?: string;
  pod_name?: string;
  container_name?: string;
  message?: string;
  note?: string;
  possible_causes?: string[];
  severity: "critical" | "warning" | "info";
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface K8sEvent {
  type: string;
  reason: string;
  message: string;
  involved_object?: string;
  involved_object_kind?: string;  // backend field name
  involved_object_name?: string;  // backend field name
  namespace?: string;
  timestamp?: string;
  count?: number;
}

// ─── Troubleshoot.sh models ─────────────────────────────────────

export interface TroubleshootAnalyzerResult {
  name: string;
  check_name: string;
  is_pass: boolean;
  is_warn: boolean;
  is_fail: boolean;
  title: string;
  message: string;
  uri: string;
  analyzer_type: string;
  severity: "pass" | "warn" | "fail";
  strict: boolean;
}

export interface TroubleshootAnalysis {
  results: TroubleshootAnalyzerResult[];
  pass_count: number;
  warn_count: number;
  fail_count: number;
  has_results: boolean;
}

export interface PreflightCheckResult {
  name: string;
  check_name: string;
  is_pass: boolean;
  is_warn: boolean;
  is_fail: boolean;
  title: string;
  message: string;
  uri: string;
  analyzer_type: string;
  severity: "pass" | "warn" | "fail";
}

export interface PreflightReport {
  results: PreflightCheckResult[];
  pass_count: number;
  warn_count: number;
  fail_count: number;
  collected_at?: string;
}

export interface ExternalAnalyzerIssue {
  source: string;
  analyzer_type: string;
  name: string;
  title: string;
  message: string;
  severity: "critical" | "warning" | "info";
  uri: string;
  corroborates?: string | null;
  contradicts?: string | null;
}

export interface RBACIssue {
  namespace: string;
  resource_type: string;
  error_message: string;
  severity: 'critical' | 'warning' | 'info';
  suggested_permission: string;
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface QuotaIssue {
  namespace: string;
  resource_name: string;
  issue_type: 'quota_exceeded' | 'quota_near_limit' | 'limit_range_conflict' | 'no_quota';
  resource_type: string;
  current_usage: string;
  limit: string;
  message: string;
  severity: 'critical' | 'warning' | 'info';
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface NetworkPolicyIssue {
  namespace: string;
  policy_name: string;
  issue_type: 'deny_all_ingress' | 'deny_all_egress' | 'no_policies' | 'orphaned_policy';
  affected_pods: string[];
  message: string;
  severity: 'critical' | 'warning' | 'info';
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface CrashLoopContext {
  namespace: string;
  pod_name: string;
  container_name: string;
  exit_code: number | null;
  termination_reason: string;
  last_log_lines: string[];
  previous_log_lines: string[];
  crash_pattern: string;
  restart_count: number;
  message: string;
  severity: 'critical' | 'warning' | 'info';
}

export interface EventEscalation {
  namespace: string;
  involved_object_kind: string;
  involved_object_name: string;
  event_reasons: string[];
  total_count: number;
  first_seen: string | null;
  last_seen: string | null;
  escalation_type: 'repeated' | 'cascading' | 'sustained';
  message: string;
  severity: 'critical' | 'warning' | 'info';
}

export interface CoverageGap {
  area: string;
  data_present: boolean;
  data_path: string;
  why_it_matters: string;
  severity: 'high' | 'medium' | 'low';
}

export interface PodAnomaly {
  failing_pod: string;
  comparison_group: string;
  anomaly_type: 'node_placement' | 'image_version' | 'resource_limits' | 'env_config' | 'labels_annotations' | 'restart_pattern';
  description: string;
  failing_value: string;
  healthy_value: string;
  severity: 'critical' | 'warning' | 'info';
  suggestion: string;
}

export interface ServiceDependency {
  source_pod: string;
  target_service: string;
  target_namespace: string;
  discovery_method: string;
  env_var_name: string;
  is_healthy: boolean | null;
  health_detail: string;
  severity: 'critical' | 'warning' | 'info';
}

export interface DependencyMap {
  dependencies: ServiceDependency[];
  broken_dependencies: ServiceDependency[];
  total_services_discovered: number;
  total_broken: number;
}

export interface ChangeEvent {
  resource_type: string;
  resource_name: string;
  namespace: string;
  change_type: 'created' | 'modified' | 'scaled' | 'restarted' | 'deleted' | 'rolled_out';
  timestamp: string;
  detail: string;
}

export interface ChangeCorrelation {
  change: ChangeEvent;
  failure_description: string;
  time_delta_seconds: number;
  correlation_strength: 'strong' | 'moderate' | 'weak';
  explanation: string;
  severity: 'critical' | 'warning' | 'info';
}

export interface ChangeReport {
  recent_changes: ChangeEvent[];
  correlations: ChangeCorrelation[];
  timeline_window_minutes: number;
}

export interface LogDiagnosis {
  namespace: string;
  pod_name: string;
  container_name: string;
  diagnosis: string;
  root_cause_category: string;
  key_log_line: string;
  why: string;
  fix_description: string;
  fix_commands: string[];
  confidence: number;
  additional_context_needed: string[];
}

export interface DNSIssue {
  namespace: string;
  resource_name: string;
  issue_type: 'coredns_pod_failure' | 'dns_resolution_error' | 'missing_endpoints' | 'coredns_config_error';
  message: string;
  severity: 'critical' | 'warning' | 'info';
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface TLSIssue {
  namespace: string;
  resource_name: string;
  issue_type: 'cert_expired' | 'bad_certificate' | 'unknown_authority' | 'missing_tls_secret';
  message: string;
  severity: 'critical' | 'warning' | 'info';
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface SchedulingIssue {
  namespace: string;
  pod_name: string;
  issue_type: 'insufficient_cpu' | 'insufficient_memory' | 'taint_not_tolerated' | 'node_affinity_mismatch' | 'pod_affinity_conflict' | 'node_selector_mismatch' | 'unschedulable_node';
  message: string;
  severity: 'critical' | 'warning' | 'info';
  source_file?: string;
  evidence_excerpt?: string;
  confidence?: number;
}

export interface Hypothesis {
  id: string;
  title: string;
  description: string;
  category: string;
  confidence: number;
  supporting_evidence: string[];
  contradicting_evidence: string[];
  affected_resources: string[];
  suggested_fixes: string[];
  is_validated: boolean;
}

export interface TriageResult {
  pod_issues: PodIssue[];
  node_issues: NodeIssue[];
  deployment_issues: DeploymentIssue[];
  config_issues: ConfigIssue[];
  drift_issues: DriftIssue[];
  silence_signals: SilenceSignal[];
  events: K8sEvent[];
  rbac_issues: RBACIssue[];
  quota_issues: QuotaIssue[];
  network_policy_issues: NetworkPolicyIssue[];
  crash_contexts: CrashLoopContext[];
  event_escalations: EventEscalation[];
  dns_issues: DNSIssue[];
  tls_issues: TLSIssue[];
  scheduling_issues: SchedulingIssue[];
  coverage_gaps: CoverageGap[];
  pod_anomalies: PodAnomaly[];
  dependency_map?: DependencyMap | null;
  change_report?: ChangeReport | null;
  troubleshoot_analysis?: TroubleshootAnalysis;
  preflight_report?: PreflightReport | null;
  external_analyzer_issues?: ExternalAnalyzerIssue[];
}

// ─── Analysis models ─────────────────────────────────────────────

export interface Evidence {
  file: string;
  content: string;
  excerpt?: string;        // from backend API
  line_start?: number;
  line_end?: number;
  line_number?: number;    // from backend API
  relevance: string;
}

export interface Fix {
  description: string;
  commands?: string[];
  risk: "low" | "medium" | "high";
  estimated_impact: string;
}

export interface Finding {
  id: string;
  title?: string;
  severity: "critical" | "warning" | "info";
  type?: string;
  category?: string;
  resource?: string;
  symptom: string;
  root_cause: string;
  evidence: Evidence[];
  fix?: Fix | null;
  fixes?: Fix[];
  confidence: number;
  affected_resources?: string[];
}

export interface HistoricalEvent {
  timestamp: string;
  event_type: string;
  resource?: string;          // frontend-only convenience
  resource_type?: string;     // backend field
  resource_name?: string;     // backend field
  namespace?: string;
  description: string;
  is_trigger: boolean;
  related_findings?: string[];
}

export interface PredictedFailure {
  failure_type: string;
  resource: string;
  namespace?: string;
  probability?: number;        // frontend convenience
  confidence?: number;         // backend field
  eta_hours?: number;          // frontend convenience
  estimated_eta_seconds?: number | null; // backend field
  evidence: string | string[]; // backend sends list
  prevention: string;
}

export interface UncertaintyGap {
  area?: string;               // frontend convenience
  question?: string;           // backend field
  description?: string;        // frontend convenience
  reason?: string;             // backend field
  impact: string;
  what_would_help?: string;    // frontend convenience
  to_investigate?: string;     // backend field
  collect_command?: string;    // backend field
}

export interface AnalysisResult {
  bundle_id: string;
  findings: Finding[];
  timeline: HistoricalEvent[];
  predictions: PredictedFailure[];
  uncertainty_gaps: UncertaintyGap[];
  log_diagnoses: LogDiagnosis[];
  hypotheses: Hypothesis[];
  triage?: TriageResult;
  summary: {
    critical_count: number;
    warning_count: number;
    info_count: number;
    top_finding?: string;
  };
}

// ─── API / status models ─────────────────────────────────────────

export interface BundleInfo {
  id: string;
  filename: string;
  status: string;
  uploaded_at: string;
  completed_at?: string;
  file_size?: number;
  summary?: string;
  finding_count?: number;
  critical_count?: number;
  warning_count?: number;
}

export interface AnalysisStatus {
  bundle_id: string;
  status: "uploaded" | "extracting" | "triaging" | "analyzing" | "complete" | "error";
  progress: number;
  current_stage: string;
  message: string;
}

// ─── Interview models ────────────────────────────────────────────

export interface InterviewSession {
  session_id: string;
  bundle_id: string;
}

export interface InterviewMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

export interface InterviewAnswer {
  answer: string;
  evidence?: Evidence[];
  suggested_questions?: string[];
}

// ─── Diff models ────────────────────────────────────────────────

export interface DiffFinding {
  status: "new" | "resolved" | "worsened" | "unchanged";
  category: string;
  resource: string;
  description: string;
  before_detail: string;
  after_detail: string;
}

export interface DiffResult {
  summary: string;
  new_findings: DiffFinding[];
  resolved_findings: DiffFinding[];
  worsened_findings: DiffFinding[];
  unchanged_findings: DiffFinding[];
  resource_delta: Record<string, number>;
}

// ─── Simulation models ──────────────────────────────────────────

export interface SimulationResult {
  fix_resolves: string[];
  fix_creates: string[];
  residual_issues: string[];
  recovery_timeline: string;
  manual_steps_after: string[];
  confidence: number;
}

// ─── Evaluation models ──────────────────────────────────────────

export interface DependencyLink {
  step_number: number;
  resource: string;
  observation: string;
  evidence_source: string;
  evidence_excerpt: string;
  leads_to: string;
  significance: "root_cause" | "contributing" | "symptom" | "context";
}

export interface CorrelatedSignal {
  scanner_type: string;
  signal: string;
  relates_to: string;
  severity: "critical" | "warning" | "info";
}

export interface EvaluationVerdict {
  failure_point: string;
  resource: string;
  app_claimed_cause: string;
  true_likely_cause: string;
  correctness: "Correct" | "Partially Correct" | "Incorrect" | "Inconclusive";
  dependency_chain: DependencyLink[];
  correlated_signals: CorrelatedSignal[];
  supporting_evidence: string[];
  contradicting_evidence: string[];
  missed: string[];
  misinterpreted: string[];
  stronger_alternative: string | null;
  alternative_hypotheses: string[];
  blast_radius: string[];
  remediation_assessment: string;
  confidence_score: number;
  notes: string;
}

export interface MissedFailurePoint {
  failure_point: string;
  resource: string;
  evidence_summary: string;
  severity: "critical" | "warning" | "info";
  dependency_chain: DependencyLink[];
  correlated_signals: CorrelatedSignal[];
  recommended_action: string;
}

export interface EvaluationResult {
  verdicts: EvaluationVerdict[];
  overall_correctness: "Correct" | "Partially Correct" | "Incorrect" | "Inconclusive";
  overall_confidence: number;
  missed_failure_points: MissedFailurePoint[];
  cross_cutting_concerns: string[];
  evaluation_summary: string;
  evaluation_duration_seconds: number;
}

// ─── Dependency Graph models ─────────────────────────────────────

export interface CausalStep {
  resource: string;
  observation: string;
  evidence_file: string;
  evidence_excerpt: string;
}

export interface CausalChain {
  id: string;
  symptom: string;
  symptom_resource: string;
  steps: CausalStep[];
  root_cause: string | null;
  confidence: number;
  ambiguous: boolean;
  needs_ai: boolean;
  related_resources: string[];
}

export interface GraphNode {
  id: string;
  type: string;
  name: string;
  namespace: string;
  status: string;
  severity?: string;
  symptom?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship: string;
}

export interface DependencyGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  causal_chains: CausalChain[];
}

// ─── Coverage Comparison models ──────────────────────────────────

export interface TroubleshootFoundItem {
  name: string;
  analyzer_type: string;
  severity: "critical" | "warning" | "info";
  title: string;
  detail: string;
}

export interface TroubleshootAIFoundItem {
  type: string;
  resource: string;
  severity: "critical" | "warning" | "info";
  description: string;
}

export interface CoverageComparison {
  troubleshoot_found: TroubleshootFoundItem[];
  troubleshootai_found: TroubleshootAIFoundItem[];
  missed_by_troubleshoot: TroubleshootAIFoundItem[];
  troubleshoot_count: number;
  troubleshootai_count: number;
  gap_count: number;
}
