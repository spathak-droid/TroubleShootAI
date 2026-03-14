"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertTriangle, Clock, Shield } from "lucide-react";
import { getTimeline, getPredictions } from "@/lib/api";

export default function TimelinePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const bundleId = typeof id === "string" ? id : null;

  const { data: events, isLoading: eventsLoading } = useQuery({
    queryKey: ["timeline", bundleId],
    queryFn: () => getTimeline(bundleId!),
    enabled: !!bundleId,
  });

  const { data: predictions, isLoading: predsLoading } = useQuery({
    queryKey: ["predictions", bundleId],
    queryFn: () => getPredictions(bundleId!),
    enabled: !!bundleId,
  });

  if (!bundleId) return null;

  const loading = eventsLoading || predsLoading;

  if (loading) {
    return (
      <div className="flex items-center justify-center pt-32">
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Loading timeline...
        </p>
      </div>
    );
  }

  const sortedEvents = [...(events ?? [])].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );

  return (
    <div className="grid grid-cols-3 gap-5">
      {/* Timeline */}
      <div className="col-span-2">
        <h2
          className="mb-5 text-base font-semibold"
          style={{ color: "var(--foreground-bright)" }}
        >
          Event Timeline
        </h2>

        {sortedEvents.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            No timeline events available. Run the analysis first.
          </p>
        ) : (
          <div className="relative flex flex-col">
            <div className="timeline-line" />

            {sortedEvents.map((event, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className="relative flex gap-4 pb-6 pl-9"
              >
                <div className={`timeline-dot ${event.is_trigger ? "trigger" : ""}`} />

                <div className="flex flex-1 flex-col gap-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className="text-xs font-mono"
                      style={{ color: "var(--muted)" }}
                    >
                      {new Date(event.timestamp).toLocaleString()}
                    </span>
                    {event.is_trigger && (
                      <span className="badge badge-critical">
                        TRIGGER
                      </span>
                    )}
                    <span className="badge badge-muted">
                      {event.event_type}
                    </span>
                  </div>
                  <p
                    className="text-sm"
                    style={{ color: "var(--foreground)" }}
                  >
                    {event.description}
                  </p>
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    {event.resource || event.resource_name || ""}
                    {event.namespace ? ` (${event.namespace})` : ""}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      {/* Predictions sidebar */}
      <div className="col-span-1">
        <h2
          className="mb-5 text-base font-semibold"
          style={{ color: "var(--foreground-bright)" }}
        >
          Predictions
        </h2>

        {!predictions || predictions.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            No predictions available.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {predictions.map((pred, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                className="glass-card p-4"
              >
                <div className="mb-2 flex items-center gap-2">
                  <AlertTriangle
                    size={14}
                    style={{ color: "var(--warning)" }}
                  />
                  <span
                    className="text-sm font-medium"
                    style={{ color: "var(--foreground-bright)" }}
                  >
                    {pred.failure_type}
                  </span>
                </div>

                <p className="text-xs" style={{ color: "var(--muted)" }}>
                  {pred.resource}
                  {pred.namespace ? ` (${pred.namespace})` : ""}
                </p>

                <div className="mt-3 flex items-center gap-3">
                  <div className="flex items-center gap-1">
                    <Clock size={12} style={{ color: "var(--muted)" }} />
                    <span className="text-xs" style={{ color: "var(--muted)" }}>
                      ETA: {pred.estimated_eta_seconds != null ? `${(pred.estimated_eta_seconds / 3600).toFixed(1)}h` : pred.eta_hours != null ? `${pred.eta_hours}h` : "now"}
                    </span>
                  </div>
                  <span
                    className="text-xs font-semibold font-mono"
                    style={{
                      color:
                        (pred.probability ?? pred.confidence ?? 0) > 0.7
                          ? "var(--critical)"
                          : (pred.probability ?? pred.confidence ?? 0) > 0.4
                            ? "var(--warning)"
                            : "var(--muted)",
                    }}
                  >
                    {Math.round((pred.probability ?? pred.confidence ?? 0) * 100)}%
                  </span>
                </div>

                <div className="mt-3 flex items-start gap-2">
                  <Shield
                    size={12}
                    className="mt-0.5 flex-shrink-0"
                    style={{ color: "var(--success)" }}
                  />
                  <p className="text-xs" style={{ color: "var(--success)" }}>
                    {pred.prevention}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
