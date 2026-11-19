import { useParams } from "react-router-dom";
import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { formatDuration, formatIsoDateTime, useI18n } from "../lib/i18n";
import { MEETING_TYPES } from "../lib/meetingType";
import { stageKind, type StageKind } from "../lib/stage";
import { useElapsed, useJobEvents } from "../lib/useJobEvents";
import { StageBadge } from "../components/StageBadge";
import { StageTimeline } from "../components/StageTimeline";
import { AudioPlayer } from "../components/AudioPlayer";
import { Icon } from "../components/Icon";
import { BackLink, Button, ButtonLink, buttonClass, Card, Notice } from "../components/ui";
import type { Stage } from "../types";

// Must match sarai.models.CANCELLED_ERROR.
const CANCELLED_ERROR = "Cancelled by user";

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
  const { t } = useI18n();
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
  const cancelled = stage === "failed" && error === CANCELLED_ERROR;

  // Two clicks to stop: an hour of transcription is too much to lose to a slip.
  const [confirmStop, setConfirmStop] = useState(false);
  useEffect(() => {
    if (!running) setConfirmStop(false);
  }, [running]);
  const stop = useMutation({
    mutationFn: (job: string) => api.cancelJob(job),
    onSettled: () => {
      setConfirmStop(false);
      void queryClient.invalidateQueries({ queryKey: ["meeting", id] });
      void queryClient.invalidateQueries({ queryKey: ["meetings"] });
    },
  });
  const elapsed = useElapsed(meeting.data?.meeting.created_at, running);
  streamLost.current = running && status === "lost";

  if (meeting.isPending) return <p className="text-small text-ink-muted">{t("loading")}</p>;
  if (meeting.isError) {
    const message =
      meeting.error instanceof ApiError ? meeting.error.message : String(meeting.error);
    return (
      <Notice tone="danger" inline>
        <span className="font-semibold">{t("errorTitle")}</span> — {message}
      </Notice>
    );
  }

  const m = meeting.data.meeting;
  const kind = stageKind(stage);
  const percent = Math.round(progress * 100);
  const step = stepOf(stage);
  // A straight-line estimate; only shown once there is enough progress for it
  // to mean something.
  const remaining =
    running && elapsed != null && progress > 0.05 ? (elapsed / progress) * (1 - progress) : null;
  const typeLabel = m.detect_type
    ? "—"
    : t(MEETING_TYPES.find((o) => o.value === m.meeting_type)?.key ?? "typeGeneral");

  return (
    <div className="flex flex-col gap-6">
      <BackLink to="/">{t("allMeetings")}</BackLink>

      <div className="flex flex-col gap-1">
        <p className={`text-eyebrow ${STEP_TONE[kind]}`}>{step}</p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="min-w-0 text-[24px] leading-[34px] font-semibold tracking-[-0.3px] break-words sm:text-display">
            {m.title}
          </h1>
          <StageBadge stage={stage} />
        </div>
        <p className="truncate text-data text-ink-muted">
          {m.source_file} · {formatDuration(m.duration_sec)} · 16 kHz mono
        </p>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[380px_1fr]">
        <div className="flex flex-col gap-4">
          <Card as="section" className="flex flex-col gap-4 p-5 sm:p-6">
            <div className="flex flex-wrap items-baseline gap-x-2.5">
              <span className="font-mono text-[44px] leading-[52px] font-semibold tracking-[-1.76px]">
                {percent}%
              </span>
              {detail && <span className="text-data text-ink-muted">{detail}</span>}
            </div>
            <div className="h-2 overflow-hidden rounded-[4px] bg-surface-raised">
              <div
                className={`h-full rounded-[4px] transition-[width] duration-500 ${
                  kind === "failed" ? "bg-danger" : kind === "done" ? "bg-done" : ""
                }`}
                style={{
                  width: `${percent}%`,
                  backgroundImage:
                    kind === "failed" || kind === "done"
                      ? undefined
                      : "linear-gradient(90deg, #4f46e5, #06b6d4)",
                }}
              />
            </div>
            <dl className="flex gap-4">
              <div className="min-w-0 flex-1">
                <dt className="text-small text-ink-muted">{running ? t("elapsed") : t("created")}</dt>
                <dd className="font-mono text-[15px] leading-5 text-ink">
                  {running ? formatDuration(elapsed) : formatIsoDateTime(m.created_at)}
                </dd>
              </div>
              {remaining != null && (
                <div className="min-w-0 flex-1">
                  <dt className="text-small text-ink-muted">{t("eta")}</dt>
                  <dd className="font-mono text-[15px] leading-5 text-ink">
                    ~{formatDuration(remaining)}
                  </dd>
                </div>
              )}
            </dl>
            <hr className="border-line" />

            <StageTimeline stage={stage} detail={detail} />

            <div className="flex flex-wrap items-center gap-2 pt-1 text-small text-ink-muted">
              {running && status === "live" && (
                <span className="flex flex-1 items-center gap-2">
                  <span className="size-2 rounded-full bg-done" aria-hidden />
                  {t("liveLive")}
                </span>
              )}
              {running && status === "connecting" && (
                <span className="flex-1">{t("liveConnecting")}</span>
              )}
              {running && status === "lost" && (
                <span className="flex-1 text-live">{t("liveLost")}</span>
              )}
              {stage === "queued" && (
                <span className="flex-1">
                  {/* A failed attempt goes back to `queued`; say so, or a job that
                      fails every time looks like it is merely waiting its turn. */}
                  {detail?.startsWith("retrying after error")
                    ? `${t("retryingNote")} ${detail}`
                    : t("queuedNote")}
                </span>
              )}
              {stage === "awaiting_review" && <span className="flex-1">{t("readyNote")}</span>}
              {stage === "failed" && (
                <span className="flex-1 text-danger">
                  {t(cancelled ? "cancelledNote" : "failedNote")}
                </span>
              )}
              {running && jobId && (
                <span className="ml-auto flex items-center gap-1">
                  {confirmStop && !stop.isPending && (
                    <Button variant="ghost" size="sm" onClick={() => setConfirmStop(false)}>
                      {t("stopJobCancel")}
                    </Button>
                  )}
                  <Button
                    variant={confirmStop ? "danger" : "ghost"}
                    size="sm"
                    disabled={stop.isPending}
                    onClick={() => (confirmStop ? stop.mutate(jobId) : setConfirmStop(true))}
                    className={confirmStop ? "" : "text-danger hover:bg-danger-soft hover:text-danger"}
                  >
                    {stop.isPending
                      ? t("stoppingJob")
                      : confirmStop
                        ? t("stopJobConfirm")
                        : t("stopJob")}
                  </Button>
                </span>
              )}
            </div>

            {stop.error && (
              <Notice tone="danger" inline>
                {stop.error instanceof ApiError ? stop.error.message : String(stop.error)}
              </Notice>
            )}
            {error && !cancelled && (
              <Notice tone="danger" inline>
                {error}
              </Notice>
            )}
          </Card>

          {running && (
            <div className="flex gap-3 rounded-lg bg-brand-soft px-5 py-4">
              <Icon name="sparkle-20" className="text-brand-ink" />
              <div className="flex min-w-0 flex-col gap-0.5">
                <p className="text-small-strong text-brand-ink">{t("nextUp")}</p>
                <p className="text-small text-ink-muted">
                  {t(
                    stage === "summarizing" || stage === "rendering"
                      ? "nextUpMinutes"
                      : m.auto_summarize
                        ? "nextUpAuto"
                        : "nextUpReview",
                  )}
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Card as="section" className="flex flex-col gap-5 p-5 sm:p-6">
            <dl className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
              <Fact label={t("date")} value={m.meeting_date ?? "—"} />
              <Fact label={t("duration")} value={formatDuration(m.duration_sec)} mono />
              <Fact label={t("meetingType")} value={typeLabel} />
              <Fact label={t("created")} value={formatIsoDateTime(m.created_at).slice(0, 10)} mono />
            </dl>

            {m.attendees && m.attendees.length > 0 && (
              <div className="flex flex-col gap-2">
                <h2 className="text-small-strong text-ink">{t("attendees")}</h2>
                <ul className="flex flex-wrap gap-2">
                  {m.attendees.map((a) => (
                    <li
                      key={a.name}
                      className="flex items-center gap-2 rounded-full border border-line bg-surface py-1 pr-3 pl-1"
                    >
                      <span
                        aria-hidden
                        className="flex size-7 items-center justify-center rounded-[14px] bg-brand-soft text-[12.5px] font-bold text-brand-ink"
                      >
                        {[...a.name.trim()][0] ?? "?"}
                      </span>
                      <span className="text-small-strong text-ink">{a.name}</span>
                      {a.role && <span className="text-small text-ink-muted">{a.role}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {m.glossary && m.glossary.length > 0 && (
              <div className="flex flex-col gap-2">
                <h2 className="text-small-strong text-ink">{t("glossary")}</h2>
                <ul className="flex flex-wrap gap-2">
                  {m.glossary.map((term) => (
                    <li
                      key={term}
                      className="rounded-full bg-brand-soft py-[3px] pr-3 pl-2.5 text-small-strong text-brand-ink"
                    >
                      {term}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          {meeting.data.has_transcript && (
            <Card
              as="section"
              className={`flex flex-col gap-3 p-5 sm:p-6 ${
                meeting.data.has_summary ? "" : "border-brand shadow-glow"
              }`}
            >
              <h2 className="text-[20px] leading-[30px] font-semibold tracking-[-0.1px]">
                {meeting.data.has_summary ? t("minutes") : t("reviewTitle")}
              </h2>
              <p className="text-small text-ink-muted">
                {meeting.data.has_summary ? t("minutesEditableNote") : t("reviewReady")}
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                {meeting.data.has_summary ? (
                  <>
                    <ButtonLink to={`/meetings/${m.id}/minutes`} variant="solid">
                      {t("actionOpen")}
                    </ButtonLink>
                    <a href={api.pdfUrl(m.id)} className={buttonClass("primary")}>
                      {t("downloadPdf")}
                    </a>
                    <a href={api.documentUrl(m.id)} className={buttonClass("outline")}>
                      {t("downloadDocx")}
                    </a>
                    <ButtonLink to={`/meetings/${m.id}/review`} variant="ghost">
                      {t("actionReview")}
                    </ButtonLink>
                  </>
                ) : (
                  <ButtonLink to={`/meetings/${m.id}/review`} icon="arrow-right">
                    {t("actionReview")}
                  </ButtonLink>
                )}
              </div>
            </Card>
          )}

          {meeting.data.has_transcript && <LatestTranscript id={m.id} />}

          <Card as="section" className="p-5">
            <AudioPlayer src={api.audioUrl(m.id)} duration={m.duration_sec} />
          </Card>
        </div>
      </div>
    </div>
  );
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-md bg-surface-raised px-4 py-3">
      <dt className="truncate text-small text-ink-muted">{label}</dt>
      <dd
        className={`truncate leading-[28px] text-ink ${
          mono ? "font-mono text-[15px] font-medium" : "text-[16px] font-semibold"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}

/** The last few turns, so the page shows what was actually heard. */
function LatestTranscript({ id }: { id: string }) {
  const { t } = useI18n();
  const transcript = useQuery({ queryKey: ["transcript", id], queryFn: () => api.getTranscript(id) });
  const turns = transcript.data?.segments.slice(-3) ?? [];
  if (turns.length === 0) return null;
  const names = transcript.data?.speakers ?? {};
  return (
    <Card as="section" className="flex flex-col gap-3 p-5 sm:p-6">
      <div className="flex items-center gap-2.5">
        <h2 className="flex-1 text-[20px] leading-[30px] font-semibold tracking-[-0.1px]">
          {t("latestTranscript")}
        </h2>
        <ButtonLink to={`/meetings/${id}/review`} variant="outline" size="sm">
          {t("openTranscript")}
        </ButtonLink>
      </div>
      {turns.map((seg) => (
        <div key={seg.id} className="flex flex-col gap-1 py-2 sm:flex-row sm:gap-4">
          <div className="flex shrink-0 gap-2 text-data sm:w-28 sm:flex-col sm:gap-0">
            <span className="truncate text-brand-ink">{names[seg.speaker] ?? seg.speaker}</span>
            <span className="text-ink-subtle">{formatDuration(seg.start)}</span>
          </div>
          <p className="min-w-0 flex-1 text-[16px] leading-[28px] text-ink">{seg.text}</p>
        </div>
      ))}
    </Card>
  );
}

/** Pipeline step shown above the title. */
function stepOf(stage: Stage | null | undefined): string {
  if (stage === "awaiting_review") return "STEP 03 · REVIEW";
  if (stage === "summarizing" || stage === "rendering" || stage === "done")
    return "STEP 04 · MINUTES";
  if (stage === "failed") return "FAILED";
  return "STEP 02 · TRANSCRIBE";
}

const STEP_TONE: Record<StageKind, string> = {
  queued: "text-ink-subtle",
  running: "text-live",
  review: "text-brand-ink",
  done: "text-done",
  failed: "text-danger",
};
