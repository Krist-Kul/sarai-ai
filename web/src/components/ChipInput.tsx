import { useState } from "react";
import { useI18n } from "../lib/i18n";
import { Icon } from "./Icon";

/** Glossary entry input. Enter or comma commits a term; Backspace on an empty
 *  field removes the last one. */
export function ChipInput({
  values,
  onChange,
  id,
}: {
  values: string[];
  onChange: (values: string[]) => void;
  id?: string;
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
    <div className="flex min-h-11 flex-wrap items-center gap-1.5 rounded-md border border-line-control bg-surface-raised p-2 focus-within:border-brand focus-within:shadow-glow">
      {values.map((term, i) => (
        <span
          key={term}
          className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft py-0 pr-1.5 pl-3 text-[13px] leading-[26px] font-semibold text-brand-ink"
        >
          {term}
          <button
            type="button"
            aria-label={`remove ${term}`}
            onClick={() => onChange(values.filter((_, j) => j !== i))}
            className="flex size-[18px] cursor-pointer items-center justify-center rounded-[9px] hover:bg-brand/15"
          >
            <Icon name="close-12" />
          </button>
        </span>
      ))}
      <input
        id={id}
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
        className="min-w-32 flex-1 border-0 bg-transparent px-1 text-[13px] leading-[26px] text-ink outline-none placeholder:text-ink-subtle"
      />
    </div>
  );
}
