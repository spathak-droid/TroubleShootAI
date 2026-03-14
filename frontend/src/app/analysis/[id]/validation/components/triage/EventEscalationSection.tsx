"use client";

import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, ChevronDown } from "lucide-react";
import type { EventEscalation } from "@/lib/types";
import { SeverityBadge, escalationTypeColors } from "./helpers";

export function EventEscalationSection({
  escalations,
  expandedId,
  onToggle,
}: {
  escalations: EventEscalation[];
  expandedId: string | null;
  onToggle: (id: string) => void;
}) {
  if (escalations.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <TrendingUp size={16} style={{ color: "var(--warning)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          Event Escalation Patterns
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{escalations.length}</span>
      </div>
      <div className="flex flex-col">
        {escalations.map((esc, i) => {
          const rowKey = `esc-${i}`;
          const isOpen = expandedId === rowKey;
          const typeStyle = escalationTypeColors[esc.escalation_type] ?? escalationTypeColors.repeated;
          const timeSpan = esc.first_seen && esc.last_seen
            ? `${new Date(esc.first_seen).toLocaleString()} - ${new Date(esc.last_seen).toLocaleString()}`
            : null;
          return (
            <div key={rowKey}>
              <div
                className="flex items-start gap-3 rounded-lg px-3 py-2.5 cursor-pointer transition-colors hover:bg-white/[0.02]"
                style={{ borderBottom: "1px solid var(--border-subtle)" }}
                onClick={() => onToggle(rowKey)}
              >
                <TrendingUp size={14} style={{ color: typeStyle.color, marginTop: 2 }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <SeverityBadge severity={esc.severity} />
                    <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                      {esc.involved_object_kind}/{esc.involved_object_name}
                    </span>
                    <span
                      className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
                      style={{ backgroundColor: typeStyle.bg, color: typeStyle.color }}
                    >
                      {esc.escalation_type}
                    </span>
                    <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                      {esc.namespace}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-xs" style={{ color: "var(--muted)" }}>
                      {esc.total_count} events
                    </span>
                    {timeSpan && (
                      <span className="text-xs" style={{ color: "var(--muted)" }}>
                        {timeSpan}
                      </span>
                    )}
                  </div>
                  {esc.message && (
                    <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{esc.message}</p>
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
                      className="mx-3 mb-3 mt-1 rounded-lg p-4"
                      style={{ backgroundColor: "rgba(10, 14, 23, 0.5)", border: "1px solid var(--border-subtle)" }}
                    >
                      <p className="text-[10px] font-medium uppercase tracking-wider mb-1.5" style={{ color: "var(--accent-light)" }}>
                        Event Reasons
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {esc.event_reasons.map((reason, j) => (
                          <span
                            key={j}
                            className="text-[10px] font-mono rounded px-1.5 py-0.5"
                            style={{ backgroundColor: "rgba(99, 102, 241, 0.1)", color: "var(--accent-light)" }}
                          >
                            {reason}
                          </span>
                        ))}
                      </div>
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
