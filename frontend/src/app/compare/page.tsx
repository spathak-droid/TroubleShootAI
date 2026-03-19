"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  GitCompare,
  Loader2,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
  Minus,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { listBundles, compareBundles } from "@/lib/api";
import type { BundleInfo, DiffResult, DiffFinding } from "@/lib/types";

function severityIcon(status: DiffFinding["status"]) {
  switch (status) {
    case "new":
      return <AlertCircle size={14} style={{ color: "var(--critical)" }} />;
    case "resolved":
      return <CheckCircle2 size={14} style={{ color: "var(--success)" }} />;
    case "worsened":
      return <AlertTriangle size={14} style={{ color: "var(--warning)" }} />;
    case "unchanged":
      return <Minus size={14} style={{ color: "var(--muted)" }} />;
  }
}

function statusColor(status: DiffFinding["status"]): string {
  switch (status) {
    case "new":
      return "var(--critical)";
    case "resolved":
      return "var(--success)";
    case "worsened":
      return "var(--warning)";
    case "unchanged":
      return "var(--muted)";
  }
}

function statusBadgeClass(status: DiffFinding["status"]): string {
  switch (status) {
    case "new":
      return "badge badge-critical";
    case "resolved":
      return "badge badge-success";
    case "worsened":
      return "badge badge-warning";
    case "unchanged":
      return "badge badge-muted";
  }
}

function FindingSection({
  title,
  findings,
  status,
  defaultOpen = true,
}: {
  title: string;
  findings: DiffFinding[];
  status: DiffFinding["status"];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  if (findings.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="w-full"
    >
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center justify-between rounded-xl px-4 py-3 transition-colors"
        style={{
          background: "rgba(0, 0, 0, 0.2)",
          border: `1px solid ${statusColor(status)}33`,
        }}
      >
        <div className="flex items-center gap-3">
          {severityIcon(status)}
          <span
            className="text-sm font-semibold"
            style={{ color: statusColor(status) }}
          >
            {title}
          </span>
          <span className={statusBadgeClass(status)}>
            {findings.length}
          </span>
        </div>
        {open ? (
          <ChevronUp size={16} style={{ color: "var(--muted)" }} />
        ) : (
          <ChevronDown size={16} style={{ color: "var(--muted)" }} />
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="flex flex-col gap-2 pt-2">
              {findings.map((f, i) => (
                <motion.div
                  key={`${f.resource}-${i}`}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="glass-card-sm p-4"
                >
                  <div className="flex items-start gap-3">
                    <div
                      className="mt-0.5 h-2 w-2 shrink-0 rounded-full"
                      style={{ background: statusColor(status) }}
                    />
                    <div className="min-w-0 flex-1">
                      <p
                        className="text-sm font-medium"
                        style={{ color: "var(--foreground-bright)" }}
                      >
                        {f.description}
                      </p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-2">
                        <span className="badge badge-muted">{f.category}</span>
                        <span
                          className="text-xs font-mono"
                          style={{ color: "var(--muted)" }}
                        >
                          {f.resource}
                        </span>
                      </div>
                      {(f.before_detail || f.after_detail) && (
                        <div className="mt-2 flex flex-col gap-1">
                          {f.before_detail && (
                            <div className="flex items-start gap-2">
                              <span
                                className="shrink-0 text-[10px] font-bold uppercase tracking-wider"
                                style={{ color: "var(--muted)", marginTop: 2 }}
                              >
                                Before
                              </span>
                              <span
                                className="text-xs"
                                style={{ color: "var(--muted)" }}
                              >
                                {f.before_detail}
                              </span>
                            </div>
                          )}
                          {f.after_detail && (
                            <div className="flex items-start gap-2">
                              <span
                                className="shrink-0 text-[10px] font-bold uppercase tracking-wider"
                                style={{ color: "var(--muted)", marginTop: 2 }}
                              >
                                After
                              </span>
                              <span
                                className="text-xs"
                                style={{ color: "var(--muted)" }}
                              >
                                {f.after_detail}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function ComparePage() {
  const router = useRouter();
  const [bundles, setBundles] = useState<BundleInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [beforeId, setBeforeId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [comparing, setComparing] = useState(false);
  const [result, setResult] = useState<DiffResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await listBundles();
        setBundles(data);
      } catch {
        setError("Failed to load bundles");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleCompare = async () => {
    if (!beforeId || !afterId) return;
    if (beforeId === afterId) {
      setError("Please select two different bundles");
      return;
    }
    setError(null);
    setResult(null);
    setComparing(true);
    try {
      const data = await compareBundles(beforeId, afterId);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed");
    } finally {
      setComparing(false);
    }
  };

  const totalFindings = result
    ? result.new_findings.length +
      result.resolved_findings.length +
      result.worsened_findings.length +
      result.unchanged_findings.length
    : 0;

  return (
    <div className="relative z-10 flex min-h-screen flex-col items-center p-8">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="flex w-full max-w-3xl flex-col items-center gap-8 pt-8"
      >
        {/* Back button */}
        <div className="flex w-full items-center">
          <button
            onClick={() => router.push("/")}
            className="flex cursor-pointer items-center gap-2 text-sm transition-colors"
            style={{ color: "var(--muted)" }}
          >
            <ArrowLeft size={16} />
            Back to Home
          </button>
        </div>

        {/* Header */}
        <div className="flex flex-col items-center gap-3 text-center">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{
              delay: 0.1,
              duration: 0.5,
              ease: [0.22, 1, 0.36, 1],
            }}
            className="flex h-14 w-14 items-center justify-center rounded-2xl"
            style={{ background: "var(--accent-glow)" }}
          >
            <GitCompare size={28} style={{ color: "var(--accent-light)" }} />
          </motion.div>
          <div>
            <h1
              className="text-2xl font-bold tracking-tight"
              style={{ color: "var(--foreground-bright)" }}
            >
              Compare Bundles
            </h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              Select two analyzed bundles to diff their findings
            </p>
          </div>
        </div>

        {/* Bundle selectors */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.5,
            delay: 0.2,
            ease: [0.22, 1, 0.36, 1],
          }}
          className="flex w-full flex-col gap-4"
        >
          <div className="flex w-full items-end gap-4">
            {/* Before selector */}
            <div className="flex flex-1 flex-col gap-2">
              <label
                className="text-xs font-medium uppercase tracking-wider"
                style={{ color: "var(--muted)" }}
              >
                Before Bundle
              </label>
              <select
                value={beforeId}
                onChange={(e) => setBeforeId(e.target.value)}
                disabled={loading}
                className="input-modern w-full cursor-pointer p-3"
                style={{
                  appearance: "none",
                  WebkitAppearance: "none",
                  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`,
                  backgroundRepeat: "no-repeat",
                  backgroundPosition: "right 12px center",
                  paddingRight: "36px",
                }}
              >
                <option value="">Select a bundle...</option>
                {bundles.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.filename} ({b.id.slice(0, 8)}) — {b.status}
                  </option>
                ))}
              </select>
            </div>

            {/* Arrow */}
            <div
              className="flex h-[46px] items-center justify-center px-2"
              style={{ color: "var(--muted)" }}
            >
              <ArrowRight size={20} />
            </div>

            {/* After selector */}
            <div className="flex flex-1 flex-col gap-2">
              <label
                className="text-xs font-medium uppercase tracking-wider"
                style={{ color: "var(--muted)" }}
              >
                After Bundle
              </label>
              <select
                value={afterId}
                onChange={(e) => setAfterId(e.target.value)}
                disabled={loading}
                className="input-modern w-full cursor-pointer p-3"
                style={{
                  appearance: "none",
                  WebkitAppearance: "none",
                  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`,
                  backgroundRepeat: "no-repeat",
                  backgroundPosition: "right 12px center",
                  paddingRight: "36px",
                }}
              >
                <option value="">Select a bundle...</option>
                {bundles.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.filename} ({b.id.slice(0, 8)}) — {b.status}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Compare button */}
          <div className="flex justify-center pt-2">
            <button
              onClick={handleCompare}
              disabled={!beforeId || !afterId || comparing}
              className="btn-primary flex items-center gap-2"
            >
              {comparing ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Comparing...
                </>
              ) : (
                <>
                  <GitCompare size={16} />
                  Compare
                </>
              )}
            </button>
          </div>
        </motion.div>

        {/* Error */}
        {error && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-sm"
            style={{ color: "var(--critical)" }}
          >
            {error}
          </motion.p>
        )}

        {/* Results */}
        <AnimatePresence mode="wait">
          {result && (
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              className="flex w-full flex-col gap-6"
            >
              {/* Summary card */}
              <div className="glass-card p-6">
                <p
                  className="mb-4 text-sm font-medium"
                  style={{ color: "var(--foreground-bright)" }}
                >
                  {result.summary}
                </p>

                {/* Stat grid */}
                <div className="grid grid-cols-4 gap-4">
                  <div
                    className="flex flex-col items-center gap-1 rounded-xl p-3"
                    style={{ background: "var(--critical-glow)" }}
                  >
                    <span
                      className="text-2xl font-bold"
                      style={{ color: "var(--critical)" }}
                    >
                      {result.new_findings.length}
                    </span>
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: "var(--critical)" }}
                    >
                      New
                    </span>
                  </div>
                  <div
                    className="flex flex-col items-center gap-1 rounded-xl p-3"
                    style={{ background: "var(--success-glow)" }}
                  >
                    <span
                      className="text-2xl font-bold"
                      style={{ color: "var(--success)" }}
                    >
                      {result.resolved_findings.length}
                    </span>
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: "var(--success)" }}
                    >
                      Resolved
                    </span>
                  </div>
                  <div
                    className="flex flex-col items-center gap-1 rounded-xl p-3"
                    style={{ background: "var(--warning-glow)" }}
                  >
                    <span
                      className="text-2xl font-bold"
                      style={{ color: "var(--warning)" }}
                    >
                      {result.worsened_findings.length}
                    </span>
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: "var(--warning)" }}
                    >
                      Worsened
                    </span>
                  </div>
                  <div
                    className="flex flex-col items-center gap-1 rounded-xl p-3"
                    style={{ background: "rgba(107, 114, 128, 0.1)" }}
                  >
                    <span
                      className="text-2xl font-bold"
                      style={{ color: "var(--muted)" }}
                    >
                      {result.unchanged_findings.length}
                    </span>
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: "var(--muted)" }}
                    >
                      Unchanged
                    </span>
                  </div>
                </div>

                {/* Resource delta */}
                {Object.keys(result.resource_delta).length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-3">
                    {Object.entries(result.resource_delta).map(
                      ([key, value]) => (
                        <div
                          key={key}
                          className="flex items-center gap-2 rounded-lg px-3 py-1.5"
                          style={{
                            background: "rgba(0, 0, 0, 0.2)",
                            border: "1px solid var(--border-subtle)",
                          }}
                        >
                          <span
                            className="text-[10px] uppercase tracking-wider"
                            style={{ color: "var(--muted)" }}
                          >
                            {key.replace(/_/g, " ")}
                          </span>
                          <span
                            className="text-xs font-bold font-mono"
                            style={{ color: "var(--foreground-bright)" }}
                          >
                            {value}
                          </span>
                        </div>
                      ),
                    )}
                  </div>
                )}
              </div>

              {/* Finding sections */}
              {totalFindings === 0 ? (
                <div
                  className="rounded-xl border px-6 py-8 text-center"
                  style={{
                    borderColor: "var(--border)",
                    background: "var(--card)",
                  }}
                >
                  <CheckCircle2
                    size={24}
                    className="mx-auto mb-2"
                    style={{ color: "var(--success)" }}
                  />
                  <p className="text-sm" style={{ color: "var(--muted)" }}>
                    No differences found between the two bundles.
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-4">
                  <FindingSection
                    title="New Findings"
                    findings={result.new_findings}
                    status="new"
                    defaultOpen={true}
                  />
                  <FindingSection
                    title="Worsened Findings"
                    findings={result.worsened_findings}
                    status="worsened"
                    defaultOpen={true}
                  />
                  <FindingSection
                    title="Resolved Findings"
                    findings={result.resolved_findings}
                    status="resolved"
                    defaultOpen={true}
                  />
                  <FindingSection
                    title="Unchanged Findings"
                    findings={result.unchanged_findings}
                    status="unchanged"
                    defaultOpen={false}
                  />
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
