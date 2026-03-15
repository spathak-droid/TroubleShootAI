"""Evaluator prompt templates for independent second-opinion analysis.

Contains the system prompt for the expert CI/CD incident analyst persona
and the user prompt builder that separates raw evidence from the app's output.
Designed to produce detailed dependency traces, not just summary verdicts.
"""

from __future__ import annotations

from bundle_analyzer.models import AnalysisResult

EVALUATOR_SYSTEM_PROMPT = """\
You are a senior Kubernetes SRE performing a FORENSIC REVIEW of an automated \
support bundle analysis. You have access to the raw evidence and the app's \
conclusions. Your job is NOT to summarize — it is to TRACE every dependency \
chain step by step and verify whether the automated analysis got it right.

## Your methodology

For EACH failure point the app identified:
1. Start from the observed SYMPTOM (e.g. CrashLoopBackOff, Pending, NotReady)
2. Trace the dependency chain step by step through the raw evidence:
   - What does the pod spec show? (probes, resources, volumes, env refs)
   - What do the events say? (event reason, message, count, timestamps)
   - What do the logs show? (error patterns, crash signals, connection issues)
   - What do the node conditions show? (pressure, capacity, scheduling)
   - What do the config references show? (missing ConfigMaps, Secrets)
   - What do the resource limits show? (OOM risk, QoS class, overcommit)
   - What do the probes show? (bad paths, port mismatches, missing startup)
   - What do the silence signals show? (missing logs, RBAC blocks)
3. At each step, cite the EXACT evidence (file path + data excerpt)
4. Show how each step LEADS TO the next (A causes B causes C)
5. Arrive at the root cause independently
6. Compare YOUR conclusion against the app's claimed root cause

## Cross-referencing signals

For each failure point, cross-reference across ALL signal types:
- Pod scanner signals (crash loops, OOM, image pull, pending, eviction)
- Node scanner signals (memory/disk/PID pressure, NotReady, unschedulable)
- Probe scanner signals (bad probe paths, missing readiness, port mismatch)
- Resource scanner signals (no limits, no requests, exceeds node capacity)
- Config scanner signals (missing ConfigMap/Secret, missing key, wrong NS)
- Drift scanner signals (spec vs status divergence)
- Silence scanner signals (missing logs, empty logs on running pod, RBAC blocked)
- Event scanner signals (Warning events with counts and involved objects)
- Storage scanner signals (PVC pending, missing StorageClass)
- Ingress scanner signals (missing backend, TLS secret issues)

The app may have found the primary issue but missed correlated signals that \
paint a fuller picture. Report ALL of them.

## What makes a good dependency chain

BAD (what the app already does — just restating the conclusion):
  "The liveness probe is misconfigured, causing CrashLoopBackOff"

GOOD (what YOU must produce — step-by-step trace with evidence):
  Step 1: Pod spec → livenessProbe.httpGet.path = "/this-path-does-not-exist" [pod JSON]
  Step 2: This path does not exist on the nginx container → HTTP 404 responses
  Step 3: Events show 1566 "Unhealthy" events with "HTTP probe failed with statuscode: 404" [events JSON]
  Step 4: After failureThreshold (3) consecutive failures, kubelet kills the container
  Step 5: lastState.terminated.exitCode = 0 (SIGTERM from kubelet, not app crash) [pod status]
  Step 6: restartPolicy: Always → kubelet restarts → restartCount = 521 [pod status]
  Step 7: Exponential backoff → container state "waiting" reason "CrashLoopBackOff" [pod status]
  Step 8: Pod phase "Running" but Ready condition False (ContainersNotReady) [pod conditions]
  Step 9: No application logs available — nginx starts but is killed before it can log [silence signal]

Each step MUST have: resource, observation, evidence source, evidence excerpt, \
and what it leads to next.

## Blast radius

For each failure, identify what ELSE is affected:
- What Deployment/ReplicaSet owns this Pod?
- What Service selects this Pod? (traffic impact)
- What other Pods on the same Node are affected?
- What Ingress routes to the affected Service?

## Response format

You must respond with valid JSON only. No markdown, no commentary outside the JSON.

{
  "verdicts": [
    {
      "failure_point": "string — human description of the failure",
      "resource": "string — K8s resource key e.g. Pod/default/my-pod",
      "app_claimed_cause": "string — what the pipeline said was the root cause",
      "true_likely_cause": "string — your independent assessment",
      "correctness": "Correct | Partially Correct | Incorrect | Inconclusive",
      "dependency_chain": [
        {
          "step_number": 1,
          "resource": "Pod/default/my-pod",
          "observation": "livenessProbe.httpGet.path set to /this-path-does-not-exist",
          "evidence_source": "cluster-resources/pods/default.json",
          "evidence_excerpt": "livenessProbe: {httpGet: {path: /this-path-does-not-exist, port: 80}}",
          "leads_to": "HTTP probe requests to non-existent path return 404",
          "significance": "root_cause"
        }
      ],
      "correlated_signals": [
        {
          "scanner_type": "probe",
          "signal": "Liveness probe path /this-path-does-not-exist is suspicious",
          "relates_to": "Confirms the probe misconfiguration is the root cause",
          "severity": "critical"
        },
        {
          "scanner_type": "silence",
          "signal": "No application logs for container nginx",
          "relates_to": "Expected — container is killed before it can log",
          "severity": "warning"
        }
      ],
      "supporting_evidence": ["evidence excerpts that support the app's diagnosis"],
      "contradicting_evidence": ["evidence that contradicts the app's diagnosis"],
      "missed": ["signals the app should have included but didn't"],
      "misinterpreted": ["signals the app got wrong"],
      "stronger_alternative": "string or null",
      "alternative_hypotheses": ["other plausible explanations"],
      "blast_radius": ["Deployment/default/break-bad-probe", "Service/default/break-bad-probe-svc"],
      "remediation_assessment": "Is the app's suggested fix correct and complete?",
      "confidence_score": 0.95,
      "notes": "additional observations"
    }
  ],
  "overall_correctness": "Correct | Partially Correct | Incorrect | Inconclusive",
  "overall_confidence": 0.85,
  "missed_failure_points": [
    {
      "failure_point": "description of what was missed",
      "resource": "K8s resource key",
      "evidence_summary": "what evidence shows this failure",
      "severity": "critical | warning | info",
      "dependency_chain": [{"step_number": 1, "resource": "...", "observation": "...", "evidence_source": "...", "evidence_excerpt": "...", "leads_to": "...", "significance": "root_cause"}],
      "correlated_signals": [{"scanner_type": "...", "signal": "...", "relates_to": "...", "severity": "warning"}],
      "recommended_action": "what should be done"
    }
  ],
  "cross_cutting_concerns": ["issues that span multiple findings, e.g. cluster-wide resource exhaustion"],
  "evaluation_summary": "2-4 sentence detailed summary"
}

IMPORTANT CONSTRAINTS:
- Keep evidence_excerpt values SHORT (under 80 chars) — just the key data point
- Keep string values concise — no paragraphs, just the essential fact
- Limit dependency_chain to the most important 5-8 steps per verdict
- Limit correlated_signals to the most relevant 3-5 per verdict
- The response MUST be complete valid JSON — do not exceed the output limit
"""


def build_evaluator_user_prompt(
    analysis: AnalysisResult,
    raw_log_excerpts: dict[str, str],
    raw_pod_specs: dict[str, dict],
    raw_events: dict[str, list[dict]],
) -> str:
    """Build the user prompt with exhaustive raw evidence and app output.

    Includes raw pod specs (probes, resources, volumes), events, logs,
    and ALL triage scanner signals — not just critical pods.

    Args:
        analysis: The completed AnalysisResult from the main pipeline.
        raw_log_excerpts: Dict mapping source path to log excerpt content.
        raw_pod_specs: Dict mapping pod key to relevant spec sections.
        raw_events: Dict mapping namespace to list of event dicts.

    Returns:
        Formatted prompt string with Section A (raw evidence) and Section B (app output).
    """
    sections: list[str] = []

    # ── Section A: Raw Evidence ──────────────────────────────────
    sections.append("=" * 60)
    sections.append("SECTION A: RAW EVIDENCE")
    sections.append("Examine this evidence independently. Trace every dependency chain.")
    sections.append("=" * 60)
    sections.append("")

    # A.1: Raw pod specs (probes, resources, volumes, env, status)
    if raw_pod_specs:
        sections.append("## A.1 — Pod Specifications & Status")
        for pod_key, spec_data in raw_pod_specs.items():
            sections.append(f"### {pod_key}")
            # Containers with probes, resources, env
            for container in spec_data.get("containers", []):
                cname = container.get("name", "unknown")
                sections.append(f"  Container: {cname}")
                sections.append(f"    Image: {container.get('image', 'unknown')}")

                # Probes
                for probe_type in ["livenessProbe", "readinessProbe", "startupProbe"]:
                    probe = container.get(probe_type)
                    if probe:
                        sections.append(f"    {probe_type}: {_format_probe(probe)}")
                    else:
                        sections.append(f"    {probe_type}: NOT CONFIGURED")

                # Resources
                resources = container.get("resources", {})
                requests = resources.get("requests", {})
                limits = resources.get("limits", {})
                sections.append(f"    resources.requests: {requests or 'NONE'}")
                sections.append(f"    resources.limits: {limits or 'NONE'}")

                # Env refs (ConfigMap/Secret references)
                env_refs = container.get("env_refs", [])
                if env_refs:
                    sections.append(f"    env references: {', '.join(env_refs)}")

                # Volume mounts
                vol_mounts = container.get("volumeMounts", [])
                if vol_mounts:
                    for vm in vol_mounts[:5]:
                        sections.append(f"    mount: {vm.get('name', '?')} -> {vm.get('mountPath', '?')}")

            # Pod status
            status = spec_data.get("status", {})
            if status:
                sections.append(f"  Phase: {status.get('phase', 'unknown')}")
                sections.append(f"  Node: {status.get('nodeName', 'unknown')}")
                sections.append(f"  RestartPolicy: {spec_data.get('restartPolicy', 'Always')}")

                # Container statuses
                for cs in status.get("containerStatuses", []):
                    sections.append(f"  ContainerStatus[{cs.get('name', '?')}]:")
                    sections.append(f"    ready: {cs.get('ready', False)}")
                    sections.append(f"    restartCount: {cs.get('restartCount', 0)}")
                    state = cs.get("state", {})
                    for state_type, state_data in state.items():
                        sections.append(f"    state.{state_type}: {state_data}")
                    last_state = cs.get("lastState", {})
                    for state_type, state_data in last_state.items():
                        sections.append(f"    lastState.{state_type}: {state_data}")

                # Conditions
                conditions = status.get("conditions", [])
                if conditions:
                    sections.append("  Conditions:")
                    for cond in conditions:
                        sections.append(
                            f"    {cond.get('type', '?')}: {cond.get('status', '?')} "
                            f"— {cond.get('reason', '')} {cond.get('message', '')}"
                        )

            # Volumes
            volumes = spec_data.get("volumes", [])
            if volumes:
                sections.append("  Volumes:")
                for vol in volumes[:8]:
                    vol_type = next(
                        (k for k in vol if k != "name"),
                        "unknown",
                    )
                    sections.append(f"    {vol.get('name', '?')}: {vol_type}={vol.get(vol_type, {})}")
            sections.append("")

    # A.2: Raw events
    if raw_events:
        sections.append("## A.2 — Kubernetes Events")
        for ns, events in raw_events.items():
            sections.append(f"### Namespace: {ns}")
            for ev in events[:30]:
                involved = ev.get("involvedObject", {})
                sections.append(
                    f"  [{ev.get('type', '?')}] {ev.get('reason', '?')}: "
                    f"{ev.get('message', '')[:200]} "
                    f"(object={involved.get('kind', '?')}/{involved.get('name', '?')}, "
                    f"count={ev.get('count', 1)})"
                )
            sections.append("")

    # A.3: Raw log excerpts
    if raw_log_excerpts:
        sections.append("## A.3 — Log Excerpts")
        for source, content in raw_log_excerpts.items():
            sections.append(f"### {source}")
            sections.append(content[:3000])
            sections.append("")

    # A.4: ALL triage scanner signals
    triage = analysis.triage
    sections.append("## A.4 — Triage Scanner Signals (all 11 scanner types)")
    sections.append("")

    if triage.critical_pods:
        sections.append("### Pod Scanner — Critical")
        for pod in triage.critical_pods:
            sections.append(
                f"  - {pod.namespace}/{pod.pod_name} [{pod.container_name or '*'}]: "
                f"{pod.issue_type} (restarts={pod.restart_count}, exit_code={pod.exit_code}) "
                f"— {pod.message}"
            )
            if pod.log_path:
                sections.append(f"    log_path: {pod.log_path}")
            if pod.previous_log_path:
                sections.append(f"    previous_log_path: {pod.previous_log_path}")

    if triage.warning_pods:
        sections.append("### Pod Scanner — Warning")
        for pod in triage.warning_pods[:15]:
            sections.append(
                f"  - {pod.namespace}/{pod.pod_name}: {pod.issue_type} "
                f"(restarts={pod.restart_count}) — {pod.message}"
            )

    if triage.node_issues:
        sections.append("### Node Scanner")
        for node in triage.node_issues:
            sections.append(
                f"  - {node.node_name}: {node.condition} "
                f"(mem={node.memory_usage_pct}%, cpu={node.cpu_usage_pct}%) "
                f"— {node.message}"
            )

    if triage.probe_issues:
        sections.append("### Probe Scanner")
        for pi in triage.probe_issues:
            sections.append(
                f"  - {pi.namespace}/{pi.pod_name}/{pi.container_name}: "
                f"[{pi.severity}] {pi.probe_type} probe — {pi.issue}: {pi.message}"
            )

    if triage.resource_issues:
        sections.append("### Resource Scanner")
        for ri in triage.resource_issues:
            sections.append(
                f"  - {ri.namespace}/{ri.pod_name}/{ri.container_name}: "
                f"[{ri.severity}] {ri.resource_type} — {ri.issue}: {ri.message}"
            )

    if triage.config_issues:
        sections.append("### Config Scanner")
        for ci in triage.config_issues:
            sections.append(
                f"  - {ci.namespace}/{ci.resource_name} ({ci.resource_type}): "
                f"{ci.issue} — referenced by {ci.referenced_by}"
                + (f", missing_key: {ci.missing_key}" if ci.missing_key else "")
            )

    if triage.deployment_issues:
        sections.append("### Deployment Scanner")
        for di in triage.deployment_issues:
            sections.append(
                f"  - {di.namespace}/{di.name}: {di.ready_replicas}/{di.desired_replicas} ready "
                f"— {di.issue}" + (" [STUCK ROLLOUT]" if di.stuck_rollout else "")
            )

    if triage.drift_issues:
        sections.append("### Drift Scanner")
        for dr in triage.drift_issues:
            sections.append(
                f"  - {dr.namespace}/{dr.name} ({dr.resource_type}): "
                f"{dr.field} spec={dr.spec_value} vs status={dr.status_value} "
                f"— {dr.description}"
            )

    if triage.silence_signals:
        sections.append("### Silence Scanner")
        for ss in triage.silence_signals:
            sections.append(
                f"  - {ss.namespace}/{ss.pod_name}"
                + (f"/{ss.container_name}" if ss.container_name else "")
                + f": [{ss.severity}] {ss.signal_type} — {ss.note}"
            )
            if ss.possible_causes:
                sections.append(f"    possible causes: {', '.join(ss.possible_causes)}")

    if triage.warning_events:
        sections.append(f"### Event Scanner ({len(triage.warning_events)} warning events)")
        for evt in triage.warning_events[:25]:
            sections.append(
                f"  - [{evt.type}] {evt.reason}: {evt.message[:150]} "
                f"(object={evt.involved_object_kind}/{evt.involved_object_name}, count={evt.count})"
            )

    if triage.storage_issues:
        sections.append("### Storage Scanner")
        for si in triage.storage_issues:
            sections.append(
                f"  - {si.namespace}/{si.resource_name} ({si.resource_type}): "
                f"[{si.severity}] {si.issue} — {si.message}"
            )

    if triage.ingress_issues:
        sections.append("### Ingress Scanner")
        for ii in triage.ingress_issues:
            sections.append(
                f"  - {ii.namespace}/{ii.ingress_name}: "
                f"[{ii.severity}] {ii.issue} — {ii.message}"
            )

    if triage.rbac_errors:
        sections.append(f"### RBAC Errors ({len(triage.rbac_errors)})")
        for err in triage.rbac_errors[:10]:
            sections.append(f"  - {err[:200]}")

    sections.append("")

    # A.5: Existing causal chains (from chain walker)
    if analysis.causal_chains:
        sections.append("## A.5 — Deterministic Causal Chains (from ChainWalker)")
        for chain in analysis.causal_chains:
            sections.append(f"### Chain: {chain.symptom}")
            sections.append(f"  Resource: {chain.symptom_resource}")
            sections.append(f"  Root cause: {chain.root_cause or 'ambiguous'}")
            sections.append(f"  Confidence: {chain.confidence}")
            sections.append(f"  Needs AI: {chain.needs_ai}")
            sections.append(f"  Related: {', '.join(chain.related_resources)}")
            sections.append("  Steps:")
            for step in chain.steps:
                sections.append(
                    f"    {step.resource}: {step.observation}\n"
                    f"      evidence: {step.evidence_file} — {step.evidence_excerpt}"
                )
            sections.append("")

    # ── Section B: App's Output to Evaluate ──────────────────────
    sections.append("")
    sections.append("=" * 60)
    sections.append("SECTION B: APP'S OUTPUT TO EVALUATE")
    sections.append("Compare your independent trace against these conclusions.")
    sections.append("=" * 60)
    sections.append("")

    # Findings with full detail
    sections.append("## Findings")
    for finding in analysis.findings:
        evidence_detail = []
        for e in finding.evidence[:5]:
            evidence_detail.append(f"    {e.file}: {e.excerpt[:200]}")
        fix_detail = ""
        if finding.fix:
            fix_detail = f"\n  Fix: {finding.fix.description}"
            if finding.fix.commands:
                fix_detail += f"\n  Commands: {', '.join(finding.fix.commands[:3])}"
            fix_detail += f"\n  Risk: {finding.fix.risk}"

        sections.append(
            f"- [{finding.severity}] {finding.resource}\n"
            f"  Symptom: {finding.symptom}\n"
            f"  Root cause: {finding.root_cause}\n"
            f"  Confidence: {finding.confidence}\n"
            f"  Evidence:\n" + "\n".join(evidence_detail)
            + fix_detail
        )
    sections.append("")

    # Overall root cause
    if analysis.root_cause:
        sections.append(f"## App's Overall Root Cause: {analysis.root_cause}")
        sections.append(f"## App's Overall Confidence: {analysis.confidence}")
        sections.append("")

    # Uncertainty gaps
    if analysis.uncertainty:
        sections.append("## App's Uncertainty Gaps")
        for gap in analysis.uncertainty:
            sections.append(
                f"- {gap.question} ({gap.impact}): {gap.reason}"
            )
        sections.append("")

    sections.append(
        "Trace every dependency chain step by step. "
        "Cross-reference ALL triage signals. "
        "Show your work — cite exact evidence at each step. "
        "Respond with valid JSON only."
    )

    return "\n".join(sections)


def _format_probe(probe: dict) -> str:
    """Format a probe spec into a readable string."""
    parts = []
    if "httpGet" in probe:
        http = probe["httpGet"]
        parts.append(f"httpGet path={http.get('path', '/')} port={http.get('port', '?')}")
    elif "tcpSocket" in probe:
        parts.append(f"tcpSocket port={probe['tcpSocket'].get('port', '?')}")
    elif "exec" in probe:
        cmd = probe["exec"].get("command", [])
        parts.append(f"exec {' '.join(str(c) for c in cmd[:3])}")

    for field in ["initialDelaySeconds", "periodSeconds", "timeoutSeconds",
                   "failureThreshold", "successThreshold"]:
        if field in probe:
            parts.append(f"{field}={probe[field]}")

    return ", ".join(parts) if parts else str(probe)
