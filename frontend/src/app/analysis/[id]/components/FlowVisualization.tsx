"use client";

import { useRef, useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  FileText,
  Server,
  Layers,
  Settings,
  Zap,
  Clock,
  XCircle,
  Brain,
  TrendingUp,
  GitBranch,
  Shield,
} from "lucide-react";
import type { AnalysisSummary } from "../types";

const SOURCE_NODES = [
  { label: "Pod Logs", icon: FileText, color: "#ec4899" },
  { label: "Node Resources", icon: Server, color: "#f472b6" },
  { label: "Deployments", icon: Layers, color: "#f9a8d4" },
  { label: "ConfigMaps", icon: Settings, color: "#e879a0" },
  { label: "Events & Alerts", icon: Zap, color: "#fb7185" },
  { label: "Previous Logs", icon: Clock, color: "#f0abfc" },
];

const DEST_NODES = [
  { label: "Critical Findings", icon: XCircle, color: "#8b5cf6" },
  { label: "AI Diagnoses", icon: Brain, color: "#7c3aed" },
  { label: "Timeline Events", icon: Clock, color: "#6d28d9" },
  { label: "Predictions", icon: TrendingUp, color: "#8b5cf6" },
  { label: "Drift Detection", icon: GitBranch, color: "#a78bfa" },
  { label: "Coverage Report", icon: Shield, color: "#7c3aed" },
];

export function FlowVisualization({
  isDone,
  isRunning,
  progress,
  summary,
  findingsCount,
  message,
}: {
  isDone: boolean;
  isRunning: boolean;
  progress: number;
  summary: AnalysisSummary | null;
  findingsCount: number;
  message: string;
}) {
  const sourceRefs = useRef<(HTMLDivElement | null)[]>([]);
  const destRefs = useRef<(HTMLDivElement | null)[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<HTMLDivElement>(null);
  const [paths, setPaths] = useState<{ src: string[]; dest: string[] }>({ src: [], dest: [] });

  useEffect(() => {
    const updatePaths = () => {
      if (!containerRef.current || !engineRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const engineRect = engineRef.current.getBoundingClientRect();

      const srcPaths: string[] = [];
      sourceRefs.current.forEach((el) => {
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const startX = rect.right - containerRect.left;
        const startY = rect.top + rect.height / 2 - containerRect.top;
        const endX = engineRect.left - containerRect.left;
        const endY = engineRect.top + engineRect.height / 2 - containerRect.top;
        const cpX = startX + (endX - startX) * 0.5;
        srcPaths.push(`M ${startX} ${startY} C ${cpX} ${startY}, ${cpX} ${endY}, ${endX} ${endY}`);
      });

      const dstPaths: string[] = [];
      destRefs.current.forEach((el) => {
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const startX = engineRect.right - containerRect.left;
        const startY = engineRect.top + engineRect.height / 2 - containerRect.top;
        const endX = rect.left - containerRect.left;
        const endY = rect.top + rect.height / 2 - containerRect.top;
        const cpX = startX + (endX - startX) * 0.5;
        dstPaths.push(`M ${startX} ${startY} C ${cpX} ${startY}, ${cpX} ${endY}, ${endX} ${endY}`);
      });

      setPaths({ src: srcPaths, dest: dstPaths });
    };

    updatePaths();
    window.addEventListener("resize", updatePaths);
    const timer = setTimeout(updatePaths, 100);
    return () => {
      window.removeEventListener("resize", updatePaths);
      clearTimeout(timer);
    };
  }, []);

  const statusColor = isDone ? "var(--success)" : isRunning ? "var(--accent-light)" : "var(--muted)";
  const statusText = isDone
    ? "Analysis Complete"
    : isRunning
      ? "Running Analysis Engine..."
      : "Awaiting Input";

  const totalFindings = summary ? summary.critical + summary.warning + summary.info : findingsCount;
  const stagesComplete = isDone ? 12 : Math.round((progress / 100) * 12);

  return (
    <div className="flow-container" ref={containerRef}>
      {/* SVG flow lines */}
      <svg className="flow-lines-svg">
        <defs>
          <linearGradient id="sourceGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#ec4899" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#ec4899" stopOpacity="0.1" />
          </linearGradient>
          <linearGradient id="destGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.1" />
            <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.6" />
          </linearGradient>
        </defs>
        {paths.src.map((d, i) => (
          <motion.path
            key={`src-${i}`}
            d={d}
            className={`flow-line source ${isRunning ? "flow-line-animated" : ""}`}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.8, delay: i * 0.08 }}
          />
        ))}
        {paths.dest.map((d, i) => (
          <motion.path
            key={`dest-${i}`}
            d={d}
            className={`flow-line dest ${isRunning ? "flow-line-animated" : ""}`}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.5 + i * 0.08 }}
          />
        ))}
      </svg>

      {/* Left: Source nodes */}
      <div className="flow-column left">
        {SOURCE_NODES.map((node, i) => (
          <motion.div
            key={node.label}
            ref={(el) => { sourceRefs.current[i] = el; }}
            className="flow-node"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.06, duration: 0.4 }}
          >
            <span className="text-sm">{node.label}</span>
            <div className="flow-icon" style={{ background: `${node.color}22`, color: node.color }}>
              <node.icon size={14} />
            </div>
          </motion.div>
        ))}
      </div>

      {/* Center: Engine panel */}
      <motion.div
        ref={engineRef}
        className="engine-panel"
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, delay: 0.2 }}
      >
        <div className="engine-status">
          <div
            className="dot"
            style={{ background: statusColor, color: statusColor }}
          />
          <span>{statusText}</span>
        </div>

        <div className="stat-big">
          <div className="value" style={{ color: isDone ? "var(--foreground-bright)" : "var(--accent-light)" }}>
            {totalFindings}
          </div>
          <div className="label">Total Findings</div>
        </div>

        <div className="stat-divider" />

        <div className="stat-row">
          <div className="stat-pair">
            <div className="value" style={{ color: isDone ? "var(--success)" : "var(--accent-light)" }}>
              {Math.round(progress)}%
            </div>
            <div className="label">Progress</div>
          </div>
          <div className="stat-pair">
            <div className="value">
              {stagesComplete}
            </div>
            <div className="label">Stages Done</div>
          </div>
        </div>

        <div className="stat-divider" />

        {summary ? (
          <div className="stat-row">
            <div className="stat-pair">
              <div className="value" style={{ color: "var(--critical)" }}>{summary.critical}</div>
              <div className="label">Critical</div>
            </div>
            <div className="stat-pair">
              <div className="value" style={{ color: "var(--warning)" }}>{summary.warning}</div>
              <div className="label">Warnings</div>
            </div>
          </div>
        ) : (
          <div className="stat-row">
            <div className="stat-pair">
              <div className="value">{SOURCE_NODES.length}</div>
              <div className="label">Sources</div>
            </div>
            <div className="stat-pair">
              <div className="value">{DEST_NODES.length}</div>
              <div className="label">Outputs</div>
            </div>
          </div>
        )}

        {summary && summary.logDiagnoses > 0 && (
          <>
            <div className="stat-divider" />
            <div className="stat-row">
              <div className="stat-pair">
                <div className="value" style={{ color: "#a78bfa" }}>{summary.logDiagnoses}</div>
                <div className="label">AI Diagnoses</div>
              </div>
              <div className="stat-pair">
                <div className="value">{summary.crashLoops}</div>
                <div className="label">Crash Loops</div>
              </div>
            </div>
          </>
        )}

        {message && (
          <p className="text-xs text-center" style={{ color: "var(--muted)", maxWidth: "240px" }}>
            {message}
          </p>
        )}
      </motion.div>

      {/* Right: Destination nodes */}
      <div className="flow-column right">
        {DEST_NODES.map((node, i) => (
          <motion.div
            key={node.label}
            ref={(el) => { destRefs.current[i] = el; }}
            className="flow-node"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 + i * 0.06, duration: 0.4 }}
          >
            <div className="flow-icon" style={{ background: `${node.color}22`, color: node.color }}>
              <node.icon size={14} />
            </div>
            <span className="text-sm">{node.label}</span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
