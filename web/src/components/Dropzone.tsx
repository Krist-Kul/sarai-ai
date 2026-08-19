import { useRef, useState } from "react";
import { useI18n } from "../lib/i18n";

const ACCEPT = ".mp3,.m4a,.wav,.ogg,.flac,.mp4";

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

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          const dropped = e.dataTransfer.files[0];
          if (dropped) onSelect(dropped);
        }}
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
                onSelect(null);
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
          onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
        />
      </div>
      <p className="mt-2.5 px-0.5 text-[12.5px] text-ink-600">
        <span aria-hidden>🔒</span> {t("privacyNote")}
      </p>
    </div>
  );
}
