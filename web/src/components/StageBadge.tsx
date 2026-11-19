import type { Stage } from "../types";
import { useI18n } from "../lib/i18n";
import { KIND_TONE, STAGE_LABEL, stageKind } from "../lib/stage";
import { PulseDot } from "./ui";

/** Pill status label: Queued, Running (cyan pulse dot), Review, Done, Failed. */
export function StageBadge({ stage }: { stage: Stage | null | undefined }) {
  const { t } = useI18n();
  if (!stage) return <span className="text-small text-ink-subtle">—</span>;
  const kind = stageKind(stage);
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-px text-small-strong ${KIND_TONE[kind]}`}
    >
      {kind === "running" && <PulseDot className="bg-current" />}
      {t(STAGE_LABEL[stage])}
    </span>
  );
}
