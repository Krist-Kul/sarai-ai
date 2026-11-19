/**
 * Nine stages, four things the user actually has to know: it is waiting, it is
 * working, it wants you, or it broke. Every status colour and icon in the UI
 * derives from this reduction so the list and the detail page never disagree.
 */
import type { Stage } from "../types";
import type { StringKey } from "./i18n";

export type StageKind = "queued" | "running" | "review" | "done" | "failed";

const RUNNING: ReadonlySet<Stage> = new Set<Stage>([
  "normalizing",
  "diarizing",
  "transcribing",
  "summarizing",
  "rendering",
]);

export function stageKind(stage: Stage | null | undefined): StageKind {
  if (stage === "failed") return "failed";
  if (stage === "awaiting_review") return "review";
  if (stage === "done") return "done";
  if (stage != null && RUNNING.has(stage)) return "running";
  return "queued";
}

export const STAGE_LABEL: Record<Stage, StringKey> = {
  queued: "stageQueued",
  normalizing: "stageNormalizing",
  diarizing: "stageDiarizing",
  transcribing: "stageTranscribing",
  awaiting_review: "stageAwaitingReview",
  summarizing: "stageSummarizing",
  rendering: "stageRendering",
  done: "stageDone",
  failed: "stageFailed",
};

/** Badge fill + text. `queued` stays neutral: nothing is happening yet. */
export const KIND_TONE: Record<StageKind, string> = {
  queued: "bg-surface-raised text-ink-muted",
  running: "bg-live-soft text-live",
  review: "bg-brand-soft text-brand-ink",
  done: "bg-done-soft text-done",
  failed: "bg-danger-soft text-danger",
};
