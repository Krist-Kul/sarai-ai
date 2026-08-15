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
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${
          over ? "border-brand-500 bg-brand-50" : "border-slate-300 bg-white hover:border-brand-500"
        }`}
      >
        {file ? (
          <>
            <p className="font-medium break-all">{file.name}</p>
            <p className="mt-1 text-sm text-ink-600">{formatBytes(file.size)}</p>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSelect(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
              className="mt-3 text-sm text-brand-600 underline"
            >
              {t("cancel")}
            </button>
          </>
        ) : (
          <>
            <p className="font-medium">{t("dropzone")}</p>
            <p className="mt-1 text-sm text-ink-600">{t("dropzoneHint")}</p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
        />
      </div>
      <p className="mt-2 text-xs text-ink-600">{t("privacyNote")}</p>
    </div>
  );
}
