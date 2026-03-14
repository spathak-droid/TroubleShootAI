import type { Evidence } from "@/lib/types";
import type { DisplayFinding } from "./types";

export function normalizeEvidence(raw: Record<string, unknown>): Evidence {
  return {
    file: (raw.file as string) ?? "",
    content: (raw.content as string) ?? (raw.excerpt as string) ?? "",
    line_start: (raw.line_start as number) ?? (raw.line_number as number) ?? undefined,
    line_end: (raw.line_end as number) ?? undefined,
    relevance: (raw.relevance as string) ?? "",
  };
}

export function buildAIFindings(data: Record<string, unknown>): DisplayFinding[] {
  const results: DisplayFinding[] = [];
  const aiFindings = (data.findings ?? []) as Array<Record<string, unknown>>;
  for (const f of aiFindings) {
    const fix = f.fix as Record<string, unknown> | null;
    const rawEvidence = (f.evidence ?? []) as Array<Record<string, unknown>>;
    results.push({
      id: (f.id as string) ?? `ai-${results.length}`,
      severity: (f.severity as "critical" | "warning" | "info") ?? "info",
      title: (f.resource as string) ?? (f.symptom as string) ?? "AI Finding",
      category: (f.type as string) ?? "ai-analysis",
      symptom: (f.symptom as string) ?? "",
      root_cause: (f.root_cause as string) ?? "",
      evidence: rawEvidence.map(normalizeEvidence),
      fixes: fix ? [fix] : [],
      confidence: (f.confidence as number) ?? 0,
    });
  }
  const order = { critical: 0, warning: 1, info: 2 };
  results.sort((a, b) => order[a.severity] - order[b.severity]);
  return results;
}
