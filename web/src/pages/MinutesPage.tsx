/**
 * Minutes -- a document you edit in place.
 *
 * Every section is the model's draft until the user changes it; edits autosave
 * and re-render the .docx server-side, so the file on disk always matches what
 * is on screen. Action items keep their source quote next to them: that quote
 * is the evidence the commitment was actually made.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { formatDateTime, useI18n } from "../lib/i18n";
import { useDebouncedSave } from "../lib/useDebouncedSave";
import { EditableText } from "../components/EditableText";
import type { ActionItem, MinutesJSON } from "../types";

const SECTION = "mt-7 mb-2 text-[13px] font-bold uppercase tracking-[0.08em] text-ink-400";

export function MinutesPage() {
  const { id = "" } = useParams();
  const { t, lang } = useI18n();
  const queryClient = useQueryClient();

  const summary = useQuery({
    queryKey: ["summary", id],
    queryFn: () => api.getSummary(id),
    refetchOnWindowFocus: false,
    retry: false,
  });

  const [minutes, setMinutes] = useState<MinutesJSON | null>(null);
  const loaded = useRef(false);

  // Same rule as the transcript editor: the server copy seeds the page once,
  // then the editor owns it.
  useEffect(() => {
    if (!summary.data || loaded.current) return;
    setMinutes(summary.data.data);
    loaded.current = true;
  }, [summary.data]);

  const save = useDebouncedSave<MinutesJSON>(
    useCallback(
      async (next: MinutesJSON) => {
        const saved = await api.saveSummary(id, next);
        void queryClient.invalidateQueries({ queryKey: ["meetings"] });
        return saved;
      },
      [id, queryClient],
    ),
  );

  const regenerate = useMutation({
    mutationFn: () => api.summarize(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["meeting", id] });
      void queryClient.invalidateQueries({ queryKey: ["meetings"] });
    },
  });

  const edit = useCallback(
    (patch: Partial<MinutesJSON>) => {
      setMinutes((current) => {
        if (!current) return current;
        const next = { ...current, ...patch };
        save.schedule(next);
        return next;
      });
    },
    [save],
  );

  const counts = useMemo(
    () => ({
      agenda: minutes?.agenda?.length ?? 0,
      discussion: minutes?.discussion?.length ?? 0,
      decisions: minutes?.decisions?.length ?? 0,
      actions: minutes?.action_items?.length ?? 0,
      questions: minutes?.open_questions?.length ?? 0,
    }),
    [minutes],
  );

  if (summary.isPending) return <p className="text-ink-600">{t("loading")}</p>;

  if (summary.isError) {
    const notFound = summary.error instanceof ApiError && summary.error.status === 404;
    return (
      <div className="rounded-2xl border border-line bg-surface px-6 py-12 text-center">
        <h2 className="text-lg font-bold">{notFound ? t("noMinutesTitle") : t("errorTitle")}</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-ink-600">
          {notFound
            ? t("noMinutesBody")
            : summary.error instanceof ApiError
              ? summary.error.message
              : String(summary.error)}
        </p>
        <Link
          to={`/meetings/${id}`}
          className="mt-5 inline-block rounded-full border border-line px-4 py-2 text-sm font-semibold"
        >
          {t("back")}
        </Link>
      </div>
    );
  }

  if (!minutes) return <p className="text-ink-600">{t("loading")}</p>;

  const setItem = (index: number, patch: Partial<ActionItem>) =>
    edit({
      action_items: (minutes.action_items ?? []).map((item, i) =>
        i === index ? { ...item, ...patch } : item,
      ),
    });

  const setListItem = (key: "agenda" | "open_questions", index: number, value: string) =>
    edit({ [key]: (minutes[key] ?? []).map((v, i) => (i === index ? value : v)) });

  const removeListItem = (key: "agenda" | "open_questions", index: number) =>
    edit({ [key]: (minutes[key] ?? []).filter((_, i) => i !== index) });

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[220px_1fr]">
      <aside className="lg:sticky lg:top-4">
        <div className="flex flex-wrap items-center gap-2">
          <Link to={`/meetings/${id}`} className="text-sm text-ink-600 hover:text-ink-900">
            ← {t("back")}
          </Link>
        </div>
        <div className="mt-4 text-[12px] font-bold uppercase tracking-[0.06em] text-ink-400">
          {t("contents")}
        </div>
        <div className="mt-2 flex flex-col gap-0.5 text-[13.5px]">
          {(
            [
              ["summary", t("sectionSummary"), null],
              ["agenda", t("sectionAgenda"), counts.agenda],
              ["discussion", t("sectionDiscussion"), counts.discussion],
              ["decisions", t("sectionDecisions"), counts.decisions],
              ["actions", t("sectionActions"), counts.actions],
              ["questions", t("sectionQuestions"), counts.questions],
            ] as const
          ).map(([anchor, label, count]) => (
            <a
              key={anchor}
              href={`#${anchor}`}
              className="rounded-lg px-2.5 py-1.5 text-ink-600 hover:bg-sand hover:text-ink-900"
            >
              {label}
              {count != null && <span className="text-ink-400"> · {count}</span>}
            </a>
          ))}
        </div>
        <p className="mt-4 text-[12px] leading-relaxed text-ink-400">{t("minutesEditableNote")}</p>
      </aside>

      <section className="min-w-0">
        <div className="mb-4 flex flex-wrap items-center gap-2.5">
          <h1 className="text-xl font-bold tracking-tight">{t("minutes")}</h1>
          <span className="rounded-full bg-sand px-2.5 py-0.5 text-xs text-ink-600">
            {summary.data.model} · {formatDateTime(summary.data.created_at, lang)}
          </span>
          <span className="ml-auto text-[12.5px]">
            {save.error ? (
              <span className="text-bad-600">{t("saveFailed")}</span>
            ) : save.status === "saving" ? (
              <span className="text-ink-600">{t("saving")}</span>
            ) : save.status === "dirty" ? (
              <span className="text-ink-400">{t("unsaved")}</span>
            ) : (
              <span className="text-ok-600">{t("allSaved")}</span>
            )}
          </span>
          <button
            type="button"
            onClick={() => regenerate.mutate()}
            disabled={regenerate.isPending}
            className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-[13px] font-semibold hover:border-ink-200 disabled:text-ink-400"
          >
            {regenerate.isPending ? t("submitting") : t("regenerate")}
          </button>
          <a
            href={api.documentUrl(id)}
            className={`rounded-full px-4 py-2 text-[13.5px] font-bold ${
              summary.data.has_document
                ? "bg-brand-600 text-white hover:bg-brand-600/90"
                : "pointer-events-none bg-ink-200 text-surface"
            }`}
          >
            {t("downloadDocx")}
          </a>
        </div>

        {regenerate.isSuccess && (
          <div className="mb-4 rounded-xl border border-warn-line bg-warn-50 p-3 text-sm text-warn-700">
            {t("regenerateQueued")}{" "}
            <Link to={`/meetings/${id}`} className="font-semibold underline">
              {t("actionWatch")}
            </Link>
          </div>
        )}

        <article className="rounded-2xl border border-line bg-surface p-6 sm:p-10">
          <div className="border-b border-line-soft pb-4">
            <EditableText
              value={minutes.title}
              onChange={(title) => edit({ title })}
              onCommit={save.flush}
              ariaLabel={t("title")}
              className="text-2xl font-bold tracking-tight"
            />
            <p className="mt-1 px-1.5 text-[13.5px] text-ink-600">
              {minutes.meeting_date ?? "—"}
              {minutes.attendees && minutes.attendees.length > 0 && (
                <> · {minutes.attendees.map((a) => a.name).join(", ")}</>
              )}
            </p>
          </div>

          <h2 id="summary" className={SECTION}>
            {t("sectionSummary")}
          </h2>
          <EditableText
            value={minutes.summary ?? ""}
            onChange={(summaryText) => edit({ summary: summaryText })}
            onCommit={save.flush}
            ariaLabel={t("sectionSummary")}
            className="text-[15.5px] leading-[1.9]"
          />

          {(minutes.agenda ?? []).length > 0 && (
            <>
              <h2 id="agenda" className={SECTION}>
                {t("sectionAgenda")}
              </h2>
              {(minutes.agenda ?? []).map((item, index) => (
                <div key={index} className="flex items-start gap-2">
                  <span className="pt-1 text-[15px] text-ink-400">{index + 1}.</span>
                  <EditableText
                    value={item}
                    onChange={(value) => setListItem("agenda", index, value)}
                    onCommit={save.flush}
                    ariaLabel={`${t("sectionAgenda")} ${index + 1}`}
                    className="text-[15px] leading-[1.9]"
                  />
                  <button
                    type="button"
                    onClick={() => removeListItem("agenda", index)}
                    aria-label={`${t("delete")} ${index + 1}`}
                    className="pt-1 text-ink-400 hover:text-bad-600"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </>
          )}

          {(minutes.discussion ?? []).length > 0 && (
            <>
              <h2 id="discussion" className={SECTION}>
                {t("sectionDiscussion")}
              </h2>
              {(minutes.discussion ?? []).map((topic, index) => (
                <div key={index} className="mb-4">
                  <EditableText
                    value={topic.topic}
                    onChange={(value) =>
                      edit({
                        discussion: (minutes.discussion ?? []).map((d, i) =>
                          i === index ? { ...d, topic: value } : d,
                        ),
                      })
                    }
                    onCommit={save.flush}
                    ariaLabel={t("sectionDiscussion")}
                    className="text-[15px] font-semibold"
                  />
                  {(topic.points ?? []).map((point, pointIndex) => (
                    <div key={pointIndex} className="flex items-start gap-2 pl-4">
                      <span className="pt-1 text-ink-400">•</span>
                      <EditableText
                        value={point}
                        onChange={(value) =>
                          edit({
                            discussion: (minutes.discussion ?? []).map((d, i) =>
                              i === index
                                ? {
                                    ...d,
                                    points: (d.points ?? []).map((p, j) =>
                                      j === pointIndex ? value : p,
                                    ),
                                  }
                                : d,
                            ),
                          })
                        }
                        onCommit={save.flush}
                        ariaLabel={`${topic.topic} ${pointIndex + 1}`}
                        className="text-[15px] leading-[1.9]"
                      />
                    </div>
                  ))}
                </div>
              ))}
            </>
          )}

          {(minutes.decisions ?? []).length > 0 && (
            <>
              <h2 id="decisions" className={SECTION}>
                {t("sectionDecisions")}
              </h2>
              <div className="flex flex-col gap-2.5">
                {(minutes.decisions ?? []).map((decision, index) => (
                  <div key={index} className="flex gap-3">
                    <span className="w-1.5 flex-none rounded-full bg-brand-600" aria-hidden />
                    <div className="min-w-0 flex-1">
                      <EditableText
                        value={decision.decision}
                        onChange={(value) =>
                          edit({
                            decisions: (minutes.decisions ?? []).map((d, i) =>
                              i === index ? { ...d, decision: value } : d,
                            ),
                          })
                        }
                        onCommit={save.flush}
                        ariaLabel={t("sectionDecisions")}
                        className="text-[15px] leading-[1.9]"
                      />
                      {decision.rationale && (
                        <EditableText
                          value={decision.rationale}
                          onChange={(value) =>
                            edit({
                              decisions: (minutes.decisions ?? []).map((d, i) =>
                                i === index ? { ...d, rationale: value } : d,
                              ),
                            })
                          }
                          onCommit={save.flush}
                          ariaLabel={t("rationale")}
                          className="text-[13px] text-ink-600"
                        />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          <h2 id="actions" className={SECTION}>
            {t("sectionActions")}
          </h2>
          <div className="flex flex-col gap-2.5">
            {(minutes.action_items ?? []).map((item, index) => (
              <div key={index} className="rounded-xl border border-line-soft p-3.5">
                <EditableText
                  value={item.task}
                  onChange={(task) => setItem(index, { task })}
                  onCommit={save.flush}
                  ariaLabel={t("task")}
                  className="text-[15px]"
                />
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  <input
                    value={item.owner ?? ""}
                    onChange={(e) => setItem(index, { owner: e.target.value || null })}
                    onBlur={save.flush}
                    placeholder={t("owner")}
                    aria-label={t("owner")}
                    className="rounded-full bg-sand px-2.5 py-0.5 text-[12.5px] font-semibold outline-none focus:bg-surface focus:ring-1 focus:ring-brand-600"
                  />
                  <input
                    value={item.due ?? ""}
                    onChange={(e) => setItem(index, { due: e.target.value || null })}
                    onBlur={save.flush}
                    placeholder={t("due")}
                    aria-label={t("due")}
                    className="rounded-full bg-sand px-2.5 py-0.5 text-[12.5px] font-semibold outline-none focus:bg-surface focus:ring-1 focus:ring-brand-600"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      edit({
                        action_items: (minutes.action_items ?? []).filter((_, i) => i !== index),
                      })
                    }
                    className="ml-auto text-[12.5px] text-ink-400 hover:text-bad-600"
                  >
                    {t("delete")}
                  </button>
                </div>
                {/* The quote is why this item exists; it is not editable, because
                    editing it would break the link to what was actually said. */}
                <p className="mt-2 border-l-[3px] border-line pl-3 text-[13.5px] italic text-ink-600">
                  “{item.source_quote}”
                </p>
              </div>
            ))}
            <button
              type="button"
              onClick={() =>
                edit({
                  action_items: [
                    ...(minutes.action_items ?? []),
                    { task: "", owner: null, due: null, source_quote: "" },
                  ],
                })
              }
              className="self-start text-[13px] font-semibold text-brand-600 hover:underline"
            >
              ＋ {t("addActionItem")}
            </button>
          </div>

          {(minutes.open_questions ?? []).length > 0 && (
            <>
              <h2 id="questions" className={SECTION}>
                {t("sectionQuestions")}
              </h2>
              {(minutes.open_questions ?? []).map((question, index) => (
                <div key={index} className="flex items-start gap-2">
                  <span className="pt-1 text-ink-400">•</span>
                  <EditableText
                    value={question}
                    onChange={(value) => setListItem("open_questions", index, value)}
                    onCommit={save.flush}
                    ariaLabel={`${t("sectionQuestions")} ${index + 1}`}
                    className="text-[15px] leading-[1.9]"
                  />
                  <button
                    type="button"
                    onClick={() => removeListItem("open_questions", index)}
                    aria-label={`${t("delete")} ${index + 1}`}
                    className="pt-1 text-ink-400 hover:text-bad-600"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </>
          )}

          {minutes.next_meeting && (
            <>
              <h2 className={SECTION}>{t("sectionNextMeeting")}</h2>
              <EditableText
                value={minutes.next_meeting}
                onChange={(value) => edit({ next_meeting: value })}
                onCommit={save.flush}
                ariaLabel={t("sectionNextMeeting")}
                className="text-[15px]"
              />
            </>
          )}
        </article>
      </section>
    </div>
  );
}
