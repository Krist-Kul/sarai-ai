import type { Stage } from "../types";
import { useI18n, type StringKey } from "../lib/i18n";

/** The transcribe pipeline as the user sees it. `queued` sits before step 0. */
const STEPS: { stage: Stage; label: StringKey }[] = [
  { stage: "normalizing", label: "stageNormalizing" },
  { stage: "diarizing", label: "stageDiarizing" },
  { stage: "transcribing", label: "stageTranscribing" },
  { stage: "awaiting_review", label: "stageAwaitingReview" },
];

const ORDER: Partial<Record<Stage, number>> = {
  queued: -1,
  normalizing: 0,
  diarizing: 1,
  transcribing: 2,
  awaiting_review: 3,
  summarizing: 3,
  rendering: 3,
  done: 3,
};

type State = "done" | "active" | "failed" | "pending";

function stateOf(index: number, current: number, failed: boolean): State {
  if (index < current) return "done";
  if (index > current) return "pending";
  return failed ? "failed" : index === STEPS.length - 1 ? "done" : "active";
}

const DOT: Record<State, string> = {
  done: "border-brand-600 bg-brand-600 text-white",
  active: "border-brand-600 bg-white text-brand-600",
  failed: "border-rose-500 bg-rose-500 text-white",
  pending: "border-slate-300 bg-white text-ink-400",
};

const TEXT: Record<State, string> = {
  done: "text-ink-900",
  active: "font-medium text-brand-600",
  failed: "font-medium text-rose-700",
  pending: "text-ink-400",
};

export function StageStepper({ stage }: { stage: Stage | null | undefined }) {
  const { t } = useI18n();
  const failed = stage === "failed";
  // A failed job keeps its last stage in the UI only through `failed` itself,
  // so fall back to the first step rather than pretending nothing started.
  const current = failed ? 0 : (ORDER[stage ?? "queued"] ?? -1);

  return (
    <ol className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-0">
      {STEPS.map((step, i) => {
        const state = stateOf(i, current, failed);
        return (
          <li key={step.stage} className="flex flex-1 items-center gap-3">
            <span
              className={`flex size-6 shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-semibold ${DOT[state]}`}
              aria-hidden
            >
              {state === "done" ? "✓" : state === "failed" ? "!" : i + 1}
            </span>
            <span className={`text-sm ${TEXT[state]}`}>{t(step.label)}</span>
            {i < STEPS.length - 1 && (
              <span
                className={`ml-auto hidden h-0.5 flex-1 sm:block ${
                  i < current ? "bg-brand-600" : "bg-slate-200"
                }`}
                aria-hidden
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
