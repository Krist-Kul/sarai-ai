import { Link } from "react-router-dom";

import type { MeetingListItem } from "../types";
import { formatDuration, formatIsoDateTime, useI18n } from "../lib/i18n";
import { stageKind, type StageKind } from "../lib/stage";
import { StageBadge } from "./StageBadge";
import { ButtonLink, IconButton, Progress, StatusTile, type ButtonVariant } from "./ui";

/** The row border carries the same signal as the badge: indigo asks for you,
 *  rose is broken, everything else stays quiet. */
const CARD: Record<StageKind, string> = {
  queued: "border-line shadow-card hover:shadow-pop",
  running: "border-line shadow-card hover:shadow-pop",
  review: "border-brand shadow-glow",
  done: "border-line shadow-card hover:shadow-pop",
  failed: "border-danger-line shadow-card hover:shadow-pop",
};

export function MeetingRow({
  item,
  onDelete,
}: {
  item: MeetingListItem;
  onDelete: () => void;
}) {
  const { t } = useI18n();
  const m = item.meeting;
  const kind = stageKind(item.stage);
  // The row's action goes where the work is: the review editor when a
  // transcript is waiting, the minutes when they exist.
  const href =
    kind === "review"
      ? `/meetings/${m.id}/review`
      : kind === "done" && item.has_summary
        ? `/meetings/${m.id}/minutes`
        : `/meetings/${m.id}`;

  const action: { label: string; short: string; variant: ButtonVariant } =
    kind === "review"
      ? { label: t("actionReview"), short: t("actionReviewShort"), variant: "primary" }
      : kind === "done"
        ? { label: t("actionOpen"), short: t("actionOpenShort"), variant: "solid" }
        : kind === "failed"
          ? { label: t("actionDetails"), short: t("actionDetailsShort"), variant: "outline" }
          : { label: t("actionWatch"), short: t("actionWatchShort"), variant: "outline" };

  return (
    <li
      className={`flex items-center gap-3 rounded-lg border bg-surface px-3 py-3 transition-shadow sm:min-h-[76px] sm:gap-4 sm:px-5 sm:py-4 ${CARD[kind]}`}
    >
      <span className="hidden sm:block">
        <StatusTile kind={kind} />
      </span>
      <span className="sm:hidden">
        <StatusTile kind={kind} size="sm" />
      </span>

      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <Link
            to={`/meetings/${m.id}`}
            className="truncate text-[15.5px] leading-[26px] font-semibold text-ink hover:text-brand-ink"
          >
            {m.title}
          </Link>
          {/* The badge repeats what the tile already says, so on a phone it is
              the first thing to go. */}
          <span className="hidden sm:inline-flex">
            <StageBadge stage={item.stage} />
          </span>
        </div>
        <p className="truncate text-data text-ink-muted">
          {m.meeting_date ?? formatIsoDateTime(m.created_at)} · {formatDuration(m.duration_sec)}
          <span className="hidden sm:inline"> · {m.source_file}</span>
        </p>

        {kind === "running" && (
          <Progress value={item.progress ?? 0} className="max-w-[420px] pt-1.5" />
        )}

        {kind === "failed" && <p className="truncate text-small text-danger">{t("failedNote")}</p>}
      </div>

      <ButtonLink
        to={href}
        variant={action.variant}
        size="sm"
        icon={kind === "review" ? "arrow-right" : undefined}
      >
        <span className="sm:hidden">{action.short}</span>
        <span className="hidden sm:inline">{action.label}</span>
      </ButtonLink>

      {/* Deleting is confirmed by the caller, so it needs no menu in front of
          it as a second speed bump. */}
      <IconButton icon="trash" label={`${t("delete")} ${m.title}`} onClick={onDelete} />
    </li>
  );
}
