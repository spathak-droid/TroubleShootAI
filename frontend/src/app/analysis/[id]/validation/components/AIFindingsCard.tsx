"use client";

import { motion, AnimatePresence } from "framer-motion";
import { XCircle, AlertTriangle, Brain, ChevronDown } from "lucide-react";
import type { DisplayFinding } from "../../shared";
import { FindingInline } from "../../shared";

export function AIFindingsCard({
  findings,
  expandedId,
  onToggle,
}: {
  findings: DisplayFinding[];
  expandedId: string | null;
  onToggle: (id: string) => void;
}) {
  if (findings.length === 0) return null;

  const severityIcon = (sev: string) => {
    if (sev === "critical") return <XCircle size={12} style={{ color: "var(--critical)" }} />;
    if (sev === "warning") return <AlertTriangle size={12} style={{ color: "var(--warning)" }} />;
    return <Brain size={12} style={{ color: "var(--info)" }} />;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <Brain size={16} style={{ color: "var(--accent-light)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          AI Findings
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{findings.length}</span>
      </div>
      <div className="flex flex-col">
        {findings.map((f, i) => {
          const rowKey = `ai-${i}`;
          const isOpen = expandedId === rowKey;
          return (
            <div key={f.id}>
              <div
                className="flex items-start gap-3 rounded-lg px-3 py-2.5 cursor-pointer transition-colors hover:bg-white/[0.02]"
                style={{ borderBottom: "1px solid var(--border-subtle)" }}
                onClick={() => onToggle(rowKey)}
              >
                {severityIcon(f.severity)}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`badge badge-${f.severity}`}>{f.severity.toUpperCase()}</span>
                    <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                      {f.title}
                    </span>
                    <span className="badge badge-muted text-[10px]">{f.category}</span>
                  </div>
                  <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{f.symptom}</p>
                </div>
                <ChevronDown
                  size={14}
                  style={{ color: "var(--muted)", transition: "transform 0.2s", transform: isOpen ? "rotate(180deg)" : "rotate(0deg)", flexShrink: 0 }}
                />
              </div>
              <AnimatePresence>
                {isOpen && <FindingInline finding={f} />}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
