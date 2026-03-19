"use client";

import { use, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  Box,
  Server,
  Globe,
  Database,
  Settings,
  Shield,
  Network,
  Layers,
  ChevronRight,
  X,
  Loader2,
  ZapOff,
  GitBranch,
  ArrowDown,
  Target,
} from "lucide-react";
import { getDependencyGraph } from "@/lib/api";
import type { GraphNode, GraphEdge, CausalChain } from "@/lib/types";

// ─── Constants ───────────────────────────────────────────────────

const TYPE_ICONS: Record<string, typeof Box> = {
  pod: Box, deployment: Layers, replicaset: Layers, statefulset: Database,
  daemonset: Layers, service: Globe, configmap: Settings, secret: Shield,
  node: Server, ingress: Network, pvc: Database, job: GitBranch, cronjob: GitBranch,
};

const TYPE_COLORS: Record<string, string> = {
  pod: "#818cf8", deployment: "#a78bfa", replicaset: "#a78bfa",
  statefulset: "#c084fc", daemonset: "#c084fc", service: "#22d3ee",
  configmap: "#fbbf24", secret: "#f87171", node: "#6ee7b7",
  ingress: "#f472b6", pvc: "#fb923c", job: "#e879f9", cronjob: "#e879f9",
};

// Column ordering for cascade flow layout
const TYPE_COLUMNS: string[][] = [
  ["node"],
  ["configmap", "secret", "pvc"],
  ["deployment", "replicaset", "statefulset", "daemonset", "job", "cronjob"],
  ["pod"],
  ["service", "ingress"],
];

// ─── Layout ─────────────────────────────────────────────────────

interface PositionedNode extends GraphNode {
  x: number;
  y: number;
  col: number;
}

function layoutNodes(nodes: GraphNode[]): PositionedNode[] {
  // Deduplicate by canonical key
  const seen = new Map<string, GraphNode>();
  for (const node of nodes) {
    const key = `${node.type}:${node.namespace}:${node.name}`;
    const existing = seen.get(key);
    if (!existing) {
      seen.set(key, node);
    } else {
      const rank: Record<string, number> = { critical: 3, warning: 2, info: 1 };
      if ((rank[node.severity ?? ""] ?? 0) > (rank[existing.severity ?? ""] ?? 0)) {
        seen.set(key, node);
      }
    }
  }
  const deduplicated = Array.from(seen.values());

  const colMap = new Map<string, number>();
  TYPE_COLUMNS.forEach((types, colIdx) => types.forEach((t) => colMap.set(t, colIdx)));

  const columns = new Map<number, GraphNode[]>();
  deduplicated.forEach((node) => {
    const col = colMap.get(node.type) ?? 2;
    if (!columns.has(col)) columns.set(col, []);
    columns.get(col)!.push(node);
  });

  // Only render used columns, packed tightly
  const usedCols = Array.from(columns.keys()).sort((a, b) => a - b);
  const colPosition = new Map<number, number>();
  usedCols.forEach((col, i) => colPosition.set(col, i));

  const COL_WIDTH = 260;
  const ROW_HEIGHT = 85;
  const PAD_X = 30;
  const PAD_Y = 50;

  const positioned: PositionedNode[] = [];
  const severityOrder: Record<string, number> = { critical: 0, warning: 1, info: 2 };

  usedCols.forEach((colIdx) => {
    const colNodes = columns.get(colIdx) ?? [];
    const renderCol = colPosition.get(colIdx) ?? 0;
    colNodes.sort((a, b) => (severityOrder[a.severity ?? ""] ?? 3) - (severityOrder[b.severity ?? ""] ?? 3));
    colNodes.forEach((node, rowIdx) => {
      positioned.push({
        ...node,
        x: PAD_X + renderCol * COL_WIDTH,
        y: PAD_Y + rowIdx * ROW_HEIGHT,
        col: renderCol,
      });
    });
  });

  return positioned;
}

function getColumnLabel(colIdx: number): string {
  return ["Infrastructure", "Configuration", "Workloads", "Pods", "Networking"][colIdx] ?? "";
}

function shortName(name: string): string {
  const segments = name.split("-");
  if (segments.length >= 3 && segments[segments.length - 1].length >= 5 && segments[segments.length - 2].length >= 8) {
    return segments.slice(0, -2).join("-");
  }
  return name;
}

// ─── SVG Edges ──────────────────────────────────────────────────

function EdgeLines({
  edges,
  nodeMap,
  highlightedNodes,
}: {
  edges: GraphEdge[];
  nodeMap: Map<string, PositionedNode>;
  highlightedNodes: Set<string> | null;
}) {
  const NODE_W = 210;
  const NODE_H = 70;

  // Deduplicate edges by canonical node key
  const deduped = useMemo(() => {
    const seen = new Set<string>();
    return edges.filter((e) => {
      // Find actual nodes for source/target (might need canonical lookup)
      if (!nodeMap.has(e.source) || !nodeMap.has(e.target)) return false;
      if (e.source === e.target) return false;
      const key = `${e.source}→${e.target}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [edges, nodeMap]);

  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 0 }}>
      <defs>
        <marker id="arrowRed" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill="var(--critical)" fillOpacity="0.6" />
        </marker>
        <marker id="arrowOrange" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill="var(--warning)" fillOpacity="0.5" />
        </marker>
        <marker id="arrowGlow" markerWidth="10" markerHeight="8" refX="10" refY="4" orient="auto">
          <path d="M0,0 L10,4 L0,8 Z" fill="var(--critical)" />
        </marker>
      </defs>
      {deduped.map((edge, idx) => {
        const src = nodeMap.get(edge.source);
        const tgt = nodeMap.get(edge.target);
        if (!src || !tgt) return null;

        const isHighlighted = highlightedNodes !== null && highlightedNodes.has(edge.source) && highlightedNodes.has(edge.target);
        const isDimmed = highlightedNodes !== null && !isHighlighted;

        // Connection points: right side of source → left side of target
        let x1: number, y1: number, x2: number, y2: number;
        if (src.col < tgt.col) {
          x1 = src.x + NODE_W; y1 = src.y + NODE_H / 2;
          x2 = tgt.x; y2 = tgt.y + NODE_H / 2;
        } else if (src.col > tgt.col) {
          x1 = src.x; y1 = src.y + NODE_H / 2;
          x2 = tgt.x + NODE_W; y2 = tgt.y + NODE_H / 2;
        } else {
          // Same column
          x1 = src.x + NODE_W / 2; y1 = src.y + (src.y < tgt.y ? NODE_H : 0);
          x2 = tgt.x + NODE_W / 2; y2 = tgt.y + (src.y < tgt.y ? 0 : NODE_H);
        }

        const dx = x2 - x1;
        const dy = y2 - y1;
        const cpOff = Math.min(Math.abs(dx) * 0.35, 70);
        const cpx1 = x1 + (dx > 0 ? cpOff : -cpOff);
        const cpx2 = x2 - (dx > 0 ? cpOff : -cpOff);
        const cpy1 = y1 + dy * 0.1;
        const cpy2 = y2 - dy * 0.1;

        const isCascade = edge.relationship === "cascades_to";
        const marker = isHighlighted ? "url(#arrowGlow)" : isCascade ? "url(#arrowRed)" : "url(#arrowOrange)";
        const color = isHighlighted ? "var(--critical)" : isCascade ? "rgba(239,68,68,0.35)" : "rgba(245,158,11,0.25)";

        const pathD = `M${x1},${y1} C${cpx1},${cpy1} ${cpx2},${cpy2} ${x2},${y2}`;

        // Midpoint for label
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2 - 8;

        return (
          <g key={`e-${idx}`} opacity={isDimmed ? 0.5 : 1}>
            {isHighlighted && (
              <path d={pathD} fill="none" stroke="var(--critical)" strokeWidth={6} opacity={0.1} filter="blur(4px)" />
            )}
            <path
              d={pathD}
              fill="none"
              stroke={color}
              strokeWidth={isHighlighted ? 2.5 : 1.5}
              markerEnd={marker}
              strokeDasharray={isCascade || isHighlighted ? "none" : "5 4"}
            />
            {/* Edge label */}
            {!isDimmed && (
              <text
                x={mx}
                y={my}
                textAnchor="middle"
                fill="var(--muted)"
                fontSize={9}
                opacity={0.7}
              >
                {edge.relationship.replace(/_/g, " ")}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ─── Node Card ──────────────────────────────────────────────────

function NodeCard({
  node, isSelected, dimmed, onClick, delay,
}: {
  node: PositionedNode; isSelected: boolean; dimmed: boolean; onClick: () => void; delay: number;
}) {
  const Icon = TYPE_ICONS[node.type] || Box;
  const typeColor = TYPE_COLORS[node.type] || "var(--muted)";
  const statusColor = node.severity === "critical" ? "var(--critical)" : node.severity === "warning" ? "var(--warning)" : node.status === "healthy" ? "var(--success)" : "var(--muted)";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.92 }}
      animate={{ opacity: dimmed ? 0.55 : 1, scale: isSelected ? 1.04 : dimmed ? 0.97 : 1 }}
      transition={{ delay: delay * 0.04, duration: 0.3 }}
      onClick={onClick}
      className="absolute cursor-pointer"
      style={{ left: node.x, top: node.y, width: 210, zIndex: isSelected ? 10 : 1 }}
    >
      <div
        className="rounded-xl p-3 transition-all relative"
        style={{
          background: isSelected ? "rgba(99,102,241,0.1)" : "var(--card)",
          border: `1px solid ${isSelected ? "rgba(99,102,241,0.4)" : node.severity === "critical" ? "rgba(239,68,68,0.25)" : "var(--border-subtle)"}`,
          boxShadow: isSelected ? "0 0 20px rgba(99,102,241,0.15)" : node.severity === "critical" ? "0 0 12px rgba(239,68,68,0.08)" : "none",
        }}
      >
        {/* Status dot */}
        <div className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full" style={{ background: statusColor, boxShadow: `0 0 6px ${statusColor}` }} />

        <div className="flex items-center gap-2">
          <div
            className="flex items-center justify-center w-7 h-7 rounded-lg flex-shrink-0"
            style={{ background: `${typeColor}15`, border: `1px solid ${typeColor}25` }}
          >
            <Icon size={13} style={{ color: typeColor }} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-semibold truncate" style={{ color: "var(--foreground-bright)" }} title={node.name}>
              {shortName(node.name)}
            </p>
            <p className="text-[9px] truncate" style={{ color: "var(--muted)" }}>
              {node.type}{node.namespace ? ` / ${node.namespace}` : ""}
            </p>
          </div>
        </div>

        {/* Symptom — this is the key insight */}
        {node.symptom && (
          <p className="mt-1.5 text-[10px] leading-snug line-clamp-2" style={{ color: "var(--foreground)", opacity: 0.85 }} title={node.symptom}>
            {node.symptom}
          </p>
        )}

        {node.severity && node.severity !== "unknown" && (
          <div className="mt-1.5 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase" style={{ background: `${statusColor}15`, color: statusColor }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: statusColor }} />
            {node.severity}
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ─── Detail Panel ───────────────────────────────────────────────

function DetailPanel({ node, edges, chains, onClose }: {
  node: GraphNode; edges: GraphEdge[]; chains: CausalChain[]; onClose: () => void;
}) {
  const Icon = TYPE_ICONS[node.type] || Box;
  const typeColor = TYPE_COLORS[node.type] || "var(--muted)";
  const outgoing = edges.filter((e) => e.source === node.id);
  const incoming = edges.filter((e) => e.target === node.id);
  const relevant = chains.filter((c) => c.symptom_resource === node.id || c.steps.some((s) => s.resource === node.id));

  return (
    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} className="w-80 flex-shrink-0 flex flex-col gap-3 overflow-y-auto max-h-full">
      <div className="glass-card p-4">
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: `${typeColor}15`, border: `1px solid ${typeColor}25` }}>
              <Icon size={16} style={{ color: typeColor }} />
            </div>
            <div>
              <h3 className="text-sm font-bold" style={{ color: "var(--foreground-bright)" }}>{node.name}</h3>
              <p className="text-[10px]" style={{ color: "var(--muted)" }}>{node.type}{node.namespace ? ` in ${node.namespace}` : ""}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/5 cursor-pointer"><X size={14} style={{ color: "var(--muted)" }} /></button>
        </div>
        {node.symptom && <p className="text-xs leading-relaxed mt-2" style={{ color: "var(--foreground)" }}>{node.symptom}</p>}
      </div>

      {(outgoing.length > 0 || incoming.length > 0) && (
        <div className="glass-card p-4">
          <h4 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--muted)" }}>Connections</h4>
          {outgoing.map((e, i) => (
            <div key={`o-${i}`} className="flex items-center gap-2 text-[11px] py-1">
              <ChevronRight size={10} style={{ color: "var(--critical)" }} />
              <span style={{ color: "var(--foreground)" }}>{e.target.split("/").pop()}</span>
              <span className="ml-auto text-[9px]" style={{ color: "var(--muted)" }}>{e.relationship.replace(/_/g, " ")}</span>
            </div>
          ))}
          {incoming.map((e, i) => (
            <div key={`i-${i}`} className="flex items-center gap-2 text-[11px] py-1">
              <ChevronRight size={10} style={{ color: "var(--warning)", transform: "rotate(180deg)" }} />
              <span style={{ color: "var(--foreground)" }}>{e.source.split("/").pop()}</span>
              <span className="ml-auto text-[9px]" style={{ color: "var(--muted)" }}>{e.relationship.replace(/_/g, " ")}</span>
            </div>
          ))}
        </div>
      )}

      {relevant.length > 0 && (
        <div className="glass-card p-4">
          <h4 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--muted)" }}>Failure Traces</h4>
          {relevant.map((chain) => (
            <div key={chain.id} className="p-2.5 rounded-lg mb-2" style={{ background: "rgba(239,68,68,0.05)", border: "1px solid rgba(239,68,68,0.15)" }}>
              <p className="text-xs font-medium" style={{ color: "var(--foreground-bright)" }}>{chain.symptom}</p>
              {chain.root_cause && <p className="text-[10px] mt-1" style={{ color: "var(--foreground)" }}>Root cause: {chain.root_cause}</p>}
              <div className="flex items-center gap-1 flex-wrap mt-2">
                {chain.steps.map((step, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ background: step.resource === node.id ? "rgba(99,102,241,0.15)" : "rgba(0,0,0,0.2)", color: step.resource === node.id ? "var(--accent-light)" : "var(--muted)" }}>
                      {step.resource.split("/").pop()?.split("-").slice(0, -2).join("-") || step.resource.split("/").pop()}
                    </span>
                    {i < chain.steps.length - 1 && <ChevronRight size={8} style={{ color: "var(--muted)", opacity: 0.4 }} />}
                  </div>
                ))}
              </div>
              <p className="text-[10px] mt-1.5" style={{ color: chain.confidence >= 0.7 ? "var(--success)" : "var(--warning)" }}>{Math.round(chain.confidence * 100)}% confidence</p>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

// ─── Chain Trace (step-by-step below graph) ─────────────────────

function ChainTrace({ chain, index }: { chain: CausalChain; index: number }) {
  const [expanded, setExpanded] = useState(index === 0);

  const resourceType = (r: string) => {
    const kind = r.split("/")[0]?.toLowerCase();
    return ["pod", "deployment", "service", "configmap", "secret", "node", "replicaset"].includes(kind ?? "") ? kind! : "pod";
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.06 }}>
      <button onClick={() => setExpanded(!expanded)} className="w-full glass-card p-3 text-left cursor-pointer transition-all" style={{ borderColor: expanded ? "rgba(239,68,68,0.25)" : undefined }}>
        <div className="flex items-center gap-3">
          <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: "var(--critical)", boxShadow: "0 0 6px var(--critical)" }} />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold" style={{ color: "var(--foreground-bright)" }}>{chain.symptom}</p>
            {chain.root_cause && <p className="text-[10px] mt-0.5" style={{ color: "var(--foreground)" }}>→ {chain.root_cause}</p>}
          </div>
          <span className="text-[10px]" style={{ color: chain.confidence >= 0.7 ? "var(--success)" : "var(--warning)" }}>{Math.round(chain.confidence * 100)}%</span>
          <ChevronRight size={14} style={{ color: "var(--muted)", transform: expanded ? "rotate(90deg)" : "none", transition: "transform 0.2s" }} />
        </div>
      </button>
      <AnimatePresence>
        {expanded && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="ml-5 mt-1 mb-2">
              {chain.steps.map((step, i) => {
                const rType = resourceType(step.resource);
                const Icon = TYPE_ICONS[rType] || Box;
                const color = TYPE_COLORS[rType] || "var(--muted)";
                return (
                  <div key={i} className="flex items-stretch gap-0">
                    <div className="flex flex-col items-center w-7 flex-shrink-0">
                      <div className="w-px" style={{ height: 6, background: i === 0 ? "transparent" : "rgba(239,68,68,0.25)" }} />
                      <div className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0" style={{ background: `${color}15` }}>
                        <Icon size={10} style={{ color }} />
                      </div>
                      {i < chain.steps.length - 1 && <div className="w-px flex-1" style={{ background: "rgba(239,68,68,0.25)" }} />}
                    </div>
                    <div className="flex-1 ml-2 mb-1 p-2 rounded-lg" style={{ background: "rgba(0,0,0,0.12)", border: "1px solid var(--border-subtle)" }}>
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-[9px] font-bold uppercase px-1 py-0.5 rounded" style={{ background: `${color}15`, color }}>{rType}</span>
                        <span className="text-[11px] font-medium" style={{ color: "var(--foreground-bright)" }}>{shortName(step.resource.split("/").pop() || step.resource)}</span>
                      </div>
                      <p className="text-[10px]" style={{ color: "var(--foreground)" }}>{step.observation}</p>
                      {step.evidence_excerpt && <p className="text-[9px] mt-0.5 font-mono truncate" style={{ color: "var(--muted)" }}>{step.evidence_excerpt}</p>}
                    </div>
                  </div>
                );
              })}
              {chain.root_cause && (
                <div className="flex items-stretch gap-0">
                  <div className="flex flex-col items-center w-7 flex-shrink-0">
                    <div className="w-px" style={{ height: 6, background: "rgba(239,68,68,0.25)" }} />
                    <div className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0" style={{ background: "rgba(239,68,68,0.12)" }}>
                      <Target size={10} style={{ color: "var(--critical)" }} />
                    </div>
                  </div>
                  <div className="flex-1 ml-2 p-2 rounded-lg" style={{ background: "rgba(239,68,68,0.05)", border: "1px solid rgba(239,68,68,0.15)" }}>
                    <span className="text-[9px] font-bold uppercase" style={{ color: "var(--critical)" }}>Root Cause</span>
                    <p className="text-[11px] mt-0.5" style={{ color: "var(--foreground-bright)" }}>{chain.root_cause}</p>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────

export default function DependencyGraphPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const bundleId = typeof id === "string" ? id : null;
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [highlightedChain, setHighlightedChain] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["dependency-graph", bundleId],
    queryFn: () => getDependencyGraph(bundleId!),
    enabled: !!bundleId,
    retry: 2,
  });

  const positionedNodes = useMemo(() => data?.nodes ? layoutNodes(data.nodes) : [], [data?.nodes]);
  const nodeMap = useMemo(() => { const m = new Map<string, PositionedNode>(); positionedNodes.forEach((n) => m.set(n.id, n)); return m; }, [positionedNodes]);
  const canvasSize = useMemo(() => {
    if (positionedNodes.length === 0) return { width: 800, height: 300 };
    return {
      width: Math.max(800, Math.max(...positionedNodes.map((n) => n.x)) + 260),
      height: Math.max(300, Math.max(...positionedNodes.map((n) => n.y)) + 120),
    };
  }, [positionedNodes]);

  const highlightedNodes = useMemo(() => {
    if (!highlightedChain || !data?.causal_chains) return null;
    const chain = data.causal_chains.find((c) => c.id === highlightedChain);
    if (!chain) return null;
    const set = new Set<string>();
    set.add(chain.symptom_resource);
    chain.steps.forEach((s) => set.add(s.resource));
    chain.related_resources.forEach((r) => set.add(r));
    return set;
  }, [highlightedChain, data?.causal_chains]);

  const usedColumns = useMemo(() => {
    const cols = new Set<number>();
    positionedNodes.forEach((n) => cols.add(n.col));
    return Array.from(cols).sort();
  }, [positionedNodes]);

  const selectedNodeData = useMemo(() => data?.nodes.find((n) => n.id === selectedNode) ?? null, [selectedNode, data?.nodes]);

  const stats = useMemo(() => {
    if (!data) return { total: 0, critical: 0, chains: 0 };
    return {
      total: data.nodes.length,
      critical: data.nodes.filter((n) => n.severity === "critical").length,
      chains: data.causal_chains.length,
    };
  }, [data]);

  if (!bundleId) return null;

  if (isLoading) {
    return <div className="flex items-center justify-center pt-32"><Loader2 size={20} className="animate-spin" style={{ color: "var(--accent-light)" }} /><p className="ml-3 text-sm" style={{ color: "var(--muted)" }}>Loading...</p></div>;
  }

  if (isError || !data || (data.nodes.length === 0 && data.causal_chains.length === 0)) {
    return (
      <div className="flex flex-col gap-5">
        <motion.div className="dashboard-header" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <h1 className="text-lg font-semibold" style={{ color: "var(--foreground-bright)" }}>Dependency Graph</h1>
        </motion.div>
        <div className="glass-card p-10 text-center">
          <ZapOff size={28} style={{ color: "var(--muted)", margin: "0 auto 10px" }} />
          <p className="text-sm" style={{ color: "var(--foreground)" }}>No dependency data available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <motion.div className="dashboard-header" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <h1 className="text-lg font-semibold" style={{ color: "var(--foreground-bright)" }}>Dependency Graph</h1>
        <div className="filter-pill"><Box size={12} />{stats.total} Resources</div>
        {stats.critical > 0 && <div className="filter-pill" style={{ borderColor: "rgba(239,68,68,0.3)", color: "var(--critical)" }}><AlertTriangle size={12} />{stats.critical} Critical</div>}
        {stats.chains > 0 && <div className="filter-pill"><GitBranch size={12} />{stats.chains} Chains</div>}
      </motion.div>

      {/* Chain filter pills */}
      {data.causal_chains.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => setHighlightedChain(null)} className="px-3 py-1.5 rounded-lg text-[11px] font-medium cursor-pointer transition-all" style={{ background: highlightedChain === null ? "rgba(99,102,241,0.12)" : "transparent", border: `1px solid ${highlightedChain === null ? "rgba(99,102,241,0.3)" : "var(--border-subtle)"}`, color: highlightedChain === null ? "var(--accent-light)" : "var(--muted)" }}>
            All Resources
          </button>
          {data.causal_chains.map((c) => (
            <button key={c.id} onClick={() => setHighlightedChain(highlightedChain === c.id ? null : c.id)} className="px-3 py-1.5 rounded-lg text-[11px] font-medium cursor-pointer transition-all truncate max-w-[220px]" style={{ background: highlightedChain === c.id ? "rgba(239,68,68,0.1)" : "transparent", border: `1px solid ${highlightedChain === c.id ? "rgba(239,68,68,0.3)" : "var(--border-subtle)"}`, color: highlightedChain === c.id ? "var(--critical)" : "var(--muted)" }} title={c.symptom}>
              {c.symptom.length > 35 ? c.symptom.slice(0, 35) + "..." : c.symptom}
            </button>
          ))}
        </div>
      )}

      {/* Visual Graph + Detail Panel */}
      <div className="flex gap-4 min-h-0">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card p-4 flex-1 overflow-auto relative">
          {/* Column headers */}
          <div className="flex gap-0 mb-1" style={{ width: canvasSize.width }}>
            {usedColumns.map((colIdx) => (
              <div key={colIdx} className="text-center" style={{ width: 260, marginLeft: colIdx === usedColumns[0] ? 30 : 0 }}>
                <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)", opacity: 0.5 }}>
                  {getColumnLabel(colIdx)}
                </span>
              </div>
            ))}
          </div>
          {/* Canvas */}
          <div className="relative" style={{ width: canvasSize.width, height: canvasSize.height }}>
            <EdgeLines edges={data.edges} nodeMap={nodeMap} highlightedNodes={highlightedNodes} />
            {positionedNodes.map((node, idx) => (
              <NodeCard
                key={node.id}
                node={node}
                isSelected={selectedNode === node.id}
                dimmed={highlightedNodes !== null && !highlightedNodes.has(node.id)}
                onClick={() => setSelectedNode(selectedNode === node.id ? null : node.id)}
                delay={idx}
              />
            ))}
          </div>
        </motion.div>

        <AnimatePresence>
          {selectedNodeData && <DetailPanel node={selectedNodeData} edges={data.edges} chains={data.causal_chains} onClose={() => setSelectedNode(null)} />}
        </AnimatePresence>
      </div>

      {/* Step-by-step traces below the graph */}
      {data.causal_chains.length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
          <h2 className="text-xs font-semibold uppercase tracking-wider mb-3 flex items-center gap-2" style={{ color: "var(--muted)" }}>
            <ArrowDown size={12} />Step-by-Step Failure Traces
          </h2>
          <div className="flex flex-col gap-2">
            {data.causal_chains.map((chain, i) => <ChainTrace key={chain.id} chain={chain} index={i} />)}
          </div>
        </motion.div>
      )}
    </div>
  );
}
