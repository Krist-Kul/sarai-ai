import { useState } from "react";
import { useI18n } from "../lib/i18n";

/** Glossary entry input. Enter or comma commits a term; Backspace on an empty
 *  field removes the last one. */
export function ChipInput({
  values,
  onChange,
}: {
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState("");

  const commit = (raw: string) => {
    const term = raw.trim();
    if (!term || values.includes(term)) {
      setDraft("");
      return;
    }
    onChange([...values, term]);
    setDraft("");
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-line bg-surface p-2 focus-within:border-brand-600">
      {values.map((term, i) => (
        <span
          key={term}
          className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-0.5 text-[13px] font-semibold text-brand-600"
        >
          {term}
          <button
            type="button"
            aria-label={`remove ${term}`}
            onClick={() => onChange(values.filter((_, j) => j !== i))}
            className="opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit(draft);
          } else if (e.key === "Backspace" && draft === "" && values.length > 0) {
            onChange(values.slice(0, -1));
          }
        }}
        onBlur={() => commit(draft)}
        placeholder={t("glossaryPlaceholder")}
        className="min-w-32 flex-1 border-0 bg-transparent px-1 py-0.5 text-[13px] outline-none placeholder:text-ink-400"
      />
    </div>
  );
}
