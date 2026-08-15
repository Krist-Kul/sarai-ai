import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { formatDateTime, formatDuration, useI18n } from "../lib/i18n";
import { StageBadge } from "../components/StageBadge";

export function MeetingsPage() {
  const { t, lang } = useI18n();
  const queryClient = useQueryClient();

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

  if (meetings.isPending) return <p className="text-ink-600">{t("loading")}</p>;

  if (meetings.isError) {
    const message =
      meetings.error instanceof ApiError ? meetings.error.message : String(meetings.error);
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-rose-800">
        <p className="font-medium">{t("errorTitle")}</p>
        <p className="mt-1 text-sm">{message}</p>
        <button onClick={() => meetings.refetch()} className="mt-3 text-sm underline">
          {t("retry")}
        </button>
      </div>
    );
  }

  if (meetings.data.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <h2 className="text-lg font-semibold">{t("emptyTitle")}</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-ink-600">{t("emptyBody")}</p>
        <Link
          to="/new"
          className="mt-6 inline-block rounded-lg bg-brand-600 px-5 py-2.5 font-medium text-white hover:bg-brand-500"
        >
          {t("uploadCta")}
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("meetings")}</h1>
        <Link
          to="/new"
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500"
        >
          {t("uploadCta")}
        </Link>
      </div>

      <ul className="divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 bg-white">
        {meetings.data.map((item) => (
          <li key={item.meeting.id} className="flex items-center gap-4 px-4 py-3">
            <div className="min-w-0 flex-1">
              <Link
                to={`/meetings/${item.meeting.id}`}
                className="block truncate font-medium hover:text-brand-600"
              >
                {item.meeting.title}
              </Link>
              <p className="mt-0.5 text-xs text-ink-600">
                {item.meeting.meeting_date ?? formatDateTime(item.meeting.created_at, lang)} ·{" "}
                {formatDuration(item.meeting.duration_sec)} · {item.meeting.source_file}
              </p>
            </div>
            <StageBadge stage={item.stage} />
            <button
              onClick={() => {
                if (window.confirm(t("deleteConfirm"))) remove.mutate(item.meeting.id);
              }}
              className="rounded-lg px-2 py-1 text-sm text-ink-400 hover:bg-slate-100 hover:text-rose-600"
            >
              {t("delete")}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
