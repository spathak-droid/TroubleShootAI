"use client";

import { motion, AnimatePresence } from "framer-motion";
import { RotateCcw, ChevronDown, EyeOff } from "lucide-react";
import type { CrashLoopContext } from "@/lib/types";
import { SeverityBadge, crashPatternColors } from "./helpers";

export function CrashLoopSection({
  crashes,
  expandedId,
  onToggle,
}: {
  crashes: CrashLoopContext[];
  expandedId: string | null;
  onToggle: (id: string) => void;
}) {
  if (crashes.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <RotateCcw size={16} style={{ color: "var(--critical)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          Crash Loop Analysis
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{crashes.length}</span>
      </div>
      <div className="flex flex-col">
        {crashes.map((crash, i) => {
          const rowKey = `crash-${i}`;
          const isOpen = expandedId === rowKey;
          const patternStyle = crashPatternColors[crash.crash_pattern] ?? crashPatternColors.unknown;
          return (
            <div key={rowKey}>
              <div
                className="flex items-start gap-3 rounded-lg px-3 py-2.5 cursor-pointer transition-colors hover:bg-white/[0.02]"
                style={{ borderBottom: "1px solid var(--border-subtle)" }}
                onClick={() => onToggle(rowKey)}
              >
                <RotateCcw size={14} style={{ color: "var(--critical)", marginTop: 2 }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <SeverityBadge severity={crash.severity} />
                    <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                      {crash.namespace}/{crash.pod_name}
                    </span>
                    <span
                      className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
                      style={{ backgroundColor: patternStyle.bg, color: patternStyle.color }}
                    >
                      {crash.crash_pattern || "unknown"}
                    </span>
                    {crash.container_name && (
                      <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                        {crash.container_name}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-xs" style={{ color: "var(--muted)" }}>
                      {crash.restart_count} restarts
                    </span>
                    {crash.exit_code != null && (
                      <span className="text-xs" style={{ color: "var(--muted)" }}>
                        exit code: {crash.exit_code}
                      </span>
                    )}
                    {crash.termination_reason && (
                      <span className="text-xs" style={{ color: "var(--muted)" }}>
                        {crash.termination_reason}
                      </span>
                    )}
                  </div>
                  {crash.message && (
                    <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{crash.message}</p>
                  )}
                </div>
                <ChevronDown
                  size={14}
                  style={{ color: "var(--muted)", transition: "transform 0.2s", transform: isOpen ? "rotate(180deg)" : "rotate(0deg)", flexShrink: 0 }}
                />
              </div>
              <AnimatePresence>
                {isOpen && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div
                      className="mx-3 mb-3 mt-1 rounded-lg p-4 flex flex-col gap-3"
                      style={{ backgroundColor: "rgba(10, 14, 23, 0.5)", border: "1px solid var(--border-subtle)" }}
                    >
                      {crash.previous_log_lines.length > 0 && (
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--warning)" }}>
                            Previous Container Logs (pre-crash)
                          </p>
                          <pre
                            className="overflow-auto rounded p-3 text-[11px] leading-relaxed font-mono max-h-[300px]"
                            style={{ backgroundColor: "rgba(10, 14, 23, 0.8)", border: "1px solid var(--border-subtle)", color: "var(--foreground)" }}
                          >
                            {crash.previous_log_lines.join("\n")}
                          </pre>
                        </div>
                      )}
                      {crash.last_log_lines.length > 0 && (
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--accent-light)" }}>
                            Current Container Logs
                          </p>
                          <pre
                            className="overflow-auto rounded p-3 text-[11px] leading-relaxed font-mono max-h-[300px]"
                            style={{ backgroundColor: "rgba(10, 14, 23, 0.8)", border: "1px solid var(--border-subtle)", color: "var(--foreground)" }}
                          >
                            {crash.last_log_lines.join("\n")}
                          </pre>
                        </div>
                      )}
                      {crash.previous_log_lines.length === 0 && crash.last_log_lines.length === 0 && (
                        <div className="flex items-center gap-2 py-2">
                          <EyeOff size={14} style={{ color: "var(--muted)" }} />
                          <p className="text-xs" style={{ color: "var(--muted)" }}>
                            No log output captured. The container may be crashing too quickly to produce logs,
                            or log collection was not configured for this pod.
                          </p>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
