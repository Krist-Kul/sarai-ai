/**
 * Transcript review -- the screen that decides whether the minutes are worth
 * anything.
 *
 * Three things make 1,300 rows workable: consecutive turns by one speaker are
 * grouped into a block, the speaker sidebar renames a voice once for the whole
 * transcript, and the player drives the list (click a block to seek, playback
 * scrolls the list). Everything autosaves.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { formatDuration, useI18n } from "../lib/i18n";
import { useDebouncedSave } from "../lib/useDebouncedSave";
import { EditableText } from "../components/EditableText";
import { Icon } from "../components/Icon";
import { StageBadge } from "../components/StageBadge";
import { StageTimeline } from "../components/StageTimeline";
import { BackLink, Button, Card, Notice } from "../components/ui";
import playIcon from "../assets/icons/play-40.svg";
import type { Segment } from "../types";

type Filter = "all" | "unnamed" | "low" | "edited";

const FILTER_LABEL = {
  all: "filterAll",
  unnamed: "filterUnnamed",
  low: "filterLowConfidence",
  edited: "filterEdited",
} as const;

const LOW_CONFIDENCE = 0.6;

/** First character for the avatar. Array spread so a Thai name starting with
 *  a combining mark still shows what was typed. */
function initial(label: string): string {
  return [...label.trim()][0] ?? "?";
}

function clock(seconds: number): string {
  return formatDuration(seconds);
}

export function ReviewPage() {
  const { id = "" } = useParams();
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const transcript = useQuery({
    queryKey: ["transcript", id],
    queryFn: () => api.getTranscript(id),
    refetchOnWindowFocus: false,
  });

  const meeting = useQuery({
    queryKey: ["meeting", id],
    queryFn: () => api.getMeeting(id),
    refetchOnWindowFocus: false,
  });
  const [segments, setSegments] = useState<Segment[]>([]);
  const [speakers, setSpeakers] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [editedIds, setEditedIds] = useState<Set<number>>(() => new Set());
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [follow, setFollow] = useState(true);

  const audio = useRef<HTMLAudioElement>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const loaded = useRef(false);

  // The server copy seeds local state once; after that the editor owns it and
  // refetching would throw away whatever the user is in the middle of typing.
  useEffect(() => {
    if (!transcript.data || loaded.current) return;
    setSegments(transcript.data.segments);
    setSpeakers(transcript.data.speakers);
    loaded.current = true;
  }, [transcript.data]);

  const saveTranscript = useDebouncedSave<Segment[]>(
    useCallback((next: Segment[]) => api.saveTranscript(id, next), [id]),
  );
  const saveSpeakers = useDebouncedSave<Record<string, string>>(
    useCallback((next: Record<string, string>) => api.saveSpeakers(id, next), [id]),
  );

  // Stamp the moment both saves settle, for the "autosaved · 14:32" line.
  const settled =
    saveTranscript.status !== "dirty" &&
    saveTranscript.status !== "saving" &&
    saveSpeakers.status !== "dirty" &&
    saveSpeakers.status !== "saving";
  const anySaved = saveTranscript.status === "saved" || saveSpeakers.status === "saved";
  useEffect(() => {
    if (settled && anySaved) setSavedAt(new Date());
  }, [settled, anySaved]);

  const generate = useMutation({
    mutationFn: async () => {
      saveTranscript.flush();
      saveSpeakers.flush();
      // A detected type is left to the worker; a type set at upload is kept.
      const m = meeting.data?.meeting;
      return api.summarize(id, m && !m.detect_type ? m.meeting_type : undefined);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["meeting", id] });
      void queryClient.invalidateQueries({ queryKey: ["meetings"] });
      navigate(`/meetings/${id}`);
    },
  });

  const updateSegment = (segmentId: number, text: string) => {
    const next = segments.map((s) => (s.id === segmentId ? { ...s, text } : s));
    setSegments(next);
    setEditedIds((prev) => new Set(prev).add(segmentId));
    saveTranscript.schedule(next);
  };

  const reassign = (segmentId: number, speaker: string) => {
    const next = segments.map((s) => (s.id === segmentId ? { ...s, speaker } : s));
    setSegments(next);
    setEditedIds((prev) => new Set(prev).add(segmentId));
    saveTranscript.schedule(next);
  };

  const renameSpeaker = (key: string, label: string) => {
    const next = { ...speakers, [key]: label };
    setSpeakers(next);
    saveSpeakers.schedule(next);
  };

  const speakerKeys = useMemo(
    () => [...new Set(segments.map((s) => s.speaker))].sort(),
    [segments],
  );

  const labelOf = useCallback(
    (speaker: string) => {
      const label = speakers[speaker];
      return label && label !== speaker ? label : speaker;
    },
    [speakers],
  );

  const turnsBySpeaker = useMemo(() => {
    const totals = new Map<string, number>();
    for (const seg of segments) totals.set(seg.speaker, (totals.get(seg.speaker) ?? 0) + 1);
    return totals;
  }, [segments]);

  const counts = useMemo(
    () => ({
      all: segments.length,
      unnamed: segments.filter((s) => !speakers[s.speaker] || speakers[s.speaker] === s.speaker)
        .length,
      low: segments.filter((s) => s.confidence != null && s.confidence < LOW_CONFIDENCE).length,
      edited: editedIds.size,
    }),
    [segments, speakers, editedIds],
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return segments.filter((s) => {
      if (filter === "unnamed" && speakers[s.speaker] && speakers[s.speaker] !== s.speaker)
        return false;
      if (filter === "low" && !(s.confidence != null && s.confidence < LOW_CONFIDENCE))
        return false;
      if (filter === "edited" && !editedIds.has(s.id)) return false;
      if (!needle) return true;
      return s.text.toLowerCase().includes(needle);
    });
  }, [segments, speakers, query, filter, editedIds]);

  const currentId = useMemo(() => {
    const active = segments.find((s) => position >= s.start && position < s.end);
    return active?.id ?? null;
  }, [segments, position]);

  // Follow playback: keep the segment being spoken on screen.
  useEffect(() => {
    if (!follow || currentId == null) return;
    document
      .getElementById(`seg-${currentId}`)
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [currentId, follow]);

  const seek = (seconds: number) => {
    const el = audio.current;
    if (!el) return;
    el.currentTime = seconds;
    void el.play();
  };

  const togglePlay = useCallback(() => {
    const el = audio.current;
    if (!el) return;
    if (el.paused) void el.play();
    else el.pause();
  }, []);

  // Space plays and pauses -- unless the user is typing in the transcript,
  // where a space is a space.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing =
        target?.tagName === "TEXTAREA" || target?.tagName === "INPUT" || target?.isContentEditable;
      if (e.code === "Space" && !typing) {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePlay]);

  if (transcript.isPending) return <p className="text-small text-ink-muted">{t("loading")}</p>;
  if (transcript.isError) {
    const message =
      transcript.error instanceof ApiError ? transcript.error.message : String(transcript.error);
    return (
      <div className="flex flex-col gap-4">
        <BackLink to={`/meetings/${id}`}>{t("back")}</BackLink>
        <Notice tone="danger" inline>
          <span className="font-semibold">{t("errorTitle")}</span> — {message}
        </Notice>
      </div>
    );
  }

  const m = meeting.data?.meeting;
  const stage = meeting.data?.stage ?? "awaiting_review";
  const saveError = saveTranscript.error ?? saveSpeakers.error;
  const duration = segments.at(-1)?.end ?? 0;

  return (
    <div className="flex flex-col gap-6 pb-24">
      <BackLink to="/">{t("allMeetings")}</BackLink>

      <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="text-eyebrow text-brand-ink">STEP 03 · REVIEW</p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="min-w-0 text-[24px] leading-[34px] font-semibold tracking-[-0.3px] break-words sm:text-display">
              {m?.title ?? t("reviewTitle")}
            </h1>
            <StageBadge stage={stage} />
          </div>
          <p className="truncate text-data text-ink-muted">
            {[
              m?.meeting_date,
              formatDuration(m?.duration_sec ?? duration),
              t("speakerCount", { n: speakerKeys.length }),
              t("turnCount", { n: segments.length }),
              m?.source_file,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Button variant="outline" onClick={togglePlay}>
            {playing ? t("pause") : t("listen")}
          </Button>
          <Button
            icon="arrow-right"
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
            className="shadow-glow"
          >
            {generate.isPending ? t("submitting") : t("generateMinutes")}
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-3 rounded-md border border-brand bg-brand-soft px-[18px] py-3 text-small-strong text-brand-ink">
        <Icon name="pencil-18" />
        <p className="min-w-0">{t("reviewReady")}</p>
      </div>

      {generate.isError && (
        <Notice tone="danger" inline>
          {generate.error instanceof ApiError ? generate.error.message : String(generate.error)}
        </Notice>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[320px_1fr]">
        <aside className="flex flex-col gap-4 lg:sticky lg:top-24">
          <Card className="flex flex-col gap-3.5 p-6">
            <p className="text-eyebrow text-ink-subtle">PIPELINE</p>
            <StageTimeline stage={stage} />
          </Card>

          <Card className="flex flex-col gap-2.5 p-6">
            <p className="text-eyebrow text-ink-subtle">SPEAKERS · {speakerKeys.length}</p>
            <p className="text-small text-ink-muted">{t("speakersHint")}</p>
            {speakerKeys.map((key) => {
              const named = Boolean(speakers[key] && speakers[key] !== key);
              return (
                <label
                  key={key}
                  className={`flex items-center gap-2.5 rounded-md py-1.5 pr-2.5 pl-2 focus-within:bg-surface-raised ${
                    named
                      ? "border border-transparent hover:bg-surface-raised"
                      : "border border-dashed border-line-control bg-surface-raised"
                  }`}
                >
                  <span
                    aria-hidden
                    className="flex size-7 shrink-0 items-center justify-center rounded-[14px] bg-brand-soft text-[12.5px] font-bold text-brand-ink"
                  >
                    {named ? initial(speakers[key] ?? "") : "?"}
                  </span>
                  <input
                    value={named ? (speakers[key] ?? "") : ""}
                    onChange={(e) => renameSpeaker(key, e.target.value)}
                    onBlur={() => saveSpeakers.flush()}
                    placeholder={t("nameThisSpeaker")}
                    aria-label={`${t("speakers")} ${key}`}
                    className="min-w-0 flex-1 border-0 bg-transparent text-small-strong text-ink outline-none placeholder:font-normal placeholder:text-ink-subtle"
                  />
                  <span className="shrink-0 text-data text-ink-subtle">
                    {turnsBySpeaker.get(key) ?? 0}
                  </span>
                </label>
              );
            })}
          </Card>
        </aside>

        <Card as="section" className="min-w-0 overflow-hidden">
          <div className="flex flex-wrap items-center gap-2.5 border-b border-line py-4 pr-5 pl-6">
            <h2 className="flex-1 text-[20px] leading-[30px] font-semibold tracking-[-0.1px]">
              {t("reviewTitle")}
            </h2>
            <span className="text-small text-ink-subtle">
              {saveError ? (
                <span className="text-danger">{t("saveFailed")}</span>
              ) : saveTranscript.status === "saving" || saveSpeakers.status === "saving" ? (
                t("saving")
              ) : saveTranscript.status === "dirty" || saveSpeakers.status === "dirty" ? (
                t("unsaved")
              ) : savedAt ? (
                `${t("autosaved")} · ${savedAt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`
              ) : (
                t("autosaved")
              )}
            </span>
            <div role="tablist" className="flex gap-[3px] rounded-full border border-line bg-surface-raised p-[3px]">
              {(Object.keys(FILTER_LABEL) as Filter[])
                .filter((value) => value === "all" || value === filter || counts[value] > 0)
                .map((value) => (
                  <button
                    key={value}
                    type="button"
                    role="tab"
                    aria-selected={filter === value}
                    onClick={() => setFilter(value)}
                    className={`cursor-pointer rounded-full px-3 py-1 text-small-strong whitespace-nowrap ${
                      filter === value ? "bg-ink text-on-ink" : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    {t(FILTER_LABEL[value])}
                    {value !== "all" && ` · ${counts[value]}`}
                  </button>
                ))}
            </div>
            <div className="flex w-full items-center gap-2">
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("searchTranscript")}
                className="h-8 min-w-0 flex-1 rounded-full border border-line bg-surface px-3.5 text-small outline-none placeholder:text-ink-subtle focus:border-brand"
              />
              <button
                type="button"
                aria-pressed={follow}
                onClick={() => setFollow((f) => !f)}
                className={`flex h-8 cursor-pointer items-center gap-1.5 rounded-full px-3 text-small-strong ${
                  follow ? "bg-brand-soft text-brand-ink" : "text-ink-muted hover:text-ink"
                }`}
              >
                {follow && <Icon name="check-14" />}
                {t("followPlayback")}
              </button>
            </div>
          </div>

          {visible.length === 0 ? (
            <p className="px-6 py-12 text-center text-small text-ink-muted">{t("noMatches")}</p>
          ) : (
            <ol className="flex flex-col px-4 pt-2 pb-4 sm:px-6">
              {visible.map((segment) => {
                const named = Boolean(speakers[segment.speaker] && speakers[segment.speaker] !== segment.speaker);
                const low = segment.confidence != null && segment.confidence < LOW_CONFIDENCE;
                return (
                  <li
                    key={segment.id}
                    id={`seg-${segment.id}`}
                    className={`flex flex-col gap-1 border-b border-line py-2 last:border-b-0 sm:flex-row sm:gap-3 ${
                      currentId === segment.id ? "bg-brand-soft/60" : ""
                    }`}
                  >
                    <div className="flex shrink-0 items-baseline gap-2 pt-0.5 text-[13px] sm:w-28 sm:flex-col sm:gap-0">
                      <select
                        value={segment.speaker}
                        onChange={(e) => reassign(segment.id, e.target.value)}
                        aria-label={t("reassignSpeaker")}
                        title={t("reassignSpeaker")}
                        className={`max-w-full cursor-pointer appearance-none truncate border-0 bg-transparent p-0 leading-[26px] font-semibold outline-none hover:underline ${
                          named ? "text-brand-ink" : "text-ink-subtle"
                        }`}
                      >
                        {speakerKeys.map((key) => (
                          <option key={key} value={key}>
                            {labelOf(key)}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => seek(segment.start)}
                        className="w-fit cursor-pointer font-mono leading-5 text-ink-subtle hover:text-brand-ink"
                      >
                        {clock(segment.start)}
                      </button>
                    </div>
                    <div className="min-w-0 flex-1">
                      <EditableText
                        value={segment.text}
                        onChange={(text) => updateSegment(segment.id, text)}
                        onCommit={() => saveTranscript.flush()}
                        onFocus={() => seek(segment.start)}
                        ariaLabel={`${clock(segment.start)} ${labelOf(segment.speaker)}`}
                        className="text-[16px] leading-[28px]"
                      />
                      {low && (
                        <p className="px-2 text-small text-live">
                          {t("lowConfidenceHint", {
                            n: Math.round((segment.confidence ?? 0) * 100),
                          })}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </Card>
      </div>

      {/* Player, pinned: the transcript is read against the audio, not instead of it. */}
      <div className="fixed inset-x-0 bottom-0 z-10 border-t border-line bg-surface/80 backdrop-blur-[16px]">
        <div className="mx-auto flex max-w-[1152px] items-center gap-3 px-4 py-2.5 sm:px-6">
          <button
            type="button"
            onClick={togglePlay}
            aria-label={playing ? t("pause") : t("play")}
            className="size-10 shrink-0 cursor-pointer rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            {playing ? (
              <span className="flex size-10 items-center justify-center gap-1 rounded-full bg-ink">
                <span className="h-3.5 w-[3px] rounded-[1px] bg-on-ink" />
                <span className="h-3.5 w-[3px] rounded-[1px] bg-on-ink" />
              </span>
            ) : (
              <img src={playIcon} alt="" width={40} height={40} className="dark-invert" />
            )}
          </button>
          <span className="shrink-0 text-data text-ink-muted">
            {clock(position)} / {clock(duration)}
          </span>
          <input
            type="range"
            min={0}
            max={Math.max(1, duration)}
            step={0.5}
            value={position}
            onChange={(e) => seek(Number(e.target.value))}
            aria-label={t("seek")}
            className="h-1.5 min-w-0 flex-1 accent-brand"
          />
          <audio
            ref={audio}
            src={api.audioUrl(id)}
            onTimeUpdate={(e) => setPosition(e.currentTarget.currentTime)}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            className="hidden"
          >
            <track kind="captions" />
          </audio>
          <span className="hidden text-small text-ink-subtle md:inline">{t("spaceToPlay")}</span>
        </div>
      </div>
    </div>
  );
}
