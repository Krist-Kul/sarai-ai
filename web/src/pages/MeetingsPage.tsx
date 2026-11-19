import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { useI18n, type StringKey } from "../lib/i18n";
import { stageKind, type StageKind } from "../lib/stage";
import type { MeetingListItem } from "../types";
import { MeetingRow } from "../components/MeetingRow";
import { Icon, type IconName } from "../components/Icon";
import { ButtonLink, Card, Notice, PageHead, PrivacyNote, PulseDot } from "../components/ui";

type Filter = "all" | "review" | "processing" | "done" | "failed";

const FILTERS: { value: Filter; label: StringKey; kinds: StageKind[] | null }[] = [
  { value: "all", label: "filterAll", kinds: null },
  { value: "review", label: "filterReview", kinds: ["review"] },
  { value: "processing", label: "filterProcessing", kinds: ["queued", "running"] },
  { value: "done", label: "filterFinished", kinds: ["done"] },
  { value: "failed", label: "filterFailed", kinds: ["failed"] },
];

/** The API stores UTC without a zone marker. */
function parseUtc(iso: string): Date {
  return new Date(iso.replace(" ", "T") + "Z");
}

function useStats(items: MeetingListItem[]) {
  return useMemo(() => {
    const now = new Date();
    const count = (filter: Filter) => {
      const kinds = FILTERS.find((f) => f.value === filter)?.kinds;
      return kinds ? items.filter((i) => kinds.includes(stageKind(i.stage))).length : items.length;
    };
    // Meetings carry no completion time, so "this month" counts finished
    // meetings uploaded this month.
    const doneThisMonth = items.filter((i) => {
      if (stageKind(i.stage) !== "done") return false;
      const d = parseUtc(i.meeting.created_at);
      return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
    }).length;
    const seconds = items
      .filter((i) => i.has_transcript)
      .reduce((sum, i) => sum + (i.meeting.duration_sec ?? 0), 0);
    return {
      byFilter: Object.fromEntries(FILTERS.map((f) => [f.value, count(f.value)])) as Record<
        Filter,
        number
      >,
      doneThisMonth,
      hours: seconds / 3600,
    };
  }, [items]);
}

function Stat({
  label,
  value,
  dot,
  valueClass,
  highlight = false,
}: {
  label: string;
  value: string;
  dot: React.ReactNode;
  valueClass: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex min-w-0 flex-col gap-1.5 rounded-lg border bg-surface px-5 pt-4 pb-[18px] ${
        highlight ? "border-brand shadow-glow" : "border-line shadow-card"
      }`}
    >
      <div className="flex items-center gap-2">
        {dot}
        <span className="truncate text-small text-ink-muted">{label}</span>
      </div>
      <span
        className={`font-mono text-[30px] leading-[38px] font-semibold tracking-[-0.6px] ${valueClass}`}
      >
        {value}
      </span>
    </div>
  );
}

const STEPS: { icon: IconName; eyebrow: string; title: StringKey; body: StringKey }[] = [
  { icon: "upload-20", eyebrow: "01 · UPLOAD", title: "stepUploadTitle", body: "stepUploadBody" },
  {
    icon: "waveform-20",
    eyebrow: "02 · TRANSCRIBE",
    title: "stepTranscribeTitle",
    body: "stepTranscribeBody",
  },
  { icon: "pencil-20", eyebrow: "03 · REVIEW", title: "stepReviewTitle", body: "stepReviewBody" },
  {
    icon: "sparkle-20",
    eyebrow: "04 · MINUTES",
    title: "stepMinutesTitle",
    body: "stepMinutesBody",
  },
];

function EmptyState() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center gap-10 pt-6 pb-2 sm:pt-8">
      <div className="flex flex-col items-center gap-4 text-center">
        <div
          aria-hidden
          className="mb-2 flex size-24 items-center justify-center gap-1 rounded-[28px] shadow-[0_16px_40px_-8px_rgba(79,70,229,0.3)]"
          style={{ backgroundImage: "linear-gradient(135deg, #4f46e5 25%, #06b6d4 75%)" }}
        >
          {[14, 30, 44, 24, 36, 18].map((h, i) => (
            <span key={i} className="w-[5px] rounded-[3px] bg-white" style={{ height: h }} />
          ))}
        </div>
        <h1 className="text-[34px] leading-[46px] font-semibold tracking-[-0.96px] sm:text-[48px] sm:leading-[60px]">
          {t("emptyTitle")}
        </h1>
        <p className="max-w-[560px] text-[18px] leading-[30px] text-ink-muted">{t("emptyBody")}</p>
        <div className="pt-2">
          <ButtonLink to="/new" icon="upload">
            {t("uploadCta")}
          </ButtonLink>
        </div>
        <PrivacyNote />
      </div>
      <div className="grid w-full gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((step) => (
          <Card key={step.eyebrow} className="flex flex-col gap-2.5 p-5">
            <div className="flex items-center">
              <span className="flex size-10 items-center justify-center rounded-md bg-brand-soft text-brand">
                <Icon name={step.icon} />
              </span>
              <span className="ml-auto text-eyebrow text-ink-subtle">{step.eyebrow}</span>
            </div>
            <p className="text-[16px] leading-[28px] font-semibold">{t(step.title)}</p>
            <p className="text-small text-ink-muted">{t(step.body)}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function MeetingsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Filter>("all");
  const [newestFirst, setNewestFirst] = useState(true);

  const meetings = useQuery({
    queryKey: ["meetings"],
    queryFn: api.listMeetings,
    // Cheap poll keeps stage badges honest while jobs run. The dedicated
    // meeting page uses SSE instead of polling.
    refetchInterval: 5_000,
  });

  const remove = useMutation({
    mutationFn: api.deleteMeeting,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["meetings"] }),
  });

  const all = useMemo(() => meetings.data ?? [], [meetings.data]);
  const stats = useStats(all);

  const visible = useMemo(() => {
    const kinds = FILTERS.find((f) => f.value === filter)?.kinds ?? null;
    const rows = all.filter((item) => !kinds || kinds.includes(stageKind(item.stage)));
    const time = (i: MeetingListItem) => parseUtc(i.meeting.created_at).getTime();
    return rows.sort((a, b) => (newestFirst ? time(b) - time(a) : time(a) - time(b)));
  }, [all, filter, newestFirst]);

  if (meetings.isPending) return <p className="text-small text-ink-muted">{t("loading")}</p>;

  if (meetings.isError) {
    const message =
      meetings.error instanceof ApiError ? meetings.error.message : String(meetings.error);
    return (
      <Notice
        tone="danger"
        inline
        action={
          <button
            type="button"
            onClick={() => meetings.refetch()}
            className="cursor-pointer text-small-strong underline"
          >
            {t("retry")}
          </button>
        }
      >
        <span className="font-semibold">{t("errorTitle")}</span> — {message}
      </Notice>
    );
  }

  if (all.length === 0) return <EmptyState />;

  return (
    <div className="flex flex-col gap-8">
      <PageHead
        eyebrow={`MEETINGS · ${all.length}`}
        title={t("meetings")}
        subtitle={t("meetingsSubtitle")}
      />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Stat
          label={t("statReview")}
          value={String(stats.byFilter.review)}
          dot={<span aria-hidden className="size-1.5 rounded-full bg-brand" />}
          valueClass="text-brand-ink"
          highlight={stats.byFilter.review > 0}
        />
        <Stat
          label={t("statProcessing")}
          value={String(stats.byFilter.processing)}
          dot={<PulseDot />}
          valueClass="text-live"
        />
        <Stat
          label={t("statDoneMonth")}
          value={String(stats.doneThisMonth)}
          dot={<span aria-hidden className="size-1.5 rounded-full bg-done" />}
          valueClass="text-done"
        />
        <Stat
          label={t("statHours")}
          value={stats.hours.toFixed(1)}
          dot={<span aria-hidden className="size-1.5 rounded-full bg-line-control" />}
          valueClass="text-ink"
        />
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <div
            role="tablist"
            className="flex max-w-full gap-0.5 overflow-x-auto rounded-full border border-line bg-surface p-1"
          >
            {FILTERS.map((option) => {
              const active = filter === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setFilter(option.value)}
                  className={`flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full py-[5px] pr-3 pl-3.5 text-[13px] leading-5 ${
                    active ? "bg-ink text-on-ink" : "text-ink-muted hover:text-ink"
                  }`}
                >
                  <span className="font-semibold">{t(option.label)}</span>
                  <span className={`font-mono ${active ? "" : "text-ink-subtle"}`}>
                    {stats.byFilter[option.value]}
                  </span>
                </button>
              );
            })}
          </div>
          <button
            type="button"
            onClick={() => setNewestFirst((v) => !v)}
            className="ml-auto flex cursor-pointer items-center gap-1.5 whitespace-nowrap"
          >
            <span className="text-small text-ink-subtle">{t("sortBy")}</span>
            <span className="text-small-strong text-ink">
              {t(newestFirst ? "sortNewest" : "sortOldest")}
            </span>
          </button>
        </div>

        {visible.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line bg-surface px-6 py-12 text-center">
            <p className="text-small text-ink-muted">{t("noMatches")}</p>
            <button
              type="button"
              onClick={() => setFilter("all")}
              className="mt-3 cursor-pointer text-small-strong text-brand-ink hover:underline"
            >
              {t("clearFilters")}
            </button>
          </div>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {visible.map((item) => (
              <MeetingRow
                key={item.meeting.id}
                item={item}
                onDelete={() => {
                  if (window.confirm(t("deleteConfirm"))) remove.mutate(item.meeting.id);
                }}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
