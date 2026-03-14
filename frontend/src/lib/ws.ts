export interface ProgressMessage {
  stage?: string;
  status?: "pending" | "running" | "complete" | "failed";
  progress?: number;
  pct?: number;
  message?: string;
  findings_so_far?: number;
  error?: string;
}

export function createProgressSocket(
  bundleId: string,
  onMessage: (msg: ProgressMessage) => void,
  onClose?: () => void,
  onError?: (err: Event) => void,
): WebSocket {
  const wsBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/^http/, "ws");
  const ws = new WebSocket(
    `${wsBase}/api/v1/ws/${bundleId}/progress`,
  );

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as ProgressMessage;
      onMessage(data);
    } catch {
      // ignore non-JSON frames
    }
  };

  ws.onclose = () => {
    onClose?.();
  };

  ws.onerror = (err) => {
    onError?.(err);
  };

  return ws;
}
