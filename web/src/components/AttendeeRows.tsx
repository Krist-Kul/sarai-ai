import type { Attendee } from "../types";
import { useI18n } from "../lib/i18n";

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

  const field =
    "rounded-[10px] border border-line bg-surface px-2.5 py-1.5 text-[13.5px] outline-none focus:border-brand-600";

  return (
    <div className="space-y-2">
      {values.map((attendee, i) => (
        <div key={i} className="flex items-center gap-2">
          <span
            className="flex size-6.5 flex-none items-center justify-center rounded-full bg-brand-50 text-xs font-bold text-brand-600"
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
            className={`flex-1 ${field}`}
          />
          <input
            value={attendee.role ?? ""}
            onChange={(e) => update(i, { role: e.target.value || null })}
            placeholder={t("attendeeRole")}
            className={`w-32 ${field}`}
          />
          <button
            type="button"
            aria-label={`remove attendee ${i + 1}`}
            onClick={() => onChange(values.filter((_, j) => j !== i))}
            className="flex-none rounded-full px-2 text-ink-400 hover:text-bad-600"
          >
            ✕
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...values, { name: "", role: null }])}
        className="text-[13px] font-semibold text-brand-600 hover:underline"
      >
        ＋ {t("addAttendee")}
      </button>
    </div>
  );
}
