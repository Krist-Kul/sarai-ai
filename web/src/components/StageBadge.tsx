import type { Stage } from "../types";
import { useI18n, type StringKey } from "../lib/i18n";

const LABEL: Record<Stage, StringKey> = {
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

const TONE: Record<Stage, string> = {
  queued: "bg-slate-100 text-ink-600 ring-slate-200",
  normalizing: "bg-amber-50 text-amber-800 ring-amber-200",
  diarizing: "bg-amber-50 text-amber-800 ring-amber-200",
  transcribing: "bg-amber-50 text-amber-800 ring-amber-200",
  awaiting_review: "bg-brand-50 text-brand-600 ring-brand-200",
  summarizing: "bg-amber-50 text-amber-800 ring-amber-200",
  rendering: "bg-amber-50 text-amber-800 ring-amber-200",
  done: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  failed: "bg-rose-50 text-rose-700 ring-rose-200",
};

const ACTIVE: ReadonlySet<Stage> = new Set<Stage>([
  "normalizing",
  "diarizing",
  "transcribing",
  "summarizing",
  "rendering",
]);

export function StageBadge({ stage }: { stage: Stage | null | undefined }) {
  const { t } = useI18n();
  if (!stage) return <span className="text-sm text-ink-400">—</span>;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONE[stage]}`}
    >
      {ACTIVE.has(stage) && (
        <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden />
      )}
      {t(LABEL[stage])}
    </span>
  );
}
