import { useEffect, useRef, useState } from "react";

import playIcon from "../assets/icons/play-40.svg";
import { useI18n } from "../lib/i18n";

/** Decorative waveform from the design; the played share turns brand. */
const BARS = [
  8, 14, 20, 12, 24, 18, 10, 22, 16, 26, 12, 8, 18, 24, 14, 10, 20, 16, 22, 12, 8, 16, 24, 18, 12,
  20, 14, 10, 22, 16, 12, 18, 24, 14, 8, 20, 16, 12, 22, 18, 10, 14, 20, 12, 8, 16, 22, 18, 12, 10,
  16, 20, 14, 8, 12,
];

function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const pad = (n: number) => String(n).padStart(2, "0");
  const h = Math.floor(s / 3600);
  return h > 0
    ? `${h}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`
    : `${pad(Math.floor(s / 60))}:${pad(s % 60)}`;
}

export function AudioPlayer({ src, duration }: { src: string; duration?: number | null }) {
  const { t } = useI18n();
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [total, setTotal] = useState(duration ?? 0);

  useEffect(() => {
    const el = audio.current;
    if (!el) return;
    const onTime = () => setTime(el.currentTime);
    const onMeta = () => Number.isFinite(el.duration) && setTotal(el.duration);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
    };
  }, []);

  const fraction = total > 0 ? time / total : 0;
  const seek = (value: number) => {
    if (audio.current && total > 0) audio.current.currentTime = value * total;
  };

  return (
    <div className="flex items-center gap-4">
      <audio ref={audio} src={src} preload="metadata" />
      <button
        type="button"
        aria-label={playing ? t("pause") : t("play")}
        onClick={() => (playing ? audio.current?.pause() : void audio.current?.play())}
        className="relative size-10 shrink-0 cursor-pointer rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        {playing ? (
          <span className="flex size-10 items-center justify-center gap-1 rounded-full bg-ink">
            <span className="h-3.5 w-[3px] rounded-[1px] bg-on-ink" />
            <span className="h-3.5 w-[3px] rounded-[1px] bg-on-ink" />
          </span>
        ) : (
          // The exported glyph is ink-on-white; invert keeps it ink-coloured in
          // the dark theme without redrawing it.
          <img src={playIcon} alt="" width={40} height={40} className="dark-invert" />
        )}
      </button>
      <div
        role="slider"
        tabIndex={0}
        aria-label={t("listen")}
        aria-valuemin={0}
        aria-valuemax={Math.round(total)}
        aria-valuenow={Math.round(time)}
        aria-valuetext={`${clock(time)} / ${clock(total)}`}
        onClick={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          seek((e.clientX - box.left) / box.width);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") seek(Math.min(1, fraction + 0.02));
          if (e.key === "ArrowLeft") seek(Math.max(0, fraction - 0.02));
        }}
        className="flex h-8 min-w-0 flex-1 cursor-pointer items-center justify-between gap-px overflow-hidden"
      >
        {BARS.map((h, i) => (
          <span
            key={i}
            className={`w-[3px] shrink-0 rounded-[2px] ${
              i / BARS.length < fraction ? "bg-brand" : "bg-line-control"
            }`}
            style={{ height: h }}
          />
        ))}
      </div>
      <span className="shrink-0 text-data text-ink-muted">
        {clock(time)} / {clock(total)}
      </span>
    </div>
  );
}
