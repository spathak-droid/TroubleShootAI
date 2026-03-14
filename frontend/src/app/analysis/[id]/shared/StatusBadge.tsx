"use client";

export function StatusBadge({ result }: { result: { is_pass: boolean; is_warn: boolean; is_fail: boolean } }) {
  if (result.is_fail) return <span className="badge badge-critical">FAIL</span>;
  if (result.is_warn) return <span className="badge badge-warning">WARN</span>;
  return <span className="badge badge-success">PASS</span>;
}
