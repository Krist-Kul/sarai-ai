import type { Stage } from "../types";
import { useI18n, type StringKey } from "../lib/i18n";
import { Icon } from "./Icon";

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
  // Past review: every transcribe step is behind us.
  summarizing: 4,
  rendering: 4,
  done: 4,
};

type State = "done" | "active" | "review" | "failed" | "pending";

function stateOf(index: number, current: number, failed: boolean): State {
  if (index < current) return "done";
  if (index > current) return "pending";
  if (failed) return "failed";
  return index === STEPS.length - 1 ? "review" : "active";
}

const DOT: Record<State, string> = {
  done: "border-done bg-done text-surface",
  active: "border-live bg-surface text-live shadow-[0_0_0_4px_color-mix(in_srgb,var(--live)_16%,transparent)]",
  review: "border-brand bg-brand text-on-brand shadow-glow",
  failed: "border-danger bg-danger text-surface",
  pending: "border-line-control bg-surface text-ink-subtle",
};

const LABEL: Record<State, string> = {
  done: "text-ink",
  active: "text-live",
  review: "text-brand-ink",
  failed: "text-danger",
  pending: "text-ink-subtle",
};

/**
 * Vertical pipeline. `detail` is the live line from the job stream ("120 / 380
 * turns") and belongs to whichever step is running; the others show a fixed
 * description of what that step does.
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
        const live = state === "active" && detail;
        return (
          <li key={step.stage} className="flex gap-3.5">
            <div className="flex flex-none flex-col items-center gap-1">
              <span
                className={`flex size-6 items-center justify-center rounded-[12px] border-2 font-mono text-[11px] font-semibold ${DOT[state]}`}
                aria-hidden
              >
                {state === "done" ? (
                  <Icon name="check-14" />
                ) : state === "review" ? (
                  <Icon name="pencil-14" />
                ) : state === "failed" ? (
                  "!"
                ) : (
                  String(i + 1).padStart(2, "0")
                )}
              </span>
              {!last && (
                <span
                  className={`min-h-4 w-0.5 flex-1 rounded-[1px] ${
                    state === "done" ? "bg-done" : "bg-line"
                  }`}
                  aria-hidden
                />
              )}
            </div>
            <div className={`min-w-0 flex-1 ${last ? "" : "pb-4"}`}>
              <div className={`text-label ${LABEL[state]}`}>{t(step.label)}</div>
              <div className={live ? "text-data text-ink-muted" : "text-small text-ink-subtle"}>
                {live ? detail : t(step.hint)}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
