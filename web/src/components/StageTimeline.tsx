import type { Stage } from "../types";
import { useI18n, type StringKey } from "../lib/i18n";

/** The transcribe pipeline as the user sees it. `queued` sits before step 0. */
const STEPS: { stage: Stage; label: StringKey; hint: StringKey }[] = [
  { stage: "normalizing", label: "stageNormalizing", hint: "stepNormalizingHint" },
  { stage: "diarizing", label: "stageDiarizing", hint: "stepDiarizingHint" },
  { stage: "transcribing", label: "stageTranscribing", hint: "stepTranscribingHint" },
  { stage: "awaiting_review", label: "stageAwaitingReview", hint: "stepReviewHint" },
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
  done: "border-ok-600 bg-ok-600 text-white",
  active: "animate-pulse border-brand-600 bg-surface text-brand-600",
  failed: "border-bad-600 bg-bad-600 text-white",
  pending: "border-line bg-surface text-ink-400",
};

const TEXT: Record<State, string> = {
  done: "font-semibold text-ink-900",
  active: "font-bold text-brand-600",
  failed: "font-bold text-bad-600",
  pending: "text-ink-400",
};

/**
 * Vertical timeline. `detail` is the live line from the job stream ("120 of 380
 * turns") and belongs to whichever step is running; the others fall back to a
 * fixed description of what that step does.
 */
export function StageTimeline({
  stage,
  detail,
}: {
  stage: Stage | null | undefined;
  detail?: string | null;
}) {
  const { t } = useI18n();
  const failed = stage === "failed";
  // A failed job keeps its last stage in the UI only through `failed` itself,
  // so fall back to the first step rather than pretending nothing started.
  const current = failed ? 0 : (ORDER[stage ?? "queued"] ?? -1);

  return (
    <ol className="flex flex-col">
      {STEPS.map((step, i) => {
        const state = stateOf(i, current, failed);
        const last = i === STEPS.length - 1;
        return (
          <li key={step.stage} className="flex gap-3.5">
            <div className="flex flex-none flex-col items-center">
              <span
                className={`flex size-[22px] items-center justify-center rounded-full border-2 text-[11px] font-bold ${DOT[state]}`}
                aria-hidden
              >
                {state === "done" ? "✓" : state === "failed" ? "!" : i + 1}
              </span>
              {!last && (
                <span
                  className={`w-0.5 flex-1 ${state === "done" ? "bg-ok-600" : "bg-line"}`}
                  aria-hidden
                />
              )}
            </div>
            <div className={last ? "" : "pb-4"}>
              <div className={`text-sm ${TEXT[state]}`}>{t(step.label)}</div>
              <div className="text-[12.5px] text-ink-400">
                {state === "active" && detail ? detail : t(step.hint)}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
