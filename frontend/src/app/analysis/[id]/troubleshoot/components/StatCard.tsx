"use client";

import React from "react";
import { motion } from "framer-motion";

export function StatCard({
  label,
  value,
  color,
  icon: Icon,
}: {
  label: string;
  value: number;
  color: string;
  icon: React.ComponentType<{ size?: number; style?: React.CSSProperties }>;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-4 flex items-center gap-4"
    >
      <div
        className="flex h-10 w-10 items-center justify-center rounded-xl flex-shrink-0"
        style={{ background: `${color}18` }}
      >
        <Icon size={18} style={{ color }} />
      </div>
      <div>
        <p className="text-2xl font-bold" style={{ color }}>{value}</p>
        <p className="text-[11px] uppercase tracking-wider" style={{ color: "var(--muted)" }}>{label}</p>
      </div>
    </motion.div>
  );
}
