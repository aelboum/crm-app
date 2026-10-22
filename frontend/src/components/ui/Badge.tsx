import type { ReactNode } from "react";

/** Fixed status colours from the design (not tenant-changeable), plus the accent and a neutral chip. */
export type Tone = "neutral" | "accent" | "success" | "pending" | "risk" | "info";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
