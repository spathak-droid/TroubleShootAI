"use client";

import { motion } from "framer-motion";
import { Brain } from "lucide-react";
import type { DisplayFinding } from "./types";

export function FindingInline({ finding }: { finding: DisplayFinding }) {
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2 }}
      className="overflow-hidden"
    >
      <div
        className="mx-3 mb-3 mt-1 rounded-xl p-4 flex flex-col gap-3"
        style={{ backgroundColor: "rgba(10, 14, 23, 0.6)", border: "1px solid var(--border-subtle)" }}
      >
        <div className="flex items-center gap-2">
          <Brain size={12} style={{ color: "var(--accent-light)" }} />
          <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: "var(--accent-light)" }}>
            AI Insight
          </span>
          <div className="flex items-center gap-1 ml-auto">
            <div className="h-1.5 w-16 rounded-full overflow-hidden" style={{ background: "var(--border-subtle)" }}>
              <div className="h-full rounded-full" style={{ width: `${finding.confidence * 100}%`, background: "var(--accent-light)" }} />
            </div>
            <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
              {Math.round(finding.confidence * 100)}%
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--muted)" }}>Symptom</p>
            <p className="text-xs" style={{ color: "var(--foreground)" }}>{finding.symptom}</p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider mb-0.5" style={{ color: "var(--muted)" }}>Root Cause</p>
            <p className="text-xs" style={{ color: "var(--foreground)" }}>{finding.root_cause}</p>
          </div>
        </div>

        {finding.fixes.length > 0 && (
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--muted)" }}>Fixes</p>
            {finding.fixes.map((fix, i) => (
              <div key={i} className="rounded-lg p-2.5 mb-1" style={{ backgroundColor: "rgba(10, 14, 23, 0.4)", border: "1px solid var(--border-subtle)" }}>
                <p className="text-xs" style={{ color: "var(--foreground)" }}>{(fix.description as string) ?? ""}</p>
                {Array.isArray(fix.commands) && fix.commands.length > 0 && (
                  <pre className="mt-1.5 text-[11px] font-mono p-2 rounded" style={{ color: "var(--accent-light)", background: "rgba(0,0,0,0.3)" }}>
                    {fix.commands.join("\n")}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}

        {finding.evidence.length > 0 && (
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider mb-1" style={{ color: "var(--muted)" }}>Evidence</p>
            {finding.evidence.map((ev, i) => (
              <div key={i} className="mb-2">
                <p className="text-[10px] font-mono" style={{ color: "var(--accent-light)" }}>
                  {ev.file}{ev.line_start != null && `:${ev.line_start}`}{ev.line_end != null && `-${ev.line_end}`}
                </p>
                <pre
                  className="mt-0.5 overflow-auto rounded-lg p-2.5 text-[11px] leading-relaxed"
                  style={{ backgroundColor: "rgba(10, 14, 23, 0.6)", border: "1px solid var(--border-subtle)", color: "var(--foreground)" }}
                >
                  {ev.content}
                </pre>
                {ev.relevance && <p className="mt-0.5 text-[10px]" style={{ color: "var(--muted)" }}>{ev.relevance}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}
