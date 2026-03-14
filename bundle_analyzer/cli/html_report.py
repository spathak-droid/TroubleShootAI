"""HTML report generation for Bundle Analyzer CLI.

Generates a standalone HTML report with inline CSS from an AnalysisResult.
"""

from __future__ import annotations

import html
from datetime import datetime

from bundle_analyzer.models import AnalysisResult


def _generate_html_report(result: AnalysisResult) -> str:
    """Generate a standalone HTML report with inline CSS.

    Args:
        result: Complete analysis result.

    Returns:
        HTML string with the full report.
    """
    triage = result.triage
    n_critical = len(triage.critical_pods)
    n_high = len(triage.warning_pods) + len(triage.node_issues)
    n_medium = (
        len(triage.deployment_issues)
        + len(triage.config_issues)
        + len(triage.drift_issues)
    )

    def _esc(text: str) -> str:
        return html.escape(str(text))

    # Build findings HTML
    findings_html = ""
    for f in result.findings[:20]:
        sev_class = f.severity
        fix_html = ""
        if f.fix:
            cmds = "".join(f"<code>$ {_esc(c)}</code><br>" for c in f.fix.commands[:3])
            fix_html = f"""
            <div class="fix">
                <strong>Fix:</strong> {_esc(f.fix.description)}<br>
                {cmds}
                <span class="risk risk-{f.fix.risk}">Risk: {_esc(f.fix.risk)}</span>
            </div>"""

        evidence_html = ""
        for ev in f.evidence[:3]:
            evidence_html += f"""
            <div class="evidence">
                <div class="evidence-file">{_esc(ev.file)}</div>
                <pre class="yaml-block">{_esc(ev.excerpt)}</pre>
            </div>"""

        findings_html += f"""
        <div class="finding finding-{sev_class}">
            <div class="finding-header">
                <span class="severity-badge severity-{sev_class}">{_esc(f.severity.upper())}</span>
                <span class="finding-resource">{_esc(f.resource)}</span>
                <span class="confidence">{f.confidence:.0%}</span>
            </div>
            <div class="finding-body">
                <p><strong>Symptom:</strong> {_esc(f.symptom)}</p>
                <p><strong>Root cause:</strong> {_esc(f.root_cause)}</p>
                {fix_html}
                {evidence_html}
            </div>
        </div>"""

    # Triage table rows
    triage_rows = ""
    for label, items, fmt in [
        ("Critical Pods", triage.critical_pods,
         lambda p: f"{p.namespace}/{p.pod_name} ({p.issue_type})"),
        ("Warning Pods", triage.warning_pods,
         lambda p: f"{p.namespace}/{p.pod_name} ({p.issue_type})"),
        ("Node Issues", triage.node_issues,
         lambda n: f"{n.node_name} ({n.condition})"),
        ("Deployment Issues", triage.deployment_issues,
         lambda d: f"{d.namespace}/{d.name} ({d.issue})"),
        ("Config Issues", triage.config_issues,
         lambda c: f"{c.resource_type}/{c.resource_name} ({c.issue})"),
        ("Silence Signals", triage.silence_signals,
         lambda s: f"{s.namespace}/{s.pod_name} ({s.signal_type})"),
    ]:
        if items:
            details = ", ".join(_esc(fmt(i)) for i in items[:5])
            if len(items) > 5:
                details += f" ... +{len(items) - 5} more"
            triage_rows += f"<tr><td>{_esc(label)}</td><td>{len(items)}</td><td>{details}</td></tr>"

    # Timeline rows
    timeline_rows = ""
    for ev in result.timeline[:30]:
        ts_str = ev.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        ns = f"{ev.namespace}/" if ev.namespace else ""
        timeline_rows += f"""
        <tr>
            <td>{_esc(ts_str)}</td>
            <td>{_esc(ev.event_type)}</td>
            <td>{_esc(ns + ev.resource_name)}</td>
            <td>{_esc(ev.description[:100])}</td>
        </tr>"""

    # Predictions
    predictions_html = ""
    for p in result.predictions[:5]:
        eta = f"~{p.estimated_eta_seconds}s" if p.estimated_eta_seconds else "imminent"
        predictions_html += f"""
        <div class="prediction">
            <strong>{_esc(p.failure_type)}</strong> on {_esc(p.resource)}<br>
            ETA: {_esc(eta)} | Confidence: {p.confidence:.0%}<br>
            Prevention: {_esc(p.prevention)}
        </div>"""

    # Uncertainty
    uncertainty_html = ""
    for g in result.uncertainty[:10]:
        uncertainty_html += f"""
        <div class="gap gap-{g.impact.lower()}">
            <strong>[{_esc(g.impact)}]</strong> {_esc(g.question)}<br>
            <span class="gap-reason">{_esc(g.reason)}</span>
            {f'<br><code>{_esc(g.collect_command)}</code>' if g.collect_command else ''}
        </div>"""

    root_cause_html = ""
    if result.root_cause:
        root_cause_html = f"""
        <section class="section">
            <h2>Root Cause</h2>
            <div class="root-cause-box">{_esc(result.root_cause)}</div>
        </section>"""

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bundle_name = _esc(str(result.bundle_metadata.bundle_path.name))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bundle Analysis Report - {bundle_name}</title>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #c9d1d9; --text-dim: #8b949e; --accent: #58a6ff;
    --red: #ff7b72; --yellow: #d29922; --green: #3fb950; --magenta: #bc8cff;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
         background: var(--bg); color: var(--text); padding: 2rem; line-height: 1.6; }}
  h1 {{ color: var(--accent); margin-bottom: 0.5rem; }}
  h2 {{ color: var(--accent); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
  .meta {{ color: var(--text-dim); margin-bottom: 2rem; }}
  .section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
              padding: 1.5rem; margin-bottom: 1.5rem; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
                   gap: 1rem; margin-bottom: 1rem; }}
  .summary-card {{ text-align: center; padding: 1rem; border-radius: 6px; border: 1px solid var(--border); }}
  .summary-card .count {{ font-size: 2rem; font-weight: bold; }}
  .summary-card.critical .count {{ color: var(--red); }}
  .summary-card.high .count {{ color: var(--yellow); }}
  .summary-card.medium .count {{ color: var(--accent); }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 1rem; }}
  th, td {{ padding: 0.5rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--accent); }}
  .finding {{ border: 1px solid var(--border); border-radius: 6px; padding: 1rem;
              margin-bottom: 1rem; background: var(--surface); }}
  .finding-critical {{ border-left: 4px solid var(--red); }}
  .finding-warning {{ border-left: 4px solid var(--yellow); }}
  .finding-info {{ border-left: 4px solid var(--text-dim); }}
  .finding-header {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 0.5rem; }}
  .severity-badge {{ padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }}
  .severity-critical {{ background: var(--red); color: #fff; }}
  .severity-warning {{ background: var(--yellow); color: #000; }}
  .severity-info {{ background: var(--text-dim); color: #fff; }}
  .finding-resource {{ font-weight: bold; }}
  .confidence {{ color: var(--text-dim); margin-left: auto; }}
  .fix {{ background: #0d2818; border: 1px solid var(--green); border-radius: 4px;
          padding: 0.75rem; margin-top: 0.5rem; }}
  .risk {{ font-size: 0.8rem; padding: 2px 6px; border-radius: 3px; }}
  .risk-safe {{ background: var(--green); color: #000; }}
  .risk-disruptive {{ background: var(--red); color: #fff; }}
  .risk-needs-verification {{ background: var(--yellow); color: #000; }}
  .evidence {{ margin-top: 0.5rem; }}
  .evidence-file {{ color: var(--accent); font-size: 0.85rem; }}
  .yaml-block {{ background: #1a1e24; border: 1px solid var(--border); border-radius: 4px;
                 padding: 0.75rem; overflow-x: auto; font-family: 'SFMono-Regular', Consolas, monospace;
                 font-size: 0.85rem; white-space: pre-wrap; color: var(--green); }}
  .root-cause-box {{ background: #2a1215; border: 1px solid var(--red); border-radius: 4px;
                     padding: 1rem; font-weight: bold; }}
  .gap {{ padding: 0.5rem; border-left: 3px solid var(--border); margin-bottom: 0.5rem; }}
  .gap-high {{ border-left-color: var(--red); }}
  .gap-medium {{ border-left-color: var(--yellow); }}
  .gap-low {{ border-left-color: var(--text-dim); }}
  .gap-reason {{ color: var(--text-dim); font-size: 0.9rem; }}
  .prediction {{ padding: 0.75rem; border: 1px solid var(--yellow); border-radius: 4px;
                 margin-bottom: 0.5rem; }}
  code {{ background: #1a1e24; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
</style>
</head>
<body>
<h1>Bundle Analysis Report</h1>
<p class="meta">Bundle: {bundle_name} | Generated: {now_str} | Duration: {result.analysis_duration_seconds:.1f}s</p>

<section class="section">
  <h2>Summary</h2>
  <div class="summary-grid">
    <div class="summary-card critical"><div class="count">{n_critical}</div><div>Critical</div></div>
    <div class="summary-card high"><div class="count">{n_high}</div><div>High</div></div>
    <div class="summary-card medium"><div class="count">{n_medium}</div><div>Medium</div></div>
  </div>
  <p style="color:var(--text-dim)">{_esc(result.cluster_summary)}</p>
</section>

<section class="section">
  <h2>Triage Findings</h2>
  <table>
    <tr><th>Category</th><th>Count</th><th>Details</th></tr>
    {triage_rows}
  </table>
</section>

{root_cause_html}

{'<section class="section"><h2>AI Findings</h2>' + findings_html + '</section>' if findings_html else ''}

{'<section class="section"><h2>Timeline</h2><table><tr><th>Time</th><th>Type</th><th>Resource</th><th>Description</th></tr>' + timeline_rows + '</table></section>' if timeline_rows else ''}

{'<section class="section"><h2>Predicted Failures</h2>' + predictions_html + '</section>' if predictions_html else ''}

{'<section class="section"><h2>What I Cannot Tell You</h2>' + uncertainty_html + '</section>' if uncertainty_html else ''}

</body>
</html>"""
