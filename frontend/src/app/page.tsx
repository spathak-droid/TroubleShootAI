"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Upload, CheckCircle, Loader2, FileArchive, ArrowRight, Sparkles } from "lucide-react";
import { uploadBundle } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadedBundle, setUploadedBundle] = useState<{ id: string; filename: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [context, setContext] = useState("");

  const handleFile = useCallback(
    async (file: File) => {
      if (
        !file.name.endsWith(".tar.gz") &&
        !file.name.endsWith(".tgz")
      ) {
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
    },
    [],
  );

  const handleStartAnalysis = useCallback(() => {
    if (!uploadedBundle) return;
    const qs = new URLSearchParams();
    qs.set("autostart", "1");
    if (context) qs.set("context", context);
    router.push(`/analysis/${uploadedBundle.id}?${qs.toString()}`);
  }, [uploadedBundle, context, router]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const onDragLeave = useCallback(() => setDragging(false), []);

  return (
    <div className="relative z-10 flex min-h-screen flex-col items-center justify-center p-8">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="flex w-full max-w-lg flex-col items-center gap-10"
      >
        {/* Header */}
        <div className="flex flex-col items-center gap-4 text-center">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.1, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="flex h-16 w-16 items-center justify-center rounded-2xl"
            style={{ background: "var(--accent-gradient)", boxShadow: "0 0 40px rgba(99, 102, 241, 0.3)" }}
          >
            <FileArchive size={32} color="white" />
          </motion.div>
          <div>
            <h1
              className="text-3xl font-bold tracking-tight"
              style={{ color: "var(--foreground-bright)" }}
            >
              Bundle Analyzer
            </h1>
            <p
              className="mt-2 text-sm"
              style={{ color: "var(--muted)" }}
            >
              AI-powered Kubernetes support bundle forensics
            </p>
          </div>
        </div>

        {/* Upload zone */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          className="w-full"
        >
          <div
            onDrop={uploadedBundle ? undefined : onDrop}
            onDragOver={uploadedBundle ? undefined : onDragOver}
            onDragLeave={uploadedBundle ? undefined : onDragLeave}
            onClick={uploadedBundle ? undefined : () => fileInputRef.current?.click()}
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
                <Upload size={24} style={{ color: "var(--accent-light)" }} />
              </div>
            )}

            <div>
              {uploadedBundle ? (
                <>
                  <p className="text-sm font-medium" style={{ color: "var(--success)" }}>
                    {uploadedBundle.filename}
                  </p>
                  <p className="mt-1 text-xs font-mono" style={{ color: "var(--muted)" }}>
                    ID: {uploadedBundle.id.slice(0, 12)}
                  </p>
                </>
              ) : uploading ? (
                <p className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
                  Uploading bundle...
                </p>
              ) : (
                <>
                  <p className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
                    Drop a support bundle here, or click to browse
                  </p>
                  <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
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
          transition={{ duration: 0.5, delay: 0.35, ease: [0.22, 1, 0.36, 1] }}
          className="flex w-full flex-col gap-2"
        >
          <label
            className="text-xs font-medium uppercase tracking-wider"
            style={{ color: "var(--muted)" }}
          >
            ISV Context
            <span className="ml-1 normal-case tracking-normal" style={{ opacity: 0.6 }}>(optional)</span>
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

        {/* Status text */}
        {uploadedBundle && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-xs"
            style={{ color: "var(--muted)" }}
          >
            Ready to analyze
          </motion.p>
        )}
      </motion.div>
    </div>
  );
}
