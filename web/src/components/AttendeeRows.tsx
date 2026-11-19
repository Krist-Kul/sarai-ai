import type { Attendee } from "../types";
import { useI18n } from "../lib/i18n";
import { Icon } from "./Icon";

export const fieldClass =
  "rounded-md border border-line-control bg-surface-raised px-3 text-small text-ink outline-none " +
  "placeholder:text-ink-subtle focus:border-brand focus:shadow-glow";

export function AttendeeRows({
  values,
  onChange,
}: {
  values: Attendee[];
  onChange: (values: Attendee[]) => void;
}) {
  const { t } = useI18n();

  const update = (index: number, patch: Partial<Attendee>) => {
    onChange(values.map((a, i) => (i === index ? { ...a, ...patch } : a)));
  };

  return (
    <div className="flex flex-col gap-4">
      {values.map((attendee, i) => (
        <div key={i} className="flex items-center gap-2">
          <span
            className="flex size-7 flex-none items-center justify-center rounded-[14px] bg-brand-soft text-[12.5px] font-bold text-brand-ink"
            aria-hidden
          >
            {/* Array spread, not [0]: Thai vowels and Latin both index by code
                point here, so a name starting with a combining mark still
                shows the character the user typed. */}
            {[...attendee.name.trim()][0] ?? "?"}
          </span>
          <input
            value={attendee.name}
            onChange={(e) => update(i, { name: e.target.value })}
            placeholder={t("attendeeName")}
            aria-label={t("attendeeName")}
            className={`h-9 min-w-0 flex-1 ${fieldClass}`}
          />
          <input
            value={attendee.role ?? ""}
            onChange={(e) => update(i, { role: e.target.value || null })}
            placeholder={t("attendeeRole")}
            aria-label={t("attendeeRole")}
            className={`h-9 w-24 sm:w-32 ${fieldClass}`}
          />
          <button
            type="button"
            aria-label={`remove attendee ${i + 1}`}
            onClick={() => onChange(values.filter((_, j) => j !== i))}
            className="flex size-7 flex-none cursor-pointer items-center justify-center rounded-full text-ink-subtle hover:bg-danger-soft hover:text-danger"
          >
            <Icon name="close-14" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...values, { name: "", role: null }])}
        className="flex w-fit cursor-pointer items-center gap-1.5 text-small-strong text-brand-ink hover:underline"
      >
        <Icon name="plus-14" />
        {t("addAttendee")}
      </button>
    </div>
  );
}
