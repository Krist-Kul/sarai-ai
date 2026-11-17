import { useEffect, useRef, useState } from "react";
import { useI18n } from "../lib/i18n";

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

  return (
    <div>
      <div
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        role="button"
        tabIndex={0}
        className={`cursor-pointer rounded-2xl border-2 border-dashed transition ${
          over ? "border-brand-600 bg-brand-50" : "border-brand-200 bg-brand-25 hover:border-brand-600"
        } ${file ? "p-5" : "px-6 py-10"}`}
      >
        {file ? (
          <div className="flex items-center gap-4">
            <span
              className="flex size-13 flex-none items-center justify-center rounded-2xl bg-brand-50 text-xl text-brand-600"
              aria-hidden
            >
              ♪
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[15px] font-semibold">{file.name}</p>
              <p className="text-[12.5px] text-ink-600">
                {formatBytes(file.size)} · {t("fileReady")}
              </p>
              <div className="mt-2 h-1.5 max-w-[420px] overflow-hidden rounded-full bg-sand">
                <span className="block h-full w-full rounded-full bg-ok-600" />
              </div>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                choose(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
              className="flex-none rounded-full border border-line bg-surface px-3.5 py-1.5 text-[13px] font-semibold text-ink-600 hover:text-ink-900"
            >
              {t("replaceFile")}
            </button>
          </div>
        ) : (
          <div className="text-center">
            <p className="font-semibold">{t("dropzone")}</p>
            <p className="mt-1 text-sm text-ink-600">{t("dropzoneHint")}</p>
          </div>
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
        <p role="alert" className="mt-2.5 px-0.5 text-[12.5px] font-semibold text-bad-600">
          {t("unsupportedFile")}
        </p>
      )}
      <p className="mt-2.5 px-0.5 text-[12.5px] text-ink-600">
        <span aria-hidden>🔒</span> {t("privacyNote")}
      </p>
    </div>
  );
}
