"use client";

import { CheckCircle, AlertTriangle, XCircle } from "lucide-react";

export function StatusIcon({ result }: { result: { is_pass: boolean; is_warn: boolean; is_fail: boolean } }) {
  if (result.is_fail) return <XCircle size={14} style={{ color: "var(--critical)" }} />;
  if (result.is_warn) return <AlertTriangle size={14} style={{ color: "var(--warning)" }} />;
  return <CheckCircle size={14} style={{ color: "var(--success)" }} />;
}
