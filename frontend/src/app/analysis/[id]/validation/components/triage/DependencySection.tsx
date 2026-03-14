"use client";

import { motion } from "framer-motion";
import { Link2Off } from "lucide-react";
import type { DependencyMap } from "@/lib/types";
import { SeverityBadge, discoveryMethodColors } from "./helpers";

export function DependencySection({
  dependencyMap,
}: {
  dependencyMap: DependencyMap;
}) {
  const broken = dependencyMap.broken_dependencies;
  if (broken.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <Link2Off size={16} style={{ color: "var(--critical)" }} />
        <h2 className="text-base font-semibold" style={{ color: "var(--foreground-bright)" }}>
          Broken Service Dependencies
        </h2>
        <span className="badge badge-muted text-[10px] ml-1">{broken.length}</span>
      </div>
      <p className="text-xs mb-3" style={{ color: "var(--muted)" }}>
        {dependencyMap.total_services_discovered} services discovered, {dependencyMap.total_broken} broken
      </p>
      <div className="flex flex-col">
        {broken.map((dep, i) => {
          const methodStyle = discoveryMethodColors[dep.discovery_method] ?? discoveryMethodColors.env_var;
          return (
            <motion.div
              key={`dep-${i}`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3 rounded-lg px-3 py-2.5"
              style={{ borderBottom: "1px solid var(--border-subtle)" }}
            >
              <Link2Off size={14} style={{ color: "var(--critical)", marginTop: 2 }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <SeverityBadge severity={dep.severity} />
                  <span className="text-sm font-medium font-mono" style={{ color: "var(--foreground-bright)" }}>
                    {dep.source_pod}
                  </span>
                  <span style={{ color: "var(--muted)" }}>&#8594;</span>
                  <span className="text-sm font-medium font-mono" style={{ color: "var(--accent-light)" }}>
                    {dep.target_service}
                    {dep.target_namespace && <span className="text-[10px]" style={{ color: "var(--muted)" }}>.{dep.target_namespace}</span>}
                  </span>
                  <span
                    className="text-[10px] font-semibold uppercase rounded px-1.5 py-0.5"
                    style={{ backgroundColor: methodStyle.bg, color: methodStyle.color }}
                  >
                    {dep.discovery_method.replace(/_/g, " ")}
                  </span>
                </div>
                {dep.health_detail && (
                  <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{dep.health_detail}</p>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
