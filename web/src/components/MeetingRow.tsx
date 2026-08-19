import { Link } from "react-router-dom";

import type { MeetingListItem } from "../types";
import { formatDateTime, formatDuration, useI18n } from "../lib/i18n";
import { KIND_ICON, stageKind, type StageKind } from "../lib/stage";
import { StageBadge } from "./StageBadge";

/** The row border carries the same signal as the badge: blue asks for you,
 *  red is broken, everything else stays quiet. */
const CARD: Record<StageKind, string> = {
  queued: "border-line",
  running: "border-line",
  review: "border-brand-200 shadow-[0_0_0_3px_rgba(59,91,212,.07)]",
  done: "border-line",
  failed: "border-bad-line",
};

const TILE: Record<StageKind, string> = {
  queued: "bg-sand text-ink-400",
  running: "bg-brand-50 text-brand-600",
  review: "bg-brand-50 text-brand-600",
  done: "bg-ok-50 text-ok-600",
  failed: "bg-bad-50 text-bad-600",
};

export function MeetingRow({
  item,
  onDelete,
}: {
  item: MeetingListItem;
  onDelete: () => void;
}) {
  const { t, lang } = useI18n();
  const m = item.meeting;
  const kind = stageKind(item.stage);
  const percent = Math.round((item.progress ?? 0) * 100);
  // The row's action goes where the work is: the review editor when a
  // transcript is waiting, the minutes when they exist.
  const href =
    kind === "review"
      ? `/meetings/${m.id}/review`
      : kind === "done" && item.has_summary
        ? `/meetings/${m.id}/minutes`
        : `/meetings/${m.id}`;

  const action =
    kind === "review"
      ? {
          label: `${t("actionReview")} →`,
          short: t("actionReviewShort"),
          className: "bg-brand-600 text-white hover:bg-brand-600/90",
        }
      : kind === "done"
        ? {
            label: t("actionOpen"),
            short: t("actionOpenShort"),
            className: "bg-ink-900 text-surface hover:bg-ink-900/90",
          }
        : kind === "failed"
          ? {
              label: t("actionDetails"),
              short: t("actionDetailsShort"),
              className: "border border-line bg-surface hover:border-ink-200",
            }
          : {
              label: t("actionWatch"),
              short: t("actionWatchShort"),
              className: "border border-line bg-surface hover:border-ink-200",
            };

  return (
    <li
      className={`flex items-center gap-2.5 rounded-2xl border bg-surface p-3 sm:gap-4 sm:px-[18px] sm:py-4 ${CARD[kind]}`}
    >
      <span
        className={`flex size-9 flex-none items-center justify-center rounded-lg text-sm sm:size-11 sm:rounded-xl sm:text-[17px] ${TILE[kind]}`}
        aria-hidden
      >
        {KIND_ICON[kind]}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <Link
            to={`/meetings/${m.id}`}
            className="truncate text-[15px] font-semibold hover:text-brand-600 sm:text-base"
          >
            {m.title}
          </Link>
          {/* The badge repeats what the tile colour already says, so on a phone
              it is the first thing to go. */}
          <span className="hidden sm:inline">
            <StageBadge stage={item.stage} />
          </span>
        </div>
        <p className="truncate text-[12.5px] text-ink-600">
          {m.meeting_date ?? formatDateTime(m.created_at, lang)} · {formatDuration(m.duration_sec)}
          <span className="hidden sm:inline"> · {m.source_file}</span>
        </p>

        {kind === "running" && (
          <div className="mt-1.5 flex items-center gap-2.5">
            <span className="h-1 max-w-[420px] flex-1 overflow-hidden rounded-full bg-sand sm:h-1.5">
              <span
                className="block h-full rounded-full bg-brand-600 transition-[width] duration-500"
                style={{ width: `${percent}%` }}
              />
            </span>
            <span className="text-xs tabular-nums text-ink-600">{percent}%</span>
          </div>
        )}

        {kind === "failed" && (
          <p className="mt-1 truncate text-[12.5px] text-bad-600">{t("failedNote")}</p>
        )}
      </div>

      <Link
        to={href}
        className={`flex-none rounded-full px-3 py-1.5 text-[12.5px] font-semibold sm:px-4 sm:py-2 sm:text-[13.5px] ${action.className}`}
      >
        <span className="sm:hidden">{action.short}</span>
        <span className="hidden sm:inline">{action.label}</span>
      </Link>

      {/* Deleting is confirmed by the caller, so it does not need a menu in
          front of it as a second speed bump. */}
      <button
        type="button"
        onClick={onDelete}
        aria-label={`${t("delete")} ${m.title}`}
        title={t("delete")}
        className="flex size-8 flex-none items-center justify-center rounded-full text-bad-600 hover:bg-bad-50"
      >
        {/* Inline so the icon inherits the button's colour and the project
            stays free of an icon dependency for one glyph. */}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="size-[18px]"
          aria-hidden
        >
          <path d="M4 7h16" />
          <path d="M10 4h4a1 1 0 0 1 1 1v2H9V5a1 1 0 0 1 1-1Z" />
          <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" />
          <path d="M10 11v6M14 11v6" />
        </svg>
      </button>
    </li>
  );
}
