export function correctnessColor(correctness: string): string {
  switch (correctness) {
    case "Correct": return "var(--success)";
    case "Partially Correct": return "var(--warning)";
    case "Incorrect": return "var(--critical)";
    default: return "var(--muted)";
  }
}

export function correctnessBg(correctness: string): string {
  switch (correctness) {
    case "Correct": return "rgba(34, 197, 94, 0.12)";
    case "Partially Correct": return "rgba(234, 179, 8, 0.12)";
    case "Incorrect": return "rgba(239, 68, 68, 0.12)";
    default: return "rgba(148, 163, 184, 0.12)";
  }
}
