export const significanceColors: Record<string, string> = {
  root_cause: "var(--critical)",
  contributing: "var(--warning)",
  symptom: "var(--info)",
  context: "var(--muted)",
};

export const scannerTypeColors: Record<string, string> = {
  probe: "#a78bfa",
  resource: "#f59e0b",
  silence: "#94a3b8",
  event: "#60a5fa",
  config: "#f97316",
  drift: "#e879f9",
  pod: "#ef4444",
  node: "#22d3ee",
  storage: "#84cc16",
  ingress: "#fb923c",
};
