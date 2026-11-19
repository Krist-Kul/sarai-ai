import { useEffect, useRef, useState } from "react";
import { formatDuration, useI18n } from "../lib/i18n";
import { Icon } from "./Icon";
import { Button } from "./ui";

// Must match sarai.config.ALLOWED_UPLOAD_EXTENSIONS.
const ACCEPT =
  ".mp3,.m4a,.wav,.ogg,.flac,.aac,.opus,.wma,.amr,.aiff," +
  ".mp4,.mov,.mkv,.webm,.m4v,.avi,.3gp";
const EXTENSIONS = ACCEPT.split(",");

function isAccepted(file: File): boolean {
  const name = file.name.toLowerCase();
  return EXTENSIONS.some((ext) => name.endsWith(ext));
}

function hasFiles(e: DragEvent): boolean {
  return e.dataTransfer?.types.includes("Files") ?? false;
}

function formatBytes(bytes: number): string {
  const mb = bytes / 1024 / 1024;
  return mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(1)} MB`;
}

export function Dropzone({
  file,
  onSelect,
}: {
  file: File | null;
  onSelect: (file: File | null) => void;
}) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [rejected, setRejected] = useState(false);

  const choose = (picked: File | null) => {
    if (picked && !isAccepted(picked)) {
      setRejected(true);
      return;
    }
    setRejected(false);
    onSelect(picked);
  };
  const chooseRef = useRef(choose);
  chooseRef.current = choose;

  // The whole page is the drop target while this component is mounted. A file
  // dropped outside the box would otherwise make the browser open it and
  // throw away the form. The counter absorbs the dragenter/dragleave pairs
  // fired by every child element the pointer crosses.
  useEffect(() => {
    let depth = 0;
    const onEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth += 1;
      setOver(true);
    };
    const onLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setOver(false);
    };
    const onOver = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    };
    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setOver(false);
      const dropped = e.dataTransfer?.files[0];
      if (dropped) chooseRef.current(dropped);
    };
    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("dragover", onOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("drop", onDrop);
    };
  }, []);

  const duration = useMediaDuration(file);

  return (
    <div>
      <div
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        role="button"
        tabIndex={0}
        className={`flex cursor-pointer items-center gap-4 rounded-[24px] p-5 transition-[border-color,background-color,box-shadow] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
          over
            ? "border-[1.5px] border-solid border-brand bg-brand-soft shadow-glow"
            : "border-[1.5px] border-dashed border-line-control bg-surface hover:border-brand"
        } ${file ? "min-h-[92px] flex-wrap sm:flex-nowrap" : "min-h-[132px] flex-col justify-center text-center"}`}
      >
        {file ? (
          <>
            <span
              className="flex size-13 flex-none items-center justify-center rounded-md bg-brand text-on-brand"
              aria-hidden
            >
              <Icon name="file-audio-24" />
            </span>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <p className="truncate text-[16px] leading-[28px] font-semibold text-ink">
                {file.name}
              </p>
              <p className="truncate text-data text-ink-muted">
                {formatBytes(file.size)}
                {duration != null && ` · ${formatDuration(duration)}`} · {t("fileReady")}
              </p>
              <span className="h-1 w-full max-w-[280px] rounded-[2px] bg-done" aria-hidden />
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                choose(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
            >
              {t("replaceFile")}
            </Button>
          </>
        ) : (
          <>
            <span
              className={`flex size-13 items-center justify-center rounded-md ${
                over ? "bg-brand text-on-brand" : "bg-brand-soft text-brand"
              }`}
              aria-hidden
            >
              <Icon name="upload-20" />
            </span>
            <div className="flex flex-col gap-1">
              <p className="text-[16px] leading-[28px] font-semibold text-ink">{t("dropzone")}</p>
              <p className="text-small text-ink-muted">{t("dropzoneHint")}</p>
            </div>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            choose(e.target.files?.[0] ?? null);
            e.target.value = "";
          }}
        />
      </div>
      {rejected && (
        <p role="alert" className="mt-2.5 px-0.5 text-small-strong text-danger">
          {t("unsupportedFile")}
        </p>
      )}
    </div>
  );
}

/** Length of the picked recording, read by the browser's own decoder. Null
 *  until known, and for containers the browser cannot open (.wma, .amr). */
function useMediaDuration(file: File | null): number | null {
  const [duration, setDuration] = useState<number | null>(null);
  useEffect(() => {
    setDuration(null);
    if (!file) return;
    const url = URL.createObjectURL(file);
    const media = document.createElement(file.type.startsWith("video") ? "video" : "audio");
    media.preload = "metadata";
    media.onloadedmetadata = () => {
      if (Number.isFinite(media.duration)) setDuration(media.duration);
    };
    media.src = url;
    return () => {
      media.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
  }, [file]);
  return duration;
}
