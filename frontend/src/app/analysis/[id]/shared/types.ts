import type { Evidence } from "@/lib/types";

export interface DisplayFinding {
  id: string;
  severity: "critical" | "warning" | "info";
  title: string;
  category: string;
  symptom: string;
  root_cause: string;
  evidence: Evidence[];
  fixes: Array<Record<string, unknown>>;
  confidence: number;
}
