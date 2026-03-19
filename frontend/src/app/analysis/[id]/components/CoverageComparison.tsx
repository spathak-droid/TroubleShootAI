"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Shield,
  ShieldAlert,
  AlertTriangle,
  XCircle,
  Info,
  Sparkles,
  Eye,
} from "lucide-react";
import { getCoverageComparison } from "@/lib/api";
import type {
  TroubleshootFoundItem,
  TroubleshootAIFoundItem,
} from "@/lib/types";

/* ── Severity icon helper ─────────────────────────── */

function SeverityIcon({ severity }: { severity: string }) {
  if (severity === "critical")
    return <XCircle size={14} style={{ color: "var(--critical)" }} />;
  if (severity === "warning")
    return <AlertTriangle size={14} style={{ color: "var(--warning)" }} />;
  return <Info size={14} style={{ color: "var(--accent-light)" }} />;
}

/* ── Issue type label helper ──────────────────────── */

function issueTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    pod_issue: "Pod",
    node_issue: "Node",
    deployment_issue: "Deploy",
    config_issue: "Config",
    drift_issue: "Drift",
    silence_signal: "Silence",
    event: "Event",
    probe_issue: "Probe",
    resource_issue: "Resource",
    ingress_issue: "Ingress",
    storage_issue: "Storage",
    rbac_issue: "RBAC",
    quota_issue: "Quota",
    network_policy_issue: "NetPol",
    dns_issue: "DNS",
    tls_issue: "TLS",
    scheduling_issue: "Sched",
    crash_context: "Crash",
    event_escalation: "Escalation",
  };
  return labels[type] ?? type;
}

/* ── Proportional coverage bar ────────────────────── */

function CoverageBar({
  tsCount,
  aiCount,
}: {
  tsCount: number;
  aiCount: number;
}) {
  const total = tsCount + aiCount;
  if (total === 0) return null;
  const tsPct = Math.max((tsCount / total) * 100, 2);
  const aiPct = Math.max((aiCount / total) * 100, 2);

  return (
    <div className="flex flex-col gap-2">
      <div
        className="flex h-3 overflow-hidden rounded-full"
        style={{ background: "var(--border-subtle)" }}
      >
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${tsPct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          style={{ background: "var(--muted)", opacity: 0.5 }}
        />
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${aiPct}%` }}
          transition={{ duration: 0.8, ease: "easeOut", delay: 0.15 }}
          style={{ background: "var(--success)" }}
        />
      </div>
      <div className="flex gap-5 text-xs">
        <div className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: "var(--muted)", opacity: 0.5 }}
          />
          <span style={{ color: "var(--muted)" }}>
            Troubleshoot.sh ({tsCount})
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: "var(--success)" }}
          />
          <span style={{ color: "var(--success)" }}>
            TroubleShootAI ({aiCount})
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── Left column item (Troubleshoot.sh result) ────── */

function TroubleshootItem({
  item,
  index,
}: {
  item: TroubleshootFoundItem;
  index: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.1 + index * 0.04 }}
      className="flex items-start gap-3 rounded-lg px-3 py-2.5"
      style={{
        background: "rgba(0, 0, 0, 0.15)",
        border: "1px solid var(--border-subtle)",
      }}
    >
      <SeverityIcon severity={item.severity} />
      <div className="flex-1 min-w-0">
        <p
          className="text-xs font-medium truncate"
          style={{ color: "var(--foreground)" }}
        >
          {item.title || item.name}
        </p>
        <p
          className="text-[11px] mt-0.5 line-clamp-2"
          style={{ color: "var(--muted)" }}
        >
          {item.detail}
        </p>
      </div>
    </motion.div>
  );
}

/* ── Right column item (TroubleShootAI result) ────── */

function TroubleShootAIItem({
  item,
  isMissed,
  index,
}: {
  item: TroubleshootAIFoundItem;
  isMissed: boolean;
  index: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.1 + index * 0.04 }}
      className="flex items-start gap-3 rounded-lg px-3 py-2.5"
      style={{
        background: isMissed
          ? "rgba(16, 185, 129, 0.04)"
          : "rgba(0, 0, 0, 0.15)",
        border: isMissed
          ? "1px solid rgba(16, 185, 129, 0.2)"
          : "1px solid var(--border-subtle)",
      }}
    >
      <SeverityIcon severity={item.severity} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded"
            style={{
              background: "rgba(107, 114, 128, 0.15)",
              color: "var(--muted)",
            }}
          >
            {issueTypeLabel(item.type)}
          </span>
          {isMissed && (
            <span
              className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
              style={{
                background: "rgba(16, 185, 129, 0.15)",
                color: "var(--success)",
              }}
            >
              NEW
            </span>
          )}
        </div>
        <p
          className="text-xs font-medium mt-1 truncate"
          style={{ color: "var(--foreground-bright)" }}
        >
          {item.resource}
        </p>
        <p
          className="text-[11px] mt-0.5 line-clamp-2"
          style={{ color: "var(--muted)" }}
        >
          {item.description}
        </p>
      </div>
    </motion.div>
  );
}

/* ── Main Component ───────────────────────────────── */

export function CoverageComparisonPanel({
  bundleId,
}: {
  bundleId: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["coverage-comparison", bundleId],
    queryFn: () => getCoverageComparison(bundleId),
    enabled: !!bundleId,
    retry: 1,
    staleTime: 30_000,
  });

  // Don't render if loading, no data, or no troubleshoot.sh results
  if (isLoading || !data) return null;
  if (data.troubleshoot_count === 0 && data.troubleshootai_count === 0)
    return null;

  const missedSet = new Set(
    data.missed_by_troubleshoot.map(
      (i) => `${i.type}:${i.resource}:${i.description}`,
    ),
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="glass-card p-6"
    >
      {/* Section header */}
      <div className="flex items-center gap-3 mb-5">
        <div
          className="flex h-9 w-9 items-center justify-center rounded-xl flex-shrink-0"
          style={{ background: "rgba(16, 185, 129, 0.1)" }}
        >
          <Eye size={18} style={{ color: "var(--success)" }} />
        </div>
        <div>
          <h2
            className="text-base font-semibold"
            style={{ color: "var(--foreground-bright)" }}
          >
            What Troubleshoot.sh Missed
          </h2>
          <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
            Coverage comparison between built-in analyzers and AI-powered
            scanning
          </p>
        </div>
      </div>

      {/* Headline stats */}
      <div className="grid grid-cols-3 gap-4 mb-5">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="rounded-xl p-4 text-center"
          style={{
            background: "rgba(107, 114, 128, 0.08)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <div className="flex items-center justify-center gap-2 mb-2">
            <Shield size={16} style={{ color: "var(--muted)" }} />
            <span
              className="text-[11px] font-medium uppercase tracking-wider"
              style={{ color: "var(--muted)" }}
            >
              Troubleshoot.sh
            </span>
          </div>
          <p
            className="text-3xl font-bold"
            style={{ color: "var(--foreground)" }}
          >
            {data.troubleshoot_count}
          </p>
          <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>
            issues found
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2 }}
          className="rounded-xl p-4 text-center"
          style={{
            background: "rgba(16, 185, 129, 0.06)",
            border: "1px solid rgba(16, 185, 129, 0.2)",
          }}
        >
          <div className="flex items-center justify-center gap-2 mb-2">
            <Sparkles size={16} style={{ color: "var(--success)" }} />
            <span
              className="text-[11px] font-medium uppercase tracking-wider"
              style={{ color: "var(--success)" }}
            >
              TroubleShootAI
            </span>
          </div>
          <p
            className="text-3xl font-bold"
            style={{ color: "var(--success)" }}
          >
            {data.troubleshootai_count}
          </p>
          <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>
            issues found
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.3 }}
          className="rounded-xl p-4 text-center"
          style={{
            background: "rgba(239, 68, 68, 0.06)",
            border: "1px solid rgba(239, 68, 68, 0.2)",
          }}
        >
          <div className="flex items-center justify-center gap-2 mb-2">
            <ShieldAlert size={16} style={{ color: "var(--critical)" }} />
            <span
              className="text-[11px] font-medium uppercase tracking-wider"
              style={{ color: "var(--critical)" }}
            >
              Gap
            </span>
          </div>
          <p
            className="text-3xl font-bold"
            style={{ color: "var(--critical)" }}
          >
            {data.gap_count}
          </p>
          <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>
            missed by TS.sh
          </p>
        </motion.div>
      </div>

      {/* Coverage bar */}
      <div className="mb-6">
        <CoverageBar
          tsCount={data.troubleshoot_count}
          aiCount={data.troubleshootai_count}
        />
      </div>

      {/* Side-by-side columns */}
      <div className="grid grid-cols-2 gap-5">
        {/* LEFT: Troubleshoot.sh results */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Shield size={14} style={{ color: "var(--muted)" }} />
            <h3
              className="text-xs font-medium uppercase tracking-wider"
              style={{ color: "var(--muted)" }}
            >
              Troubleshoot.sh Results
            </h3>
            <span className="badge badge-muted text-[10px]">
              {data.troubleshoot_count}
            </span>
          </div>
          <div className="flex flex-col gap-2 max-h-80 overflow-y-auto pr-1 scrollbar-hide">
            {data.troubleshoot_found.length === 0 ? (
              <div
                className="rounded-lg px-3 py-4 text-center"
                style={{
                  background: "rgba(0, 0, 0, 0.1)",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <p
                  className="text-xs"
                  style={{ color: "var(--muted)" }}
                >
                  No non-passing results from Troubleshoot.sh analyzers
                </p>
              </div>
            ) : (
              data.troubleshoot_found.map((item, i) => (
                <TroubleshootItem
                  key={`ts-${item.name}-${i}`}
                  item={item}
                  index={i}
                />
              ))
            )}
          </div>
        </div>

        {/* RIGHT: TroubleShootAI results */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={14} style={{ color: "var(--success)" }} />
            <h3
              className="text-xs font-medium uppercase tracking-wider"
              style={{ color: "var(--success)" }}
            >
              TroubleShootAI Results
            </h3>
            <span className="badge badge-success text-[10px]">
              {data.troubleshootai_count}
            </span>
          </div>
          <div className="flex flex-col gap-2 max-h-80 overflow-y-auto pr-1 scrollbar-hide">
            {data.troubleshootai_found.length === 0 ? (
              <div
                className="rounded-lg px-3 py-4 text-center"
                style={{
                  background: "rgba(0, 0, 0, 0.1)",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <p
                  className="text-xs"
                  style={{ color: "var(--muted)" }}
                >
                  No issues found by TroubleShootAI scanners
                </p>
              </div>
            ) : (
              data.troubleshootai_found.map((item, i) => (
                <TroubleShootAIItem
                  key={`ai-${item.type}-${item.resource}-${i}`}
                  item={item}
                  isMissed={missedSet.has(
                    `${item.type}:${item.resource}:${item.description}`,
                  )}
                  index={i}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
