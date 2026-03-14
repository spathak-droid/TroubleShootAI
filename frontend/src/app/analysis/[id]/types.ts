export interface StageState {
  status: "pending" | "running" | "complete" | "failed";
}

export interface AnalysisSummary {
  critical: number;
  warning: number;
  info: number;
  crashLoops: number;
  escalations: number;
  coverageGaps: number;
  anomalies: number;
  brokenDeps: number;
  changeCorrelations: number;
  logDiagnoses: number;
}
