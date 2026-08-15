import { Link, useParams } from "react-router-dom";
import { useCallback, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { formatDateTime, formatDuration, useI18n } from "../lib/i18n";
import { useElapsed, useJobEvents } from "../lib/useJobEvents";
import { StageBadge } from "../components/StageBadge";
import { StageStepper } from "../components/StageStepper";
import type { Stage } from "../types";

const LIVE_STAGES = new Set<Stage>(["queued", "normalizing", "diarizing", "transcribing"]);

export function MeetingPage() {
  const { id = "" } = useParams();
  const { t, lang } = useI18n();
  const queryClient = useQueryClient();

  // Progress arrives over SSE. Polling only wakes up if the stream dies, and
  // the two never run together -- that would double the load and race.
  const streamLost = useRef(false);
  const meeting = useQuery({
    queryKey: ["meeting", id],
    queryFn: () => api.getMeeting(id),
    refetchInterval: () => (streamLost.current ? 3_000 : false),
  });

  const jobId = meeting.data?.job_id ?? null;
  const dbStage = meeting.data?.stage ?? null;

  const onEnd = useCallback(() => {
    // The stream is closed; refetch so has_transcript and the rest are current.
    void queryClient.invalidateQueries({ queryKey: ["meeting", id] });
    void queryClient.invalidateQueries({ queryKey: ["meetings"] });
  }, [queryClient, id]);

  const { event, status } = useJobEvents(jobId, {
    enabled: dbStage != null && LIVE_STAGES.has(dbStage),
    onEnd,
  });

  // Live frames win; the fetched row is the starting point and the fallback.
  const stage = event?.stage ?? dbStage;
  const progress = event?.progress ?? meeting.data?.progress ?? 0;
  const detail = event?.detail ?? meeting.data?.detail ?? null;
  const error = event?.error ?? meeting.data?.error ?? null;

  const running = stage != null && LIVE_STAGES.has(stage);
  const elapsed = useElapsed(meeting.data?.meeting.created_at, running);
  streamLost.current = running && status === "lost";

  if (meeting.isPending) return <p className="text-ink-600">{t("loading")}</p>;
  if (meeting.isError) {
    const message =
      meeting.error instanceof ApiError ? meeting.error.message : String(meeting.error);
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-rose-800">
        <p className="font-medium">{t("errorTitle")}</p>
        <p className="mt-1 text-sm">{message}</p>
      </div>
    );
  }

  const m = meeting.data.meeting;

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-sm text-brand-600 hover:underline">
          ← {t("back")}
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold">{m.title}</h1>
          <StageBadge stage={stage} />
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-4 rounded-xl border border-slate-200 bg-white p-4 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-ink-600">{t("date")}</dt>
          <dd className="mt-0.5 font-medium">{m.meeting_date ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-ink-600">{t("duration")}</dt>
          <dd className="mt-0.5 font-medium">{formatDuration(m.duration_sec)}</dd>
        </div>
        <div>
          <dt className="text-ink-600">{t("language")}</dt>
          <dd className="mt-0.5 font-medium uppercase">{m.language_hint}</dd>
        </div>
        <div>
          <dt className="text-ink-600">{running ? t("elapsed") : t("created")}</dt>
          <dd className="mt-0.5 font-medium tabular-nums">
            {running ? formatDuration(elapsed) : formatDateTime(m.created_at, lang)}
          </dd>
        </div>
      </dl>

      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
        <StageStepper stage={stage} />

        <div>
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">{t("progress")}</span>
            <span className="text-ink-600">{detail ?? "—"}</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200">
            <div
              className={`h-full transition-[width] duration-500 ${
                stage === "failed" ? "bg-rose-500" : "bg-brand-600"
              }`}
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
        </div>

        <p className="flex items-center gap-2 text-xs text-ink-600">
          {running && status === "live" && (
            <>
              <span className="size-1.5 animate-pulse rounded-full bg-emerald-500" aria-hidden />
              {t("liveLive")}
            </>
          )}
          {running && status === "connecting" && t("liveConnecting")}
          {running && status === "lost" && (
            <span className="text-amber-700">{t("liveLost")}</span>
          )}
          {stage === "queued" && <span className="ml-auto">{t("queuedNote")}</span>}
          {stage === "awaiting_review" && <span>{t("readyNote")}</span>}
          {stage === "failed" && <span className="text-rose-700">{t("failedNote")}</span>}
        </p>

        {error && (
          <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
            {error}
          </p>
        )}
      </div>

      <audio controls src={api.audioUrl(m.id)} className="w-full">
        <track kind="captions" />
      </audio>
    </div>
  );
}
