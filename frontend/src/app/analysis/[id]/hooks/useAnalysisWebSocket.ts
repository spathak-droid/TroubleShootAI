"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { startAnalysis, getAnalysisStatus, getAnalysis } from "@/lib/api";
import { createProgressSocket } from "@/lib/ws";
import type { ProgressMessage } from "@/lib/ws";
import { STAGES, STAGE_KEY_TO_INDEX } from "../constants";
import { buildStagesFromIndex, computeSummary } from "../utils";
import type { StageState, AnalysisSummary } from "../types";

export function useAnalysisWebSocket(bundleId: string | null) {
  const searchParams = useSearchParams();
  const contextParam = searchParams.get("context") ?? undefined;

  const [pageState, setPageState] = useState<"loading" | "ready" | "running" | "complete" | "failed">("loading");
  const [stages, setStages] = useState<StageState[]>(
    STAGES.map(() => ({ status: "pending" })),
  );
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [findingsCount, setFindingsCount] = useState(0);
  const [summary, setSummary] = useState<AnalysisSummary | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const receivedMessages = useRef(false);

  const handleMessage = useCallback((msg: ProgressMessage) => {
    receivedMessages.current = true;

    const pctValue = msg.progress ?? (msg.pct != null ? msg.pct * 100 : undefined);
    if (pctValue != null) setProgress(pctValue);
    if (msg.message) setMessage(msg.message);
    if (msg.error) setMessage(msg.error);
    if (msg.findings_so_far != null) setFindingsCount(msg.findings_so_far);

    const rawStage = msg.stage;
    if (!rawStage || rawStage === "heartbeat") return;

    const stageIdx = STAGE_KEY_TO_INDEX[rawStage];

    setStages((prev) => {
      if (rawStage === "complete") {
        return prev.map(() => ({ status: "complete" as const }));
      }
      if (stageIdx != null) {
        return buildStagesFromIndex(stageIdx, false);
      }
      return prev;
    });

    if (rawStage === "complete") {
      setProgress(100);
      setPageState("complete");
    }
    if (rawStage === "error" || msg.status === "failed") {
      setPageState("failed");
    }
  }, []);

  const connectWs = useCallback((bid: string) => {
    receivedMessages.current = false;
    wsRef.current?.close();
    wsRef.current = createProgressSocket(
      bid,
      handleMessage,
      () => {
        if (!receivedMessages.current) {
          setPageState("failed");
          setMessage("Lost connection to analysis server");
        }
      },
    );
  }, [handleMessage]);

  // Initial status check
  useEffect(() => {
    if (!bundleId) return;
    let cancelled = false;

    (async () => {
      try {
        const status = await getAnalysisStatus(bundleId);
        if (cancelled) return;

        if (status.status === "complete") {
          setPageState("complete");
          setProgress(100);
          setMessage("Analysis complete");
          setStages(STAGES.map(() => ({ status: "complete" })));
          try {
            const result = await getAnalysis(bundleId) as unknown as Record<string, unknown>;
            if (cancelled) return;
            const { summary: s, total } = computeSummary(result);
            setSummary(s);
            setFindingsCount(total);
          } catch {
            // analysis fetch failed
          }
        } else if (status.status === "error") {
          setPageState("failed");
          setMessage(status.message || "Analysis failed");
        } else if (["extracting", "triaging", "analyzing"].includes(status.status)) {
          setPageState("running");
          setProgress((status.progress ?? 0) * 100);
          setMessage(status.message || "Analysis in progress...");
          const stageIdx = STAGE_KEY_TO_INDEX[status.current_stage] ?? 0;
          setStages(buildStagesFromIndex(stageIdx, false));
          connectWs(bundleId);
        } else {
          setPageState("ready");
        }
      } catch {
        // Status endpoint failed (session not in memory).
        // Try loading analysis directly from DB.
        if (cancelled) return;
        try {
          const result = await getAnalysis(bundleId) as unknown as Record<string, unknown>;
          if (cancelled) return;
          const { summary: s, total } = computeSummary(result);
          setSummary(s);
          setFindingsCount(total);
          setPageState("complete");
          setProgress(100);
          setMessage("Analysis complete");
          setStages(STAGES.map(() => ({ status: "complete" })));
        } catch {
          if (!cancelled) setPageState("ready");
        }
      }
    })();

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bundleId]);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  const handleStart = useCallback(async () => {
    if (!bundleId) return;
    setPageState("running");
    setProgress(0);
    setStages(STAGES.map(() => ({ status: "pending" })));
    setSummary(null);

    try {
      await startAnalysis(bundleId, contextParam);
    } catch {
      setPageState("failed");
      setMessage("Failed to start analysis");
      return;
    }

    connectWs(bundleId);
  }, [bundleId, contextParam, connectWs]);

  // Auto-start logic
  const autoStartTriggered = useRef(false);
  useEffect(() => {
    if (pageState === "ready" && searchParams.get("autostart") === "1" && !autoStartTriggered.current) {
      autoStartTriggered.current = true;
      handleStart();
    }
  }, [pageState, searchParams, handleStart]);

  // Fetch summary on completion
  useEffect(() => {
    if (pageState !== "complete" || !bundleId) return;
    if (summary) return;

    getAnalysis(bundleId)
      .then((result) => {
        const { summary: s, total } = computeSummary(result as unknown as Record<string, unknown>);
        setSummary(s);
        setFindingsCount(total);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageState, bundleId]);

  return {
    pageState,
    stages,
    progress,
    message,
    findingsCount,
    summary,
    handleStart,
  };
}
