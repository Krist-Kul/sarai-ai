import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { useI18n, type StringKey } from "../lib/i18n";
import { stageKind, type StageKind } from "../lib/stage";
import { MeetingRow } from "../components/MeetingRow";

type Filter = "all" | "attention" | "active" | "done";

const FILTERS: { value: Filter; label: StringKey; kinds: StageKind[] | null }[] = [
  { value: "all", label: "filterAll", kinds: null },
  { value: "attention", label: "filterAttention", kinds: ["review", "failed"] },
  { value: "active", label: "filterActive", kinds: ["queued", "running"] },
  { value: "done", label: "filterDone", kinds: ["done"] },
];

export function MeetingsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

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

  const all = meetings.data;

  const counts = useMemo(() => {
    const kinds = (all ?? []).map((item) => stageKind(item.stage));
    return {
      total: kinds.length,
      attention: kinds.filter((k) => k === "review" || k === "failed").length,
    };
  }, [all]);

  const visible = useMemo(() => {
    if (!all) return [];
    const needle = query.trim().toLowerCase();
    const kinds = FILTERS.find((f) => f.value === filter)?.kinds ?? null;
    return all.filter((item) => {
      if (kinds && !kinds.includes(stageKind(item.stage))) return false;
      if (!needle) return true;
      const haystack = `${item.meeting.title} ${item.meeting.source_file}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [all, query, filter]);

  if (meetings.isPending) return <p className="text-ink-600">{t("loading")}</p>;

  if (meetings.isError) {
    const message =
      meetings.error instanceof ApiError ? meetings.error.message : String(meetings.error);
    return (
      <div className="rounded-2xl border border-bad-line bg-bad-50 p-4 text-bad-600">
        <p className="font-semibold">{t("errorTitle")}</p>
        <p className="mt-1 text-sm">{message}</p>
        <button onClick={() => meetings.refetch()} className="mt-3 text-sm underline">
          {t("retry")}
        </button>
      </div>
    );
  }

  if (counts.total === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-line bg-surface px-6 py-16 text-center">
        <h2 className="text-lg font-bold">{t("emptyTitle")}</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-ink-600">{t("emptyBody")}</p>
        <Link
          to="/new"
          className="mt-6 inline-block rounded-full bg-brand-600 px-5 py-2.5 font-semibold text-white hover:bg-brand-600/90"
        >
          {t("uploadCta")}
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("meetings")}</h1>
          <p className="mt-0.5 text-[13px] text-ink-600">
            {t("meetingsSummary", { n: counts.total, k: counts.attention })}
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <label className="flex min-w-0 items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-2 text-[13px]">
            <span aria-hidden className="text-ink-400">
              ⌕
            </span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("searchMeetings")}
              className="w-36 min-w-0 border-0 bg-transparent outline-none placeholder:text-ink-400 sm:w-52"
            />
          </label>
          <div className="flex flex-wrap gap-1.5">
            {FILTERS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setFilter(option.value)}
                className={`rounded-full px-3 py-1.5 text-[12.5px] font-semibold ${
                  filter === option.value
                    ? "bg-ink-900 text-surface"
                    : "border border-line bg-surface text-ink-600 hover:border-ink-200"
                }`}
              >
                {t(option.label)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {visible.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line bg-surface px-6 py-12 text-center">
          <p className="text-sm text-ink-600">{t("noMatches")}</p>
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setFilter("all");
            }}
            className="mt-3 text-sm font-semibold text-brand-600 hover:underline"
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
  );
}
