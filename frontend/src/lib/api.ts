import type {
  BundleInfo,
  AnalysisResult,
  AnalysisStatus,
  EvaluationResult,
  Finding,
  HistoricalEvent,
  PredictedFailure,
  UncertaintyGap,
  InterviewSession,
  InterviewAnswer,
  InterviewMessage,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// ─── Bundle CRUD ─────────────────────────────────────────────────

export async function uploadBundle(file: File): Promise<BundleInfo> {
  const form = new FormData();
  form.append("file", file);
  const raw = await request<{ bundle_id: string; filename: string; message: string }>(
    "/api/v1/bundles/upload",
    { method: "POST", body: form },
  );
  return { id: raw.bundle_id, filename: raw.filename, status: "uploaded", uploaded_at: new Date().toISOString(), file_size: file.size };
}

export async function listBundles(): Promise<BundleInfo[]> {
  return request<BundleInfo[]>("/api/v1/bundles");
}

export async function deleteBundle(id: string): Promise<void> {
  await request<void>(`/api/v1/bundles/${id}`, { method: "DELETE" });
}

// ─── Analysis ────────────────────────────────────────────────────

export async function startAnalysis(
  id: string,
  context?: string,
): Promise<AnalysisStatus> {
  return request<AnalysisStatus>(`/api/v1/bundles/${id}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ context: context ?? "" }),
  });
}

export async function getAnalysis(id: string): Promise<AnalysisResult> {
  return request<AnalysisResult>(`/api/v1/bundles/${id}/analysis`);
}

export async function getAnalysisStatus(id: string): Promise<AnalysisStatus> {
  return request<AnalysisStatus>(`/api/v1/bundles/${id}/analysis/status`);
}

export async function getFindings(
  id: string,
  filters?: { severity?: string; category?: string },
): Promise<Finding[]> {
  const params = new URLSearchParams();
  if (filters?.severity) params.set("severity", filters.severity);
  if (filters?.category) params.set("category", filters.category);
  const qs = params.toString();
  return request<Finding[]>(
    `/api/v1/bundles/${id}/findings${qs ? `?${qs}` : ""}`,
  );
}

export async function getTimeline(id: string): Promise<HistoricalEvent[]> {
  return request<HistoricalEvent[]>(`/api/v1/bundles/${id}/timeline`);
}

export async function getPredictions(
  id: string,
): Promise<PredictedFailure[]> {
  return request<PredictedFailure[]>(`/api/v1/bundles/${id}/predictions`);
}

export async function getUncertainty(
  id: string,
): Promise<UncertaintyGap[]> {
  return request<UncertaintyGap[]>(`/api/v1/bundles/${id}/uncertainty`);
}

// ─── Evaluation ─────────────────────────────────────

export async function startEvaluation(
  id: string,
): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/v1/bundles/${id}/evaluate`, {
    method: "POST",
  });
}

export async function getEvaluation(
  id: string,
): Promise<EvaluationResult> {
  return request<EvaluationResult>(`/api/v1/bundles/${id}/evaluation`);
}

export async function getEvaluationStatus(
  id: string,
): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/v1/bundles/${id}/evaluation/status`);
}

// ─── Export ─────────────────────────────────────────────────────

async function downloadBlob(url: string, fallbackName: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    let detail = `Export failed (${res.status})`;
    try {
      const parsed = JSON.parse(body);
      if (parsed.detail) detail = parsed.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = res.headers.get("Content-Disposition")?.match(/filename="(.+)"/)?.[1] ?? fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(blobUrl);
}

export async function exportJson(id: string): Promise<void> {
  return downloadBlob(`${BASE}/api/v1/bundles/${id}/export/json`, `analysis-${id}.json`);
}

export async function exportHtml(id: string): Promise<void> {
  return downloadBlob(`${BASE}/api/v1/bundles/${id}/export/html`, `report-${id}.html`);
}

// ─── Interview ───────────────────────────────────────────────────

export async function createInterview(
  id: string,
): Promise<InterviewSession> {
  return request<InterviewSession>(`/api/v1/bundles/${id}/interview`, {
    method: "POST",
  });
}

export async function askQuestion(
  bundleId: string,
  sessionId: string,
  question: string,
): Promise<InterviewAnswer> {
  return request<InterviewAnswer>(
    `/api/v1/bundles/${bundleId}/interview/${sessionId}/ask`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    },
  );
}

export async function askQuestionStream(
  bundleId: string,
  sessionId: string,
  question: string,
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
): Promise<void> {
  const res = await fetch(
    `${BASE}/api/v1/bundles/${bundleId}/interview/${sessionId}/ask/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    },
  );

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    onError(`API ${res.status}: ${body}`);
    onDone();
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    onError("No response stream");
    onDone();
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6);
      if (payload === "[DONE]") {
        onDone();
        return;
      }
      try {
        const parsed = JSON.parse(payload);
        if (parsed.error) {
          onError(parsed.error);
        } else if (parsed.token) {
          onToken(parsed.token);
        }
      } catch {
        // skip malformed chunks
      }
    }
  }
  onDone();
}

export async function getInterviewHistory(
  bundleId: string,
  sessionId: string,
): Promise<InterviewMessage[]> {
  return request<InterviewMessage[]>(
    `/api/v1/bundles/${bundleId}/interview/${sessionId}/history`,
  );
}
