import { Link, useParams } from "react-router-dom";
import { useCallback, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { formatDateTime, formatDuration, useI18n } from "../lib/i18n";
import { stageKind } from "../lib/stage";
import { useElapsed, useJobEvents } from "../lib/useJobEvents";
import { StageBadge } from "../components/StageBadge";
import { StageTimeline } from "../components/StageTimeline";
import type { Stage } from "../types";

const LIVE_STAGES = new Set<Stage>([
  "queued",
  "normalizing",
  "diarizing",
  "transcribing",
  "summarizing",
  "rendering",
]);

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
      <div className="rounded-2xl border border-bad-line bg-bad-50 p-4 text-bad-600">
        <p className="font-semibold">{t("errorTitle")}</p>
        <p className="mt-1 text-sm">{message}</p>
      </div>
    );
  }

  const m = meeting.data.meeting;
  const kind = stageKind(stage);
  const percent = Math.round(progress * 100);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/" className="text-sm text-ink-600 hover:text-ink-900">
          ← {t("meetings")}
        </Link>
        <span className="text-ink-200" aria-hidden>
          /
        </span>
        <h1 className="text-xl font-bold tracking-tight">{m.title}</h1>
        <StageBadge stage={stage} />
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[380px_1fr]">
        <section className="rounded-2xl border border-line bg-surface p-5">
          <div className="flex items-baseline gap-2.5">
            <span className="text-[34px] font-bold tracking-tight tabular-nums">{percent}%</span>
            <span className="text-[13px] text-ink-600">{detail ?? t("progress")}</span>
          </div>
          <div className="mt-3 mb-5 h-2 overflow-hidden rounded-full bg-sand">
            <div
              className={`h-full rounded-full transition-[width] duration-500 ${
                kind === "failed" ? "bg-bad-600" : kind === "done" ? "bg-ok-600" : "bg-brand-600"
              }`}
              style={{ width: `${percent}%` }}
            />
          </div>

          <StageTimeline stage={stage} detail={detail} />

          <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line-soft pt-4 text-[12.5px] text-ink-600">
            {running && status === "live" && (
              <span className="inline-flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-ok-600" aria-hidden />
                {t("liveLive")}
              </span>
            )}
            {running && status === "connecting" && t("liveConnecting")}
            {running && status === "lost" && <span className="text-warn-600">{t("liveLost")}</span>}
            {stage === "queued" && <span>{t("queuedNote")}</span>}
            {stage === "awaiting_review" && <span>{t("readyNote")}</span>}
            {stage === "failed" && <span className="text-bad-600">{t("failedNote")}</span>}
            {running && <span className="ml-auto text-ink-400">{t("cancelJobHint")}</span>}
          </div>

          {error && (
            <p className="mt-3 rounded-xl border border-bad-line bg-bad-50 p-3 text-sm text-bad-600">
              {error}
            </p>
          )}
        </section>

        <div className="space-y-5">
          <section className="rounded-2xl border border-line bg-surface p-5">
            <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-[12.5px] text-ink-600">{t("date")}</dt>
                <dd className="mt-0.5 font-semibold">{m.meeting_date ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-[12.5px] text-ink-600">{t("duration")}</dt>
                <dd className="mt-0.5 font-semibold tabular-nums">
                  {formatDuration(m.duration_sec)}
                </dd>
              </div>
              <div>
                <dt className="text-[12.5px] text-ink-600">{t("language")}</dt>
                <dd className="mt-0.5 font-semibold uppercase">{m.language_hint}</dd>
              </div>
              <div>
                <dt className="text-[12.5px] text-ink-600">
                  {running ? t("elapsed") : t("created")}
                </dt>
                <dd className="mt-0.5 font-semibold tabular-nums">
                  {running ? formatDuration(elapsed) : formatDateTime(m.created_at, lang)}
                </dd>
              </div>
            </dl>

            {m.attendees && m.attendees.length > 0 && (
              <div className="mt-4 border-t border-line-soft pt-4">
                <div className="text-[12.5px] font-semibold text-ink-600">{t("attendees")}</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {m.attendees.map((a) => (
                    <span
                      key={a.name}
                      className="inline-flex items-center gap-1.5 rounded-full bg-sand px-2.5 py-0.5 text-[12.5px] font-semibold"
                    >
                      {a.name}
                      {a.role && <span className="font-normal text-ink-600">· {a.role}</span>}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {m.glossary && m.glossary.length > 0 && (
              <div className="mt-4 border-t border-line-soft pt-4">
                <div className="text-[12.5px] font-semibold text-ink-600">{t("glossary")}</div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {m.glossary.map((term) => (
                    <span
                      key={term}
                      className="rounded-full bg-brand-50 px-2.5 py-0.5 text-[13px] font-semibold text-brand-600"
                    >
                      {term}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>

          {meeting.data.has_transcript && (
            <section className="rounded-2xl border border-brand-200 bg-brand-25 p-5">
              <h2 className="text-sm font-bold">
                {meeting.data.has_summary ? t("minutes") : t("reviewTitle")}
              </h2>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-600">
                {meeting.data.has_summary ? t("minutesEditableNote") : t("reviewReady")}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Link
                  to={`/meetings/${m.id}/review`}
                  className={`rounded-full px-4 py-2 text-[13.5px] font-semibold ${
                    meeting.data.has_summary
                      ? "border border-line bg-surface hover:border-ink-200"
                      : "bg-brand-600 text-white hover:bg-brand-600/90"
                  }`}
                >
                  {t("actionReview")} →
                </Link>
                {meeting.data.has_summary && (
                  <>
                    <Link
                      to={`/meetings/${m.id}/minutes`}
                      className="rounded-full bg-ink-900 px-4 py-2 text-[13.5px] font-semibold text-surface hover:bg-ink-900/90"
                    >
                      {t("actionOpen")}
                    </Link>
                    <a
                      href={api.documentUrl(m.id)}
                      className="rounded-full border border-line bg-surface px-4 py-2 text-[13.5px] font-semibold hover:border-ink-200"
                    >
                      {t("downloadDocx")}
                    </a>
                  </>
                )}
              </div>
            </section>
          )}

          <section className="rounded-2xl border border-line bg-surface p-5">
            <h2 className="mb-3 text-sm font-bold">{t("listen")}</h2>
            <audio controls src={api.audioUrl(m.id)} className="w-full">
              <track kind="captions" />
            </audio>
          </section>
        </div>
      </div>
    </div>
  );
}
