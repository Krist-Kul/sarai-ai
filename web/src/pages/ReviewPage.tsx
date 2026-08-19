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
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { formatDuration, useI18n } from "../lib/i18n";
import { useDebouncedSave } from "../lib/useDebouncedSave";
import { EditableText } from "../components/EditableText";
import type { Segment } from "../types";

type Filter = "all" | "unnamed" | "low" | "edited";

const LOW_CONFIDENCE = 0.6;

/** Palette for speaker dots and avatars, in the order speakers first appear. */
type Tone = { dot: string; avatar: string; rail: string };

const FIRST_TONE: Tone = { dot: "bg-brand-600", avatar: "bg-brand-600", rail: "bg-brand-50" };

const SPEAKER_TONE: Tone[] = [
  FIRST_TONE,
  { dot: "bg-warn-600", avatar: "bg-warn-600", rail: "bg-warn-100" },
  { dot: "bg-ok-600", avatar: "bg-ok-600", rail: "bg-ok-50" },
  { dot: "bg-bad-600", avatar: "bg-bad-600", rail: "bg-bad-50" },
  { dot: "bg-ink-600", avatar: "bg-ink-600", rail: "bg-sand" },
];

type Block = { key: string; speaker: string; segments: Segment[] };

/** Consecutive segments from one speaker read as one turn, not fifty rows. */
function toBlocks(segments: Segment[]): Block[] {
  const blocks: Block[] = [];
  for (const segment of segments) {
    const last = blocks[blocks.length - 1];
    if (last && last.speaker === segment.speaker) last.segments.push(segment);
    else blocks.push({ key: `b${segment.id}`, speaker: segment.speaker, segments: [segment] });
  }
  return blocks;
}

function initials(label: string): string {
  const trimmed = label.trim();
  if (!trimmed) return "?";
  // Thai names have no spaces to split on, so take the first characters.
  return [...trimmed].slice(0, 2).join("");
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

  const [segments, setSegments] = useState<Segment[]>([]);
  const [speakers, setSpeakers] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [editedIds, setEditedIds] = useState<Set<number>>(() => new Set());
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [follow, setFollow] = useState(true);

  const audio = useRef<HTMLAudioElement>(null);
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

  const generate = useMutation({
    mutationFn: async () => {
      saveTranscript.flush();
      saveSpeakers.flush();
      return api.summarize(id);
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

  const toneOf = useCallback(
    (speaker: string): Tone => {
      const index = speakerKeys.indexOf(speaker);
      return SPEAKER_TONE[Math.max(0, index) % SPEAKER_TONE.length] ?? FIRST_TONE;
    },
    [speakerKeys],
  );

  const labelOf = useCallback(
    (speaker: string) => {
      const label = speakers[speaker];
      return label && label !== speaker ? label : speaker;
    },
    [speakers],
  );

  /** Share of speaking time, which is how you tell a chair from a backchannel. */
  const share = useMemo(() => {
    const totals = new Map<string, number>();
    let all = 0;
    for (const s of segments) {
      const duration = Math.max(0, s.end - s.start);
      totals.set(s.speaker, (totals.get(s.speaker) ?? 0) + duration);
      all += duration;
    }
    return { totals, all };
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

  const blocks = useMemo(() => toBlocks(visible), [visible]);

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

  if (transcript.isPending) return <p className="text-ink-600">{t("loading")}</p>;
  if (transcript.isError) {
    const message =
      transcript.error instanceof ApiError ? transcript.error.message : String(transcript.error);
    return (
      <div className="rounded-2xl border border-bad-line bg-bad-50 p-4 text-bad-600">
        <p className="font-semibold">{t("errorTitle")}</p>
        <p className="mt-1 text-sm">{message}</p>
        <Link to={`/meetings/${id}`} className="mt-3 inline-block text-sm underline">
          {t("back")}
        </Link>
      </div>
    );
  }

  const saving = saveTranscript.status === "saving" || saveSpeakers.status === "saving";
  const dirty = saveTranscript.status === "dirty" || saveSpeakers.status === "dirty";
  const saveError = saveTranscript.error ?? saveSpeakers.error;
  const duration = segments.at(-1)?.end ?? 0;

  return (
    <div className="pb-28">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Link to={`/meetings/${id}`} className="text-sm text-ink-600 hover:text-ink-900">
          ← {t("back")}
        </Link>
        <h1 className="text-xl font-bold tracking-tight">{t("reviewTitle")}</h1>
        <span className="text-[12.5px] text-ink-600">
          {t("segmentCount", { n: segments.length })}
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 text-[12.5px]">
          {saveError ? (
            <span className="text-bad-600">{t("saveFailed")}</span>
          ) : saving ? (
            <span className="text-ink-600">{t("saving")}</span>
          ) : dirty ? (
            <span className="text-ink-400">{t("unsaved")}</span>
          ) : (
            <>
              <span className="size-1.5 rounded-full bg-ok-600" aria-hidden />
              <span className="text-ok-600">{t("allSaved")}</span>
            </>
          )}
        </span>
        <button
          type="button"
          onClick={() => generate.mutate()}
          disabled={generate.isPending}
          className="rounded-full bg-brand-600 px-4 py-2 text-[13.5px] font-bold text-white hover:bg-brand-600/90 disabled:bg-ink-200"
        >
          {generate.isPending ? t("submitting") : `${t("generateMinutes")} →`}
        </button>
      </div>

      {generate.isError && (
        <div className="mb-4 rounded-xl border border-bad-line bg-bad-50 p-3 text-sm text-bad-600">
          {generate.error instanceof ApiError
            ? generate.error.message
            : String(generate.error)}
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="flex min-w-0 items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-2 text-[13px]">
          <span aria-hidden className="text-ink-400">
            ⌕
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("searchTranscript")}
            className="w-40 min-w-0 border-0 bg-transparent outline-none placeholder:text-ink-400 sm:w-64"
          />
        </label>
        {(
          [
            ["all", t("filterAll"), counts.all],
            ["unnamed", t("filterUnnamed"), counts.unnamed],
            ["low", t("filterLowConfidence"), counts.low],
            ["edited", t("filterEdited"), counts.edited],
          ] as const
        ).map(([value, label, count]) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={`rounded-full px-3 py-1.5 text-[12.5px] font-semibold ${
              filter === value
                ? "bg-ink-900 text-surface"
                : "border border-line bg-surface text-ink-600 hover:border-ink-200"
            }`}
          >
            {label} · {count}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setFollow((f) => !f)}
          className={`ml-auto rounded-full px-3 py-1.5 text-[12.5px] font-semibold ${
            follow ? "bg-brand-50 text-brand-600" : "border border-line bg-surface text-ink-600"
          }`}
        >
          {t("followPlayback")} {follow ? "✓" : ""}
        </button>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[280px_1fr]">
        <aside className="rounded-2xl border border-line bg-surface p-4 lg:sticky lg:top-4">
          <h2 className="text-sm font-bold">{t("speakers")}</h2>
          <p className="mt-0.5 mb-3 text-xs text-ink-600">{t("speakersHint")}</p>
          <div className="flex flex-col gap-2.5">
            {speakerKeys.map((key) => {
              const seconds = share.totals.get(key) ?? 0;
              const percent = share.all > 0 ? (seconds / share.all) * 100 : 0;
              const named = speakers[key] && speakers[key] !== key;
              return (
                <div key={key} className="flex items-center gap-2.5">
                  <span
                    className={`size-2.5 flex-none rounded-full ${toneOf(key).dot}`}
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <input
                      value={speakers[key] === key ? "" : (speakers[key] ?? "")}
                      onChange={(e) => renameSpeaker(key, e.target.value)}
                      onBlur={() => saveSpeakers.flush()}
                      placeholder={t("nameThisSpeaker")}
                      aria-label={`${t("speakers")} ${key}`}
                      className={`w-full rounded-[9px] border px-2.5 py-1.5 text-[13.5px] outline-none focus:border-brand-600 ${
                        named ? "border-line bg-surface" : "border-brand-200 bg-brand-25"
                      }`}
                    />
                    <div className="mt-1 flex items-center gap-1.5">
                      <span className="h-1 flex-1 overflow-hidden rounded-full bg-sand">
                        <span
                          className={`block h-full rounded-full ${toneOf(key).dot}`}
                          style={{ width: `${percent}%` }}
                        />
                      </span>
                      <span className="text-[11px] tabular-nums text-ink-400">
                        {percent.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </aside>

        <section className="min-w-0">
          {blocks.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-line bg-surface px-6 py-12 text-center text-sm text-ink-600">
              {t("noMatches")}
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {blocks.map((block) => {
                const tone = toneOf(block.speaker);
                const start = block.segments[0]?.start ?? 0;
                const end = block.segments.at(-1)?.end ?? start;
                return (
                  <article
                    key={block.key}
                    className="flex gap-3.5 rounded-2xl border border-line bg-surface p-4"
                  >
                    <div className="flex w-8 flex-none flex-col items-center gap-1.5">
                      <span
                        className={`flex size-8 items-center justify-center rounded-full text-[12.5px] font-bold text-white ${tone.avatar}`}
                        aria-hidden
                      >
                        {initials(labelOf(block.speaker))}
                      </span>
                      <span className={`w-0.5 flex-1 rounded-full ${tone.rail}`} aria-hidden />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span className="text-[13.5px] font-bold">{labelOf(block.speaker)}</span>
                        <button
                          type="button"
                          onClick={() => seek(start)}
                          className="font-mono text-xs text-ink-400 hover:text-brand-600"
                        >
                          {clock(start)} → {clock(end)}
                        </button>
                        <select
                          value={block.speaker}
                          onChange={(e) =>
                            block.segments.forEach((s) => reassign(s.id, e.target.value))
                          }
                          aria-label={t("reassignSpeaker")}
                          className="ml-auto rounded-full border border-line bg-surface px-2 py-0.5 text-xs text-ink-600"
                        >
                          {speakerKeys.map((key) => (
                            <option key={key} value={key}>
                              {labelOf(key)}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="mt-1.5 flex flex-col gap-1.5">
                        {block.segments.map((segment) => {
                          const low =
                            segment.confidence != null && segment.confidence < LOW_CONFIDENCE;
                          return (
                            <div
                              key={segment.id}
                              id={`seg-${segment.id}`}
                              className={`rounded-xl px-2 py-1 ${
                                currentId === segment.id ? "bg-brand-50" : ""
                              }`}
                            >
                              <EditableText
                                value={segment.text}
                                onChange={(text) => updateSegment(segment.id, text)}
                                onCommit={() => saveTranscript.flush()}
                                onFocus={() => seek(segment.start)}
                                ariaLabel={`${clock(segment.start)} ${labelOf(segment.speaker)}`}
                                className="text-[15px] leading-[1.85]"
                              />
                              {low && (
                                <p className="px-0.5 text-[12px] text-warn-600">
                                  {t("lowConfidenceHint", {
                                    n: Math.round((segment.confidence ?? 0) * 100),
                                  })}
                                </p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {/* Player, pinned: the transcript is read against the audio, not instead of it. */}
      <div className="fixed inset-x-0 bottom-0 border-t border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-2.5 sm:px-6">
          <button
            type="button"
            onClick={togglePlay}
            aria-label={playing ? t("pause") : t("play")}
            className="flex size-9 flex-none items-center justify-center rounded-full bg-brand-600 text-sm text-white"
          >
            {playing ? "❚❚" : "▶"}
          </button>
          <span className="flex-none font-mono text-[12.5px] tabular-nums text-ink-600">
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
            className="h-1.5 flex-1 accent-brand-600"
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
          <span className="hidden text-[12px] text-ink-400 sm:inline">{t("spaceToPlay")}</span>
        </div>
      </div>
    </div>
  );
}
