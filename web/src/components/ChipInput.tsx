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
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-300 bg-white px-2 py-2 focus-within:border-brand-500">
      {values.map((term, i) => (
        <span
          key={term}
          className="inline-flex items-center gap-1 rounded-md bg-brand-50 px-2 py-1 text-sm text-brand-600"
        >
          {term}
          <button
            type="button"
            aria-label={`remove ${term}`}
            onClick={() => onChange(values.filter((_, j) => j !== i))}
            className="text-brand-600/70 hover:text-brand-600"
          >
            ×
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
        className="min-w-40 flex-1 border-0 px-1 py-0.5 text-sm outline-none"
      />
    </div>
  );
}
