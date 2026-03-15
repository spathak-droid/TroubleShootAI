"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  CheckCircle,
  Loader2,
  ArrowRight,
  Sparkles,
  Clock,
  AlertTriangle,
  AlertCircle,
  FileText,
  Trash2,
  ChevronRight,
  LogOut,
} from "lucide-react";
import { uploadBundle, listBundles, deleteBundle } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { BundleInfo } from "@/lib/types";

function timeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return date.toLocaleDateString();
}

function statusColor(status: string): string {
  switch (status) {
    case "complete":
      return "var(--success)";
    case "error":
      return "var(--critical)";
    case "analyzing":
    case "extracting":
    case "triaging":
      return "var(--accent-light)";
    default:
      return "var(--muted)";
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "complete":
      return "Complete";
    case "error":
      return "Failed";
    case "analyzing":
      return "Analyzing...";
    case "extracting":
      return "Extracting...";
    case "triaging":
      return "Triaging...";
    case "uploaded":
      return "Uploaded";
    default:
      return status;
  }
}

export default function HomePage() {
  const router = useRouter();
  const { user, signOut } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadedBundle, setUploadedBundle] = useState<{
    id: string;
    filename: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [context, setContext] = useState("");
  const [bundles, setBundles] = useState<BundleInfo[]>([]);
  const [loadingBundles, setLoadingBundles] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Load past analyses on mount
  useEffect(() => {
    loadBundles();
  }, []);

  const loadBundles = async () => {
    try {
      const data = await listBundles();
      setBundles(data);
    } catch {
      // silently fail — homepage still works for uploads
    } finally {
      setLoadingBundles(false);
    }
  };

  const handleFile = useCallback(async (file: File) => {
    if (!file.name.endsWith(".tar.gz") && !file.name.endsWith(".tgz")) {
      setError("Please upload a .tar.gz or .tgz file");
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const bundle = await uploadBundle(file);
      setUploadedBundle({ id: bundle.id, filename: bundle.filename });
      setUploading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setUploading(false);
    }
  }, []);

  const handleStartAnalysis = useCallback(() => {
    if (!uploadedBundle) return;
    const qs = new URLSearchParams();
    qs.set("autostart", "1");
    if (context) qs.set("context", context);
    router.push(`/analysis/${uploadedBundle.id}?${qs.toString()}`);
  }, [uploadedBundle, context, router]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (deletingId) return;
    setDeletingId(id);
    try {
      await deleteBundle(id);
      setBundles((prev) => prev.filter((b) => b.id !== id));
    } catch {
      // ignore
    } finally {
      setDeletingId(null);
    }
  };

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const onDragLeave = useCallback(() => setDragging(false), []);

  // Only show bundles that have started or completed analysis (not just uploaded)
  const visibleBundles = bundles.filter((b) => b.status !== "uploaded");

  return (
    <div className="relative z-10 flex min-h-screen flex-col items-center p-8">
      {/* Top bar */}
      {user && (
        <div
          className="fixed top-0 right-0 left-0 z-50 flex items-center justify-end px-6 py-3"
          style={{
            background: "linear-gradient(to bottom, var(--background), transparent)",
            backdropFilter: "blur(12px)",
          }}
        >
          <div
            className="flex items-center gap-3 rounded-full px-4 py-1.5"
            style={{
              background: "rgba(255, 255, 255, 0.05)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
            }}
          >
            <div
              className="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold uppercase"
              style={{
                background: "var(--accent-gradient)",
                color: "white",
              }}
            >
              {user.email?.charAt(0) || "U"}
            </div>
            <span className="text-xs font-mono" style={{ color: "var(--foreground)" }}>
              {user.email}
            </span>
            <div className="h-3 w-px" style={{ background: "rgba(255,255,255,0.15)" }} />
            <button
              onClick={() => signOut()}
              className="flex cursor-pointer items-center gap-1.5 text-xs transition-colors hover:text-white"
              style={{ color: "var(--muted)" }}
              title="Sign out"
            >
              <LogOut size={12} />
              Sign out
            </button>
          </div>
        </div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="flex w-full max-w-2xl flex-col items-center gap-10 pt-12"
      >
        {/* Header */}
        <div className="flex flex-col items-center gap-4 text-center">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{
              delay: 0.1,
              duration: 0.5,
              ease: [0.22, 1, 0.36, 1],
            }}
            className="flex h-16 w-16 items-center justify-center"
          >
            <Image
              src="/logo.svg"
              alt="Bundle threat analyzer logo"
              width={64}
              height={64}
              priority
              className="h-16 w-16 object-contain"
            />
          </motion.div>
          <div>
            <h1
              className="text-3xl font-bold tracking-tight"
              style={{ color: "var(--foreground-bright)" }}
            >
              Bundle Analyzer
            </h1>
            <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
              AI-powered support bundle forensics
            </p>
            <p
              className="mt-1 text-sm font-medium"
              style={{ color: "var(--accent-light)" }}
            >
              from log chaos to log structure
            </p>
          </div>
        </div>

        {/* Upload zone */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.5,
            delay: 0.2,
            ease: [0.22, 1, 0.36, 1],
          }}
          className="w-full"
        >
          <div
            onDrop={uploadedBundle ? undefined : onDrop}
            onDragOver={uploadedBundle ? undefined : onDragOver}
            onDragLeave={uploadedBundle ? undefined : onDragLeave}
            onClick={
              uploadedBundle
                ? undefined
                : () => fileInputRef.current?.click()
            }
            className={`upload-zone flex flex-col items-center justify-center gap-4 p-10 text-center ${
              uploadedBundle ? "uploaded" : ""
            } ${dragging ? "dragging" : ""}`}
          >
            {uploadedBundle ? (
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 300, damping: 20 }}
              >
                <CheckCircle size={36} style={{ color: "var(--success)" }} />
              </motion.div>
            ) : uploading ? (
              <Loader2
                size={36}
                className="animate-spin"
                style={{ color: "var(--accent-light)" }}
              />
            ) : (
              <div
                className="flex h-12 w-12 items-center justify-center rounded-xl"
                style={{ background: "rgba(99, 102, 241, 0.1)" }}
              >
                <Upload
                  size={24}
                  style={{ color: "var(--accent-light)" }}
                />
              </div>
            )}

            <div>
              {uploadedBundle ? (
                <>
                  <p
                    className="text-sm font-medium"
                    style={{ color: "var(--success)" }}
                  >
                    {uploadedBundle.filename}
                  </p>
                  <p
                    className="mt-1 text-xs font-mono"
                    style={{ color: "var(--muted)" }}
                  >
                    ID: {uploadedBundle.id.slice(0, 12)}
                  </p>
                </>
              ) : uploading ? (
                <p
                  className="text-sm font-medium"
                  style={{ color: "var(--foreground)" }}
                >
                  Uploading bundle...
                </p>
              ) : (
                <>
                  <p
                    className="text-sm font-medium"
                    style={{ color: "var(--foreground)" }}
                  >
                    Drop a support bundle here, or click to browse
                  </p>
                  <p
                    className="mt-1 text-xs"
                    style={{ color: "var(--muted)" }}
                  >
                    Accepts .tar.gz and .tgz files
                  </p>
                </>
              )}
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept=".tar.gz,.tgz,.gz"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
          </div>
        </motion.div>

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

        {/* ISV context */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.5,
            delay: 0.35,
            ease: [0.22, 1, 0.36, 1],
          }}
          className="flex w-full flex-col gap-2"
        >
          <label
            className="text-xs font-medium uppercase tracking-wider"
            style={{ color: "var(--muted)" }}
          >
            ISV Context
            <span
              className="ml-1 normal-case tracking-normal"
              style={{ opacity: 0.6 }}
            >
              (optional)
            </span>
          </label>
          <textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
            placeholder="Describe the issue or provide context about the environment..."
            rows={3}
            className="input-modern w-full resize-none p-3"
          />
        </motion.div>

        {/* Start Analysis button */}
        {uploadedBundle && (
          <motion.div
            initial={{ opacity: 0, y: 15, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <button
              onClick={handleStartAnalysis}
              className="btn-primary flex items-center gap-2"
            >
              <Sparkles size={16} />
              Start Analysis
              <ArrowRight size={16} />
            </button>
          </motion.div>
        )}

        {/* Past Analyses */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.5,
            delay: 0.45,
            ease: [0.22, 1, 0.36, 1],
          }}
          className="w-full"
        >
          <div className="mb-4 flex items-center gap-2">
            <Clock size={14} style={{ color: "var(--muted)" }} />
            <h2
              className="text-xs font-medium uppercase tracking-wider"
              style={{ color: "var(--muted)" }}
            >
              Past Analyses
            </h2>
          </div>

          {loadingBundles ? (
            <div className="flex items-center justify-center py-8">
              <Loader2
                size={20}
                className="animate-spin"
                style={{ color: "var(--muted)" }}
              />
            </div>
          ) : visibleBundles.length === 0 ? (
            <div
              className="rounded-xl border px-6 py-8 text-center"
              style={{
                borderColor: "var(--border)",
                background: "var(--surface)",
              }}
            >
              <FileText
                size={24}
                className="mx-auto mb-2"
                style={{ color: "var(--muted)", opacity: 0.5 }}
              />
              <p className="text-sm" style={{ color: "var(--muted)" }}>
                No analyses yet. Upload a bundle to get started.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <AnimatePresence>
                {visibleBundles.map((bundle, i) => (
                  <motion.div
                    key={bundle.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ delay: i * 0.03 }}
                    onClick={() => {
                      if (bundle.status === "complete" || bundle.status === "analyzing" || bundle.status === "extracting" || bundle.status === "triaging") {
                        router.push(`/analysis/${bundle.id}`);
                      }
                    }}
                    className="group flex cursor-pointer items-center gap-4 rounded-xl border px-4 py-3 transition-all hover:border-[var(--accent-light)]/30"
                    style={{
                      borderColor: "var(--border)",
                      background: "var(--surface)",
                    }}
                  >
                    {/* Status indicator */}
                    <div
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ background: statusColor(bundle.status) }}
                    />

                    {/* Info */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p
                          className="truncate text-sm font-medium"
                          style={{ color: "var(--foreground)" }}
                        >
                          {bundle.filename}
                        </p>
                        <span
                          className="shrink-0 text-[10px] font-medium uppercase tracking-wider"
                          style={{ color: statusColor(bundle.status) }}
                        >
                          {statusLabel(bundle.status)}
                        </span>
                      </div>
                      <div className="mt-0.5 flex items-center gap-3">
                        <span
                          className="text-xs font-mono"
                          style={{ color: "var(--muted)" }}
                        >
                          {bundle.id.slice(0, 8)}
                        </span>
                        <span
                          className="text-xs"
                          style={{ color: "var(--muted)" }}
                        >
                          {timeAgo(bundle.uploaded_at)}
                        </span>
                        {bundle.status === "complete" && (bundle.finding_count ?? 0) > 0 && (
                          <span className="flex items-center gap-1 text-xs">
                            {(bundle.critical_count ?? 0) > 0 && (
                              <span
                                className="flex items-center gap-0.5"
                                style={{ color: "var(--critical)" }}
                              >
                                <AlertCircle size={10} />
                                {bundle.critical_count}
                              </span>
                            )}
                            {(bundle.warning_count ?? 0) > 0 && (
                              <span
                                className="flex items-center gap-0.5"
                                style={{ color: "var(--warning, #f59e0b)" }}
                              >
                                <AlertTriangle size={10} />
                                {bundle.warning_count}
                              </span>
                            )}
                            <span style={{ color: "var(--muted)" }}>
                              {bundle.finding_count} findings
                            </span>
                          </span>
                        )}
                      </div>
                      {bundle.summary && (
                        <p
                          className="mt-1 line-clamp-1 text-xs"
                          style={{ color: "var(--muted)" }}
                        >
                          {bundle.summary}
                        </p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        onClick={(e) => handleDelete(e, bundle.id)}
                        className="rounded-lg p-1.5 opacity-0 transition-opacity hover:bg-[var(--critical)]/10 group-hover:opacity-100"
                        style={{ color: "var(--muted)" }}
                        title="Delete"
                      >
                        {deletingId === bundle.id ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <Trash2 size={14} />
                        )}
                      </button>
                      <ChevronRight
                        size={16}
                        className="opacity-0 transition-opacity group-hover:opacity-100"
                        style={{ color: "var(--muted)" }}
                      />
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </motion.div>
      </motion.div>
    </div>
  );
}
