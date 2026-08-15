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

  return (
    <div className="space-y-2">
      {values.map((attendee, i) => (
        <div key={i} className="flex gap-2">
          <input
            value={attendee.name}
            onChange={(e) => update(i, { name: e.target.value })}
            placeholder={t("attendeeName")}
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500"
          />
          <input
            value={attendee.role ?? ""}
            onChange={(e) => update(i, { role: e.target.value || null })}
            placeholder={t("attendeeRole")}
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500"
          />
          <button
            type="button"
            aria-label={`remove attendee ${i + 1}`}
            onClick={() => onChange(values.filter((_, j) => j !== i))}
            className="rounded-lg px-3 text-ink-400 hover:bg-slate-100 hover:text-rose-600"
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...values, { name: "", role: null }])}
        className="text-sm font-medium text-brand-600 hover:underline"
      >
        + {t("addAttendee")}
      </button>
    </div>
  );
}
