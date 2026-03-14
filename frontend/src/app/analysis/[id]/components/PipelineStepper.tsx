"use client";

import { motion } from "framer-motion";
import { CheckCircle, Loader2, XCircle } from "lucide-react";
import { STAGES, STAGE_SHORT } from "../constants";
import type { StageState } from "../types";

export function PipelineStepper({ stages }: { stages: StageState[] }) {
  return (
    <motion.div
      className="glass-card p-5"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4 }}
    >
      <h3
        className="mb-4 text-xs font-medium uppercase tracking-wider"
        style={{ color: "var(--muted)" }}
      >
        Pipeline Stages
      </h3>
      <div className="pipeline-stepper">
        {stages.map((stage, i) => (
          <div key={STAGES[i]} className={`pipeline-step ${stage.status}`}>
            <div className="step-dot">
              {stage.status === "complete" ? (
                <CheckCircle size={14} style={{ color: "white" }} />
              ) : stage.status === "running" ? (
                <Loader2 size={14} className="animate-spin" style={{ color: "var(--accent-light)" }} />
              ) : stage.status === "failed" ? (
                <XCircle size={14} style={{ color: "white" }} />
              ) : (
                <span className="text-[9px]" style={{ color: "var(--muted)" }}>{i + 1}</span>
              )}
            </div>
            <span className="step-label">{STAGE_SHORT[i]}</span>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
