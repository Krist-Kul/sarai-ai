import type { Stage } from "../types";
import { useI18n } from "../lib/i18n";
import { KIND_TONE, STAGE_LABEL, stageKind } from "../lib/stage";

export function StageBadge({ stage }: { stage: Stage | null | undefined }) {
  const { t } = useI18n();
  if (!stage) return <span className="text-sm text-ink-400">—</span>;
  const kind = stageKind(stage);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${KIND_TONE[kind]}`}
    >
      {kind === "running" && (
        <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden />
      )}
      {t(STAGE_LABEL[stage])}
    </span>
  );
}
