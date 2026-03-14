"""HTML report builder — constructs a self-contained HTML report from analysis results."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from bundle_analyzer.api.session import BundleSession


def build_html_report(analysis: Any, triage: Any, session: BundleSession) -> str:
    """Build a self-contained HTML report from analysis results.

    Args:
        analysis: The AnalysisResult object.
        triage: The TriageResult object.
        session: The bundle session for metadata.

    Returns:
        Complete HTML string.
    """
    h = html.escape

    # Counts
    critical = len(triage.critical_pods)
    warning = len(triage.warning_pods) + len(triage.node_issues)
    info_count = len(triage.deployment_issues) + len(triage.config_issues)
    ai_findings = len(analysis.findings)
    ext_issues = len(triage.external_analyzer_issues)

    ts_section = _build_troubleshoot_section(triage, h)
    pf_section = _build_preflight_section(triage, h)
    ext_section = _build_external_section(triage, h)
    findings_section = _build_findings_section(analysis, h)
    pods_section = _build_pods_section(triage, h)
    crash_section = _build_crash_section(triage, h)
    esc_section = _build_escalation_section(triage, h)
    rbac_section = _build_rbac_section(triage, h)
    quota_section = _build_quota_section(triage, h)
    netpol_section = _build_netpol_section(triage, h)
    coverage_section = _build_coverage_section(triage, h)
    log_diag_section = _build_log_diag_section(analysis, h)
    anomaly_section = _build_anomaly_section(triage, h)
    dep_section = _build_dep_section(triage, h)
    change_section = _build_change_section(triage, h)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bundle Analysis Report — {h(session.id)}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
           background: #0a0e17; color: #c8cdd5; line-height: 1.6; padding: 2rem; }}
    h1 {{ color: #f0f2f5; margin-bottom: 0.5rem; font-size: 1.5rem; }}
    h2 {{ color: #e2e5ea; margin-bottom: 1rem; font-size: 1.15rem;
          border-bottom: 1px solid #1e2433; padding-bottom: 0.5rem; }}
    section {{ margin-bottom: 2.5rem; }}
    .meta {{ color: #6b7280; font-size: 0.85rem; margin-bottom: 2rem; }}
    .summary {{ color: #9ca3af; font-size: 0.9rem; margin-bottom: 1rem; }}
    .stats {{ display: flex; gap: 2rem; margin-bottom: 2rem; }}
    .stat {{ padding: 1rem 1.5rem; border-radius: 8px; background: #111827;
             border: 1px solid #1e2433; }}
    .stat .num {{ font-size: 1.5rem; font-weight: 700; }}
    .stat .label {{ font-size: 0.75rem; color: #6b7280; text-transform: uppercase; }}
    .stat.critical .num {{ color: #ef4444; }}
    .stat.warning .num {{ color: #f59e0b; }}
    .stat.info .num {{ color: #6366f1; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th {{ text-align: left; padding: 0.5rem 0.75rem; color: #6b7280;
         border-bottom: 1px solid #1e2433; font-weight: 600; font-size: 0.75rem;
         text-transform: uppercase; }}
    td {{ padding: 0.6rem 0.75rem; border-bottom: 1px solid #111827; }}
    tr:hover {{ background: #111827; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
              font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }}
    .badge.pass {{ background: #064e3b; color: #34d399; }}
    .badge.warn, .badge.warning {{ background: #78350f; color: #fbbf24; }}
    .badge.fail, .badge.critical {{ background: #7f1d1d; color: #f87171; }}
    .badge.info {{ background: #1e1b4b; color: #a5b4fc; }}
    .corr {{ font-size: 0.75rem; color: #6b7280; font-style: italic; }}
    .footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #1e2433;
              color: #4b5563; font-size: 0.75rem; }}
</style>
</head>
<body>
<h1>Bundle Analysis Report</h1>
<p class="meta">
    Bundle: {h(session.filename)} &mdash; Session: {h(session.id)}<br>
    Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}<br>
    {h(analysis.cluster_summary)}
</p>

<div class="stats">
    <div class="stat critical"><div class="num">{critical}</div><div class="label">Critical</div></div>
    <div class="stat warning"><div class="num">{warning}</div><div class="label">Warning</div></div>
    <div class="stat info"><div class="num">{info_count + ai_findings}</div><div class="label">Info / AI</div></div>
    <div class="stat info"><div class="num">{ext_issues}</div><div class="label">External</div></div>
</div>

{ts_section}
{pf_section}
{ext_section}
{pods_section}
{crash_section}
{esc_section}
{rbac_section}
{quota_section}
{netpol_section}
{coverage_section}
{log_diag_section}
{anomaly_section}
{dep_section}
{change_section}
{findings_section}

<div class="footer">
    Generated by Bundle Analyzer &mdash; AI-powered Kubernetes support bundle forensics
</div>
</body>
</html>"""


def _build_troubleshoot_section(triage: Any, h: Any) -> str:
    """Build the Troubleshoot.sh analyzer results section."""
    ts = triage.troubleshoot_analysis
    if not ts.has_results:
        return ""
    rows = ""
    for r in ts.results:
        sev_class = "pass" if r.is_pass else ("warn" if r.is_warn else "fail")
        sev_label = "PASS" if r.is_pass else ("WARN" if r.is_warn else "FAIL")
        rows += f"""<tr>
            <td><span class="badge {sev_class}">{sev_label}</span></td>
            <td>{h(r.title or r.name)}</td>
            <td>{h(r.message)}</td>
            <td>{h(r.analyzer_type)}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Troubleshoot.sh Analyzer Results</h2>
            <p class="summary">{ts.pass_count} passed, {ts.warn_count} warnings, {ts.fail_count} failures</p>
            <table>
                <thead><tr><th>Status</th><th>Title</th><th>Message</th><th>Type</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_preflight_section(triage: Any, h: Any) -> str:
    """Build the preflight check results section."""
    pf = triage.preflight_report
    if not pf or not pf.results:
        return ""
    rows = ""
    for r in pf.results:
        sev_class = "pass" if r.is_pass else ("warn" if r.is_warn else "fail")
        sev_label = "PASS" if r.is_pass else ("WARN" if r.is_warn else "FAIL")
        rows += f"""<tr>
            <td><span class="badge {sev_class}">{sev_label}</span></td>
            <td>{h(r.title or r.name)}</td>
            <td>{h(r.message)}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Preflight Check Results</h2>
            <p class="summary">{pf.pass_count} passed, {pf.warn_count} warnings, {pf.fail_count} failures</p>
            <table>
                <thead><tr><th>Status</th><th>Title</th><th>Message</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_external_section(triage: Any, h: Any) -> str:
    """Build the external analyzer issues section."""
    if not triage.external_analyzer_issues:
        return ""
    rows = ""
    for issue in triage.external_analyzer_issues:
        sev_class = issue.severity
        corr = f' <span class="corr">corroborates: {h(issue.corroborates)}</span>' if issue.corroborates else ""
        rows += f"""<tr>
            <td><span class="badge {sev_class}">{h(issue.severity).upper()}</span></td>
            <td>{h(issue.analyzer_type)}</td>
            <td>{h(issue.title)}</td>
            <td>{h(issue.message)}{corr}</td>
        </tr>"""
    return f"""
        <section>
            <h2>External Analyzer Issues</h2>
            <table>
                <thead><tr><th>Severity</th><th>Type</th><th>Title</th><th>Message</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_findings_section(analysis: Any, h: Any) -> str:
    """Build the AI findings section."""
    if not analysis.findings:
        return ""
    rows = ""
    for f in analysis.findings:
        rows += f"""<tr>
            <td><span class="badge {f.severity}">{h(f.severity).upper()}</span></td>
            <td>{h(f.resource)}</td>
            <td>{h(f.symptom)}</td>
            <td>{h(f.root_cause)}</td>
            <td>{round(f.confidence * 100)}%</td>
        </tr>"""
    return f"""
        <section>
            <h2>AI Findings</h2>
            <table>
                <thead><tr><th>Severity</th><th>Resource</th><th>Symptom</th><th>Root Cause</th><th>Confidence</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_pods_section(triage: Any, h: Any) -> str:
    """Build the pod issues section."""
    all_pods = list(triage.critical_pods) + list(triage.warning_pods)
    if not all_pods:
        return ""
    rows = ""
    for p in all_pods:
        sev = "critical" if p.issue_type in ("CrashLoopBackOff", "OOMKilled", "CreateContainerConfigError") else "warning"
        rows += f"""<tr>
            <td><span class="badge {sev}">{h(sev).upper()}</span></td>
            <td>{h(p.namespace)}/{h(p.pod_name)}</td>
            <td>{h(p.issue_type)}</td>
            <td>{h(p.message)}</td>
            <td>{p.restart_count}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Pod Issues</h2>
            <table>
                <thead><tr><th>Severity</th><th>Pod</th><th>Type</th><th>Message</th><th>Restarts</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_crash_section(triage: Any, h: Any) -> str:
    """Build the crash loop analysis section."""
    if not triage.crash_contexts:
        return ""
    rows = ""
    for ctx in triage.crash_contexts:
        prev_logs = h("\n".join(ctx.previous_log_lines[-10:])) if ctx.previous_log_lines else ""
        curr_logs = h("\n".join(ctx.last_log_lines[-10:])) if ctx.last_log_lines else ""
        log_excerpt = ""
        if prev_logs:
            log_excerpt += f'<div style="margin-top:4px"><strong style="color:#fbbf24;font-size:0.75rem">Previous logs:</strong><pre style="background:#0a0e17;padding:8px;border-radius:4px;margin-top:2px;font-size:0.75rem;overflow-x:auto">{prev_logs}</pre></div>'
        if curr_logs:
            log_excerpt += f'<div style="margin-top:4px"><strong style="color:#a5b4fc;font-size:0.75rem">Current logs:</strong><pre style="background:#0a0e17;padding:8px;border-radius:4px;margin-top:2px;font-size:0.75rem;overflow-x:auto">{curr_logs}</pre></div>'
        exit_str = str(ctx.exit_code) if ctx.exit_code is not None else "N/A"
        rows += f"""<tr>
            <td><span class="badge {ctx.severity}">{h(ctx.severity).upper()}</span></td>
            <td>{h(ctx.namespace)}/{h(ctx.pod_name)}</td>
            <td>{h(ctx.container_name)}</td>
            <td><span class="badge info">{h(ctx.crash_pattern or 'unknown')}</span></td>
            <td>{ctx.restart_count}</td>
            <td>{exit_str}</td>
            <td>{h(ctx.message)}{log_excerpt}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Crash Loop Analysis</h2>
            <table>
                <thead><tr><th>Severity</th><th>Pod</th><th>Container</th><th>Pattern</th><th>Restarts</th><th>Exit Code</th><th>Details</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_escalation_section(triage: Any, h: Any) -> str:
    """Build the event escalation patterns section."""
    if not triage.event_escalations:
        return ""
    rows = ""
    for esc in triage.event_escalations:
        reasons = ", ".join(h(r) for r in esc.event_reasons)
        first = str(esc.first_seen) if esc.first_seen else "N/A"
        last = str(esc.last_seen) if esc.last_seen else "N/A"
        rows += f"""<tr>
            <td><span class="badge {esc.severity}">{h(esc.severity).upper()}</span></td>
            <td>{h(esc.namespace)}</td>
            <td>{h(esc.involved_object_kind)}/{h(esc.involved_object_name)}</td>
            <td><span class="badge warning">{h(esc.escalation_type)}</span></td>
            <td>{esc.total_count}</td>
            <td>{h(first)} &mdash; {h(last)}</td>
            <td>{reasons}</td>
            <td>{h(esc.message)}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Event Escalation Patterns</h2>
            <table>
                <thead><tr><th>Severity</th><th>Namespace</th><th>Object</th><th>Type</th><th>Events</th><th>Time Span</th><th>Reasons</th><th>Message</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_rbac_section(triage: Any, h: Any) -> str:
    """Build the RBAC / permission issues section."""
    if not triage.rbac_issues:
        return ""
    rows = ""
    for issue in triage.rbac_issues:
        suggested = f" <em style='color:#a5b4fc'>Suggested: {h(issue.suggested_permission)}</em>" if issue.suggested_permission else ""
        rows += f"""<tr>
            <td><span class="badge {issue.severity}">{h(issue.severity).upper()}</span></td>
            <td>{h(issue.namespace)}</td>
            <td>{h(issue.resource_type)}</td>
            <td>{h(issue.error_message)}{suggested}</td>
        </tr>"""
    return f"""
        <section>
            <h2>RBAC / Permission Issues</h2>
            <table>
                <thead><tr><th>Severity</th><th>Namespace</th><th>Resource Type</th><th>Error</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_quota_section(triage: Any, h: Any) -> str:
    """Build the resource quota issues section."""
    if not triage.quota_issues:
        return ""
    rows = ""
    for issue in triage.quota_issues:
        usage = f"{h(issue.current_usage)} / {h(issue.limit)}" if issue.current_usage and issue.limit else ""
        rows += f"""<tr>
            <td><span class="badge {issue.severity}">{h(issue.severity).upper()}</span></td>
            <td>{h(issue.namespace)}/{h(issue.resource_name)}</td>
            <td><span class="badge info">{h(issue.issue_type)}</span></td>
            <td>{h(issue.resource_type)}</td>
            <td>{usage}</td>
            <td>{h(issue.message)}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Resource Quota Issues</h2>
            <table>
                <thead><tr><th>Severity</th><th>Resource</th><th>Issue Type</th><th>Resource Type</th><th>Usage</th><th>Message</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_netpol_section(triage: Any, h: Any) -> str:
    """Build the network policy issues section."""
    if not triage.network_policy_issues:
        return ""
    rows = ""
    for issue in triage.network_policy_issues:
        pods = ", ".join(h(p) for p in issue.affected_pods) if issue.affected_pods else "N/A"
        rows += f"""<tr>
            <td><span class="badge {issue.severity}">{h(issue.severity).upper()}</span></td>
            <td>{h(issue.namespace)}/{h(issue.policy_name)}</td>
            <td><span class="badge info">{h(issue.issue_type)}</span></td>
            <td>{pods}</td>
            <td>{h(issue.message)}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Network Policy Issues</h2>
            <table>
                <thead><tr><th>Severity</th><th>Policy</th><th>Issue Type</th><th>Affected Pods</th><th>Message</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_coverage_section(triage: Any, h: Any) -> str:
    """Build the coverage gaps section."""
    if not triage.coverage_gaps:
        return ""
    rows = ""
    for gap in sorted(triage.coverage_gaps, key=lambda g: {"high": 0, "medium": 1, "low": 2}.get(g.severity, 9)):
        present = "Yes" if gap.data_present else "No"
        sev_class = "warning" if gap.severity == "high" else ("info" if gap.severity == "medium" else "pass")
        rows += f"""<tr>
            <td><span class="badge {sev_class}">{h(gap.severity).upper()}</span></td>
            <td>{h(gap.area)}</td>
            <td>{present}</td>
            <td>{h(gap.data_path)}</td>
            <td>{h(gap.why_it_matters)}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Coverage Gaps</h2>
            <p class="summary">Areas of the bundle not examined by any scanner</p>
            <table>
                <thead><tr><th>Severity</th><th>Area</th><th>Data Present</th><th>Path</th><th>Why It Matters</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_log_diag_section(analysis: Any, h: Any) -> str:
    """Build the AI log diagnoses section."""
    log_diagnoses = getattr(analysis, "log_diagnoses", None) or []
    if not log_diagnoses:
        return ""
    rows = ""
    for diag in log_diagnoses:
        pod_label = f"{h(getattr(diag, 'namespace', ''))}/{h(getattr(diag, 'pod_name', ''))}"
        category = getattr(diag, "root_cause_category", "unknown")
        cat_colors = {
            "oom": ("background:#7f1d1d;color:#f87171;", "OOM"),
            "config_error": ("background:#78350f;color:#fbbf24;", "CONFIG ERROR"),
            "dependency_failure": ("background:#1e1b4b;color:#a5b4fc;", "DEPENDENCY FAILURE"),
        }
        cat_style, cat_label = cat_colors.get(
            category,
            ("background:#1e2433;color:#9ca3af;", h(category).upper()),
        )
        diagnosis_text = h(getattr(diag, "diagnosis", ""))
        key_line = h(getattr(diag, "key_log_line", ""))
        fix_desc = h(getattr(diag, "fix_description", ""))
        fix_cmds = getattr(diag, "fix_commands", []) or []
        fix_html = fix_desc
        if fix_cmds:
            cmds_text = "\n".join(h(cmd) for cmd in fix_cmds)
            fix_html += f'<pre style="background:#0a0e17;padding:8px;border-radius:4px;margin-top:4px;font-size:0.75rem;overflow-x:auto">{cmds_text}</pre>'
        confidence = getattr(diag, "confidence", 0.0) or 0.0
        rows += f"""<tr>
            <td>{pod_label}</td>
            <td><span class="badge" style="{cat_style}">{cat_label}</span></td>
            <td>{diagnosis_text}</td>
            <td><code style="font-size:0.75rem;color:#a5b4fc">{key_line}</code></td>
            <td>{fix_html}</td>
            <td>{round(confidence * 100)}%</td>
        </tr>"""
    return f"""
        <section>
            <h2>AI Log Diagnoses</h2>
            <table>
                <thead><tr><th>Pod</th><th>Category</th><th>Diagnosis</th><th>Key Log Line</th><th>Fix</th><th>Confidence</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_anomaly_section(triage: Any, h: Any) -> str:
    """Build the pod anomalies section."""
    pod_anomalies = getattr(triage, "pod_anomalies", None) or []
    if not pod_anomalies:
        return ""
    rows = ""
    anomaly_type_colors = {
        "node_placement": "background:#1e1b4b;color:#a5b4fc;",
        "image_version": "background:#78350f;color:#fbbf24;",
        "resource_limits": "background:#7f1d1d;color:#f87171;",
        "env_config": "background:#78350f;color:#fbbf24;",
        "labels_annotations": "background:#1e2433;color:#9ca3af;",
        "restart_pattern": "background:#7f1d1d;color:#f87171;",
    }
    for anom in pod_anomalies:
        atype = getattr(anom, "anomaly_type", "unknown")
        atype_style = anomaly_type_colors.get(atype, "background:#1e2433;color:#9ca3af;")
        rows += f"""<tr>
            <td>{h(getattr(anom, 'failing_pod', ''))}</td>
            <td><span class="badge" style="{atype_style}">{h(atype).upper().replace('_', ' ')}</span></td>
            <td>{h(getattr(anom, 'description', ''))}</td>
            <td><code style="font-size:0.75rem">{h(getattr(anom, 'failing_value', ''))}</code></td>
            <td><code style="font-size:0.75rem">{h(getattr(anom, 'healthy_value', ''))}</code></td>
            <td>{h(getattr(anom, 'suggestion', ''))}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Pod Anomalies</h2>
            <table>
                <thead><tr><th>Failing Pod</th><th>Anomaly Type</th><th>Description</th><th>Failing Value</th><th>Healthy Value</th><th>Suggestion</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_dep_section(triage: Any, h: Any) -> str:
    """Build the broken dependencies section."""
    dep_map = getattr(triage, "dependency_map", None)
    if not dep_map:
        return ""
    total_svc = getattr(dep_map, "total_services_discovered", 0) or 0
    total_broken = getattr(dep_map, "total_broken", 0) or 0
    broken_deps = getattr(dep_map, "broken_dependencies", []) or []
    if not broken_deps:
        return ""
    rows = ""
    for dep in broken_deps:
        sev = getattr(dep, "severity", "info")
        rows += f"""<tr>
            <td>{h(getattr(dep, 'source_pod', ''))}</td>
            <td>{h(getattr(dep, 'target_service', ''))}</td>
            <td><span class="badge info">{h(getattr(dep, 'discovery_method', '')).upper().replace('_', ' ')}</span></td>
            <td><span class="badge fail">BROKEN</span></td>
            <td>{h(getattr(dep, 'health_detail', ''))}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Broken Dependencies</h2>
            <p class="summary">{total_svc} services discovered, {total_broken} broken</p>
            <table>
                <thead><tr><th>Source Pod</th><th>Target Service</th><th>Discovery Method</th><th>Health Status</th><th>Detail</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""


def _build_change_section(triage: Any, h: Any) -> str:
    """Build the change correlations section."""
    change_report = getattr(triage, "change_report", None)
    if not change_report:
        return ""
    correlations = getattr(change_report, "correlations", []) or []
    if not correlations:
        return ""
    rows = ""
    for corr in correlations:
        strength = getattr(corr, "correlation_strength", "moderate")
        strength_colors = {
            "strong": ("background:#7f1d1d;color:#f87171;", "STRONG"),
            "moderate": ("background:#78350f;color:#fbbf24;", "MODERATE"),
            "weak": ("background:#1e2433;color:#9ca3af;", "WEAK"),
        }
        s_style, s_label = strength_colors.get(
            strength,
            ("background:#1e2433;color:#9ca3af;", h(strength).upper()),
        )
        change = getattr(corr, "change", None)
        resource_name = ""
        change_type = ""
        if change:
            ns = getattr(change, "namespace", "")
            rtype = getattr(change, "resource_type", "")
            rname = getattr(change, "resource_name", "")
            resource_name = f"{h(rtype)}/{h(ns)}/{h(rname)}" if ns else f"{h(rtype)}/{h(rname)}"
            change_type = getattr(change, "change_type", "")
        # Format time delta as human readable
        delta_secs = getattr(corr, "time_delta_seconds", 0) or 0
        if delta_secs < 60:
            time_str = f"{int(delta_secs)}s"
        elif delta_secs < 3600:
            time_str = f"{int(delta_secs // 60)}m {int(delta_secs % 60)}s"
        else:
            hrs = int(delta_secs // 3600)
            mins = int((delta_secs % 3600) // 60)
            time_str = f"{hrs}h {mins}m"
        explanation = h(getattr(corr, "explanation", ""))
        rows += f"""<tr>
            <td><span class="badge" style="{s_style}">{s_label}</span></td>
            <td>{resource_name}</td>
            <td><span class="badge info">{h(change_type).upper().replace('_', ' ')}</span></td>
            <td>{h(time_str)}</td>
            <td>{explanation}</td>
        </tr>"""
    return f"""
        <section>
            <h2>Change Correlations</h2>
            <table>
                <thead><tr><th>Strength</th><th>Resource</th><th>Change Type</th><th>Time Before Failure</th><th>Explanation</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </section>"""
