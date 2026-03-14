"use client";

export const crashPatternColors: Record<string, { bg: string; color: string }> = {
  oom: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--critical)" },
  segfault: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--critical)" },
  panic: { bg: "rgba(249, 115, 22, 0.15)", color: "#f97316" },
  config_error: { bg: "rgba(234, 179, 8, 0.15)", color: "var(--warning)" },
  dependency_timeout: { bg: "rgba(96, 165, 250, 0.15)", color: "#60a5fa" },
  unknown: { bg: "rgba(107, 114, 128, 0.15)", color: "var(--muted)" },
};

export const escalationTypeColors: Record<string, { bg: string; color: string }> = {
  repeated: { bg: "rgba(234, 179, 8, 0.15)", color: "var(--warning)" },
  cascading: { bg: "rgba(249, 115, 22, 0.15)", color: "#f97316" },
  sustained: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--critical)" },
};

export const rootCauseCategoryColors: Record<string, { bg: string; color: string }> = {
  oom: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--critical)" },
  config_error: { bg: "rgba(234, 179, 8, 0.15)", color: "var(--warning)" },
  dependency_failure: { bg: "rgba(96, 165, 250, 0.15)", color: "#60a5fa" },
  code_bug: { bg: "rgba(168, 85, 247, 0.15)", color: "#a855f7" },
  unknown: { bg: "rgba(107, 114, 128, 0.15)", color: "var(--muted)" },
};

export const anomalyTypeColors: Record<string, { bg: string; color: string }> = {
  node_placement: { bg: "rgba(249, 115, 22, 0.15)", color: "#f97316" },
  image_version: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--critical)" },
  resource_limits: { bg: "rgba(234, 179, 8, 0.15)", color: "var(--warning)" },
  env_config: { bg: "rgba(96, 165, 250, 0.15)", color: "#60a5fa" },
  labels_annotations: { bg: "rgba(168, 85, 247, 0.15)", color: "#a855f7" },
  restart_pattern: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--critical)" },
};

export const discoveryMethodColors: Record<string, { bg: string; color: string }> = {
  env_var: { bg: "rgba(96, 165, 250, 0.15)", color: "#60a5fa" },
  connection_string: { bg: "rgba(168, 85, 247, 0.15)", color: "#a855f7" },
  service_ref: { bg: "rgba(34, 197, 94, 0.15)", color: "var(--success)" },
};

export const correlationStrengthColors: Record<string, { bg: string; color: string }> = {
  strong: { bg: "rgba(239, 68, 68, 0.15)", color: "var(--critical)" },
  moderate: { bg: "rgba(234, 179, 8, 0.15)", color: "var(--warning)" },
  weak: { bg: "rgba(107, 114, 128, 0.15)", color: "var(--muted)" },
};

export function SeverityBadge({ severity }: { severity: string }) {
  const sev = severity ?? "info";
  const cls = sev === "critical" ? "badge-critical" : sev === "warning" ? "badge-warning" : "badge-info";
  return <span className={`badge ${cls}`}>{sev.toUpperCase()}</span>;
}

export function formatTimeDelta(seconds: number): string {
  const abs = Math.abs(seconds);
  if (abs < 60) return `${Math.round(abs)} seconds before failure`;
  if (abs < 3600) return `${Math.round(abs / 60)} minutes before failure`;
  if (abs < 86400) return `${(abs / 3600).toFixed(1)} hours before failure`;
  return `${(abs / 86400).toFixed(1)} days before failure`;
}
