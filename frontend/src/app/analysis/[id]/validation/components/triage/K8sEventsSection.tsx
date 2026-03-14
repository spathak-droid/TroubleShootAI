"use client";

import { motion } from "framer-motion";
import { Clock } from "lucide-react";
import type { K8sEvent } from "@/lib/types";

export function K8sEventsSection({ events }: { events: K8sEvent[] }) {
  if (events.length === 0) return null;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <Clock size={16} style={{ color: "var(--warning)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>Warning Events</h2>
        <span className="badge badge-muted text-[10px] ml-1">{events.length}</span>
      </div>
      <div className="flex flex-col gap-1">
        {events.slice(0, 30).map((event, i) => (
          <div key={`evt-${i}`} className="flex items-start gap-3 rounded-lg px-3 py-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
                  style={{ backgroundColor: event.type === "Warning" ? "rgba(234, 179, 8, 0.15)" : "rgba(99, 102, 241, 0.1)",
                    color: event.type === "Warning" ? "var(--warning)" : "var(--accent-light)" }}>
                  {event.type}
                </span>
                <span className="text-sm font-medium" style={{ color: "var(--foreground-bright)" }}>
                  {event.involved_object_kind ? `${event.involved_object_kind}/` : ""}{event.involved_object_name || event.involved_object}
                </span>
                <span className="text-[10px] font-mono rounded px-1.5 py-0.5"
                  style={{ backgroundColor: "rgba(239, 68, 68, 0.1)", color: "var(--critical)" }}>
                  {event.reason}
                </span>
                {(event.count ?? 0) > 1 && (
                  <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>x{event.count}</span>
                )}
              </div>
              {event.message && (
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{event.message}</p>
              )}
            </div>
          </div>
        ))}
        {events.length > 30 && (
          <p className="text-xs px-3 py-2" style={{ color: "var(--muted)" }}>
            ...and {events.length - 30} more events
          </p>
        )}
      </div>
    </motion.div>
  );
}
