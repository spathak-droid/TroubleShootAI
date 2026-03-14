"use client";

import { motion } from "framer-motion";
import { EyeOff } from "lucide-react";
import type { SilenceSignal } from "@/lib/types";
import { SeverityBadge } from "./helpers";

export function SilenceSignalsSection({ signals }: { signals: SilenceSignal[] }) {
  if (signals.length === 0) return null;

  const displayName = (signal: SilenceSignal): string => {
    if (signal.resource) return signal.resource;
    if (signal.pod_name) {
      const ns = signal.namespace ? `${signal.namespace}/` : "";
      const container = signal.container_name ? ` (${signal.container_name})` : "";
      return `${ns}${signal.pod_name}${container}`;
    }
    return signal.signal_type;
  };

  const displayMessage = (signal: SilenceSignal): string | undefined => {
    return signal.message || signal.note || undefined;
  };

  const signalTypeLabel: Record<string, string> = {
    LOG_FILE_MISSING: "No log file collected",
    EMPTY_LOG_RUNNING_POD: "Empty logs from running pod",
    PREVIOUS_LOG_MISSING: "Pre-crash logs missing",
    RBAC_BLOCKED: "RBAC blocked collection",
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg flex-shrink-0" style={{ background: "rgba(107, 114, 128, 0.12)" }}>
          <EyeOff size={14} style={{ color: "var(--muted)" }} />
        </div>
        <div>
          <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>Silence Signals</h2>
          <p className="text-[10px]" style={{ color: "var(--muted)" }}>
            Missing or empty data that should be present — silence can be a symptom
          </p>
        </div>
        <span className="badge badge-muted text-[10px] ml-auto">{signals.length}</span>
      </div>
      <div className="flex flex-col gap-1">
        {signals.map((signal, i) => (
          <div key={`silence-${i}`} className="flex items-start gap-3 rounded-xl px-4 py-2.5" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div
              className="flex h-7 w-7 items-center justify-center rounded-lg flex-shrink-0 mt-0.5"
              style={{
                background: signal.severity === "critical" ? "rgba(239, 68, 68, 0.12)" : "rgba(245, 158, 11, 0.12)",
              }}
            >
              <EyeOff size={12} style={{ color: signal.severity === "critical" ? "var(--critical)" : "var(--warning)" }} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityBadge severity={signal.severity} />
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                  {displayName(signal)}
                </span>
              </div>
              <p className="mt-0.5 text-xs" style={{ color: "var(--accent-light)" }}>
                {signalTypeLabel[signal.signal_type] ?? signal.signal_type}
              </p>
              {displayMessage(signal) && (
                <p className="mt-0.5 text-xs" style={{ color: "var(--muted)" }}>{displayMessage(signal)}</p>
              )}
              {signal.possible_causes && signal.possible_causes.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {signal.possible_causes.map((cause, ci) => (
                    <span key={ci} className="text-[10px] rounded px-1.5 py-0.5" style={{ background: "rgba(0,0,0,0.2)", color: "var(--muted)" }}>
                      {cause}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
