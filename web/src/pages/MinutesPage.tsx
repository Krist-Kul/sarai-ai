/**
 * Minutes -- a document you edit in place.
 *
 * Every section is the model's draft until the user changes it; edits autosave
 * and re-render the .docx server-side, so the file on disk always matches what
 * is on screen. Action items keep their source quote next to them: that quote
 * is the evidence the commitment was actually made.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { useI18n, type StringKey } from "../lib/i18n";
import { MEETING_TYPES, sectionLabels } from "../lib/meetingType";
import { useDebouncedSave } from "../lib/useDebouncedSave";
import { EditableText } from "../components/EditableText";
import { Icon } from "../components/Icon";
import { BackLink, Button, ButtonLink, buttonClass, Card, Notice } from "../components/ui";
import type { ActionItem, MinutesJSON } from "../types";

type Anchor = "summary" | "agenda" | "discussion" | "decisions" | "actions" | "questions" | "next";

function Avatar({ name, ring = false }: { name: string; ring?: boolean }) {
  return (
    <span
      aria-hidden
      className={`flex size-7 shrink-0 items-center justify-center rounded-[14px] bg-brand-soft text-[12.5px] font-bold text-brand-ink ${
        ring ? "border-2 border-surface" : ""
      }`}
    >
      {[...name.trim()][0] ?? "?"}
    </span>
  );
}

function Section({
  id,
  title,
  count,
  children,
}: {
  id: Anchor;
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="flex scroll-mt-24 flex-col gap-3.5">
      <div className="flex items-center gap-2.5 border-b border-line pb-2.5">
        <h2 className="text-[20px] leading-[30px] font-semibold tracking-[-0.1px]">{title}</h2>
        {count != null && (
          <span className="rounded-full bg-brand-soft px-2 font-mono text-[13px] leading-5 text-brand-ink">
            {count}
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

/** Which section is on screen, for the contents list. */
function useActiveSection(anchors: Anchor[]): Anchor | null {
  const [active, setActive] = useState<Anchor | null>(anchors[0] ?? null);
  const key = anchors.join(",");
  useEffect(() => {
    const seen = new Map<string, boolean>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) seen.set(e.target.id, e.isIntersecting);
        const first = key.split(",").find((a) => seen.get(a));
        if (first) setActive(first as Anchor);
      },
      { rootMargin: "-80px 0px -55% 0px" },
    );
    for (const anchor of key.split(",")) {
      const el = document.getElementById(anchor);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [key]);
  return active;
}

export function MinutesPage() {
  const { id = "" } = useParams();
  const { t } = useI18n();
  const queryClient = useQueryClient();

  const summary = useQuery({
    queryKey: ["summary", id],
    queryFn: () => api.getSummary(id),
    refetchOnWindowFocus: false,
    retry: false,
  });

  const labels = sectionLabels(summary.data?.meeting_type);

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

  const anchors = useMemo(() => {
    const list: Anchor[] = ["summary"];
    if (counts.agenda) list.push("agenda");
    if (counts.discussion) list.push("discussion");
    if (counts.decisions) list.push("decisions");
    list.push("actions");
    if (counts.questions) list.push("questions");
    if (minutes?.next_meeting) list.push("next");
    return list;
  }, [counts, minutes?.next_meeting]);
  const active = useActiveSection(anchors);

  if (summary.isPending) return <p className="text-small text-ink-muted">{t("loading")}</p>;

  if (summary.isError) {
    const notFound = summary.error instanceof ApiError && summary.error.status === 404;
    return (
      <Card className="flex flex-col items-center gap-2 px-6 py-12 text-center">
        <h2 className="text-[20px] leading-[30px] font-semibold">
          {notFound ? t("noMinutesTitle") : t("errorTitle")}
        </h2>
        <p className="max-w-md text-small text-ink-muted">
          {notFound
            ? t("noMinutesBody")
            : summary.error instanceof ApiError
              ? summary.error.message
              : String(summary.error)}
        </p>
        <ButtonLink to={`/meetings/${id}`} variant="outline" className="mt-3">
          {t("back")}
        </ButtonLink>
      </Card>
    );
  }

  if (!minutes) return <p className="text-small text-ink-muted">{t("loading")}</p>;

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

  const typeKey = MEETING_TYPES.find((o) => o.value === summary.data.meeting_type)?.key;
  const attendees = minutes.attendees ?? [];
  const contents: { anchor: Anchor; label: string; count?: number }[] = anchors.map((anchor) => {
    const label: Record<Anchor, StringKey> = {
      summary: labels.summary,
      agenda: "sectionAgenda",
      discussion: labels.discussion,
      decisions: "sectionDecisions",
      actions: "sectionActions",
      questions: "sectionQuestions",
      next: "sectionNextMeeting",
    };
    const count: Partial<Record<Anchor, number>> = {
      agenda: counts.agenda,
      discussion: counts.discussion,
      decisions: counts.decisions,
      actions: counts.actions,
      questions: counts.questions,
    };
    return { anchor, label: t(label[anchor]), count: count[anchor] };
  });
  const downloadable = summary.data.has_document;

  return (
    <div className="flex flex-col gap-5">
      <BackLink to={`/meetings/${id}`}>{t("back")}</BackLink>

      <div className="flex flex-wrap items-center gap-2.5">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className="text-eyebrow text-brand-ink">STEP 04 · MINUTES</p>
          <div className="flex flex-wrap items-center gap-x-3">
            <h1 className="text-[24px] leading-[34px] font-semibold tracking-[-0.3px] sm:text-display">
              {t("minutes")}
            </h1>
            <span className="flex items-center gap-1.5 text-small">
              {save.error ? (
                <span className="text-danger">{t("saveFailed")}</span>
              ) : save.status === "saving" ? (
                <span className="text-ink-muted">{t("saving")}</span>
              ) : save.status === "dirty" ? (
                <span className="text-ink-subtle">{t("unsaved")}</span>
              ) : (
                <span className="flex items-center gap-1.5 text-done">
                  <Icon name="check-14" />
                  {t("allSaved")}
                </span>
              )}
            </span>
          </div>
        </div>
        <Button
          variant="ghost"
          onClick={() => regenerate.mutate()}
          disabled={regenerate.isPending}
        >
          {regenerate.isPending ? t("submitting") : t("regenerate")}
        </Button>
        <a
          href={api.documentUrl(id)}
          aria-disabled={!downloadable}
          className={`${buttonClass("outline")} ${downloadable ? "" : "pointer-events-none opacity-50"}`}
        >
          {t("downloadDocx")}
          <Icon name="download" />
        </a>
        <a
          href={api.pdfUrl(id)}
          aria-disabled={!downloadable}
          className={`${buttonClass("primary")} ${downloadable ? "" : "pointer-events-none opacity-50"}`}
        >
          {t("downloadPdf")}
          <Icon name="download" />
        </a>
      </div>

      <Notice tone="danger" inline>
        {t("aiNotice")}
      </Notice>

      {regenerate.isSuccess && (
        <Notice
          tone="live"
          inline
          action={
            <ButtonLink to={`/meetings/${id}`} variant="outline" size="sm">
              {t("actionWatch")}
            </ButtonLink>
          }
        >
          {t("regenerateQueued")}
        </Notice>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[248px_1fr]">
        <nav
          aria-label={t("contents")}
          className="hidden flex-col gap-0.5 rounded-lg border border-line bg-surface px-3 py-4 lg:sticky lg:top-24 lg:flex"
        >
          <p className="pb-2 pl-2 text-eyebrow text-ink-subtle">CONTENTS</p>
          {contents.map((item) => {
            const current = active === item.anchor;
            return (
              <a
                key={item.anchor}
                href={`#${item.anchor}`}
                aria-current={current ? "location" : undefined}
                className={`flex items-center gap-2 rounded-sm px-2.5 py-[7px] ${
                  current
                    ? "bg-brand-soft text-label text-brand-ink"
                    : "text-small text-ink-muted hover:bg-surface-raised hover:text-ink"
                }`}
              >
                <span className="min-w-0 flex-1">{item.label}</span>
                {item.count != null && (
                  <span className="rounded-full bg-surface-raised px-[7px] font-mono text-[13px] leading-5 font-normal text-ink-muted">
                    {item.count}
                  </span>
                )}
              </a>
            );
          })}
          <p className="pt-3 pr-1.5 pl-2.5 text-small text-ink-subtle">{t("minutesEditableNote")}</p>
        </nav>

        <article className="flex min-w-0 flex-col gap-9 rounded-[24px] border border-line bg-surface px-5 pt-8 pb-10 shadow-card sm:px-14 sm:pt-12 sm:pb-14">
          <header className="flex flex-col gap-3">
            <span className="flex w-fit items-center gap-1.5 rounded-full bg-brand-soft py-[3px] pr-3 pl-2.5 text-small-strong text-brand-ink">
              <Icon name="sparkle-14" />
              {t("aiDraftNote")}
            </span>
            <EditableText
              value={minutes.title}
              onChange={(title) => edit({ title })}
              onCommit={save.flush}
              ariaLabel={t("title")}
              className="text-[28px] leading-[40px] font-semibold tracking-[-0.72px] sm:text-[36px] sm:leading-[48px]"
            />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-2 text-small text-ink-muted">
              <span className="flex items-center gap-1.5">
                <Icon name="clock-16" />
                {minutes.meeting_date ?? "—"}
              </span>
              {attendees.length > 0 && (
                <span className="flex items-center gap-1.5">
                  <Icon name="users-16" />
                  {t("attendeeCount", { n: attendees.length })}
                </span>
              )}
              {typeKey && (
                <span className="rounded-full bg-surface-raised px-2.5 py-0.5 text-small-strong">
                  {t(typeKey)}
                </span>
              )}
              {attendees.length > 0 && (
                <span className="flex" title={attendees.map((a) => a.name).join(", ")}>
                  {attendees.slice(0, 6).map((a, i) => (
                    <span key={a.name} className={i > 0 ? "-ml-1.5" : ""}>
                      <Avatar name={a.name} ring />
                    </span>
                  ))}
                </span>
              )}
            </div>
          </header>

          <Section id="summary" title={t(labels.summary)}>
            <EditableText
              value={minutes.summary ?? ""}
              onChange={(summaryText) => edit({ summary: summaryText })}
              onCommit={save.flush}
              ariaLabel={t(labels.summary)}
              className="text-[16px] leading-[28px]"
            />
          </Section>

          {counts.agenda > 0 && (
            <Section id="agenda" title={t("sectionAgenda")} count={counts.agenda}>
              {(minutes.agenda ?? []).map((item, index) => (
                <div key={index} className="group flex items-start gap-3.5">
                  <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-sm bg-surface-raised text-data text-ink-muted">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <EditableText
                    value={item}
                    onChange={(value) => setListItem("agenda", index, value)}
                    onCommit={save.flush}
                    ariaLabel={`${t("sectionAgenda")} ${index + 1}`}
                    className="text-[16px] leading-[28px]"
                  />
                  <RemoveButton
                    label={`${t("delete")} ${index + 1}`}
                    onClick={() => removeListItem("agenda", index)}
                  />
                </div>
              ))}
            </Section>
          )}

          {counts.discussion > 0 && (
            <Section id="discussion" title={t(labels.discussion)} count={counts.discussion}>
              {(minutes.discussion ?? []).map((topic, index) => (
                <div key={index} className="flex flex-col gap-1">
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
                    ariaLabel={t(labels.discussion)}
                    className="text-[16px] leading-[28px] font-semibold"
                  />
                  {(topic.points ?? []).map((point, pointIndex) => (
                    <div key={pointIndex} className="flex items-start gap-2 pl-4">
                      <span aria-hidden className="mt-[13px] size-1 shrink-0 rounded-full bg-ink-subtle" />
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
                        className="text-[16px] leading-[28px]"
                      />
                    </div>
                  ))}
                </div>
              ))}
            </Section>
          )}

          {counts.decisions > 0 && (
            <Section id="decisions" title={t("sectionDecisions")} count={counts.decisions}>
              {(minutes.decisions ?? []).map((decision, index) => (
                <div key={index} className="flex gap-3.5 rounded-md bg-surface-raised px-4 py-3.5">
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-[14px] bg-done-soft text-done">
                    <Icon name="check-16" />
                  </span>
                  <div className="flex min-w-0 flex-1 flex-col gap-0.5">
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
                      className="text-[16px] leading-[28px] font-semibold"
                    />
                    {decision.rationale && (
                      <div className="flex items-start gap-1 text-small text-ink-muted">
                        <span className="shrink-0 pt-0.5 pl-2">{t("rationale")} ·</span>
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
                          className="text-small text-ink-muted"
                        />
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </Section>
          )}

          <Section id="actions" title={t("sectionActions")} count={counts.actions}>
            {counts.actions > 0 && (
              <div className="overflow-hidden rounded-md border border-line">
                <div className="hidden gap-4 border-b border-line bg-surface-raised px-4 py-2 text-small-strong text-ink-subtle sm:flex">
                  <span className="flex-1">{t("task")}</span>
                  <span className="w-[190px]">{t("owner")}</span>
                  <span className="w-[120px]">{t("due")}</span>
                  <span className="w-8" />
                </div>
                {(minutes.action_items ?? []).map((item, index) => (
                  <div
                    key={index}
                    className="group flex flex-col gap-2 border-b border-line px-4 py-3 last:border-b-0 sm:flex-row sm:items-start sm:gap-4"
                  >
                    <div className="min-w-0 flex-1">
                      <EditableText
                        value={item.task}
                        onChange={(task) => setItem(index, { task })}
                        onCommit={save.flush}
                        ariaLabel={t("task")}
                        className="text-[16px] leading-[28px]"
                      />
                      {/* The quote is why this item exists; it is not editable,
                          because editing it would break the link to what was
                          actually said. */}
                      {item.source_quote && (
                        <p className="px-2 text-small text-ink-subtle italic">
                          “{item.source_quote}”
                        </p>
                      )}
                    </div>
                    <label className="flex items-center gap-2 sm:w-[190px]">
                      <Avatar name={item.owner || "?"} />
                      <input
                        value={item.owner ?? ""}
                        onChange={(e) => setItem(index, { owner: e.target.value || null })}
                        onBlur={save.flush}
                        placeholder={t("owner")}
                        aria-label={t("owner")}
                        className="h-8 min-w-0 flex-1 rounded-sm border border-transparent bg-transparent px-1.5 text-small text-ink outline-none placeholder:text-ink-subtle hover:bg-surface-raised focus:border-brand"
                      />
                    </label>
                    <div className="flex items-center sm:w-[120px]">
                      <input
                        value={item.due ?? ""}
                        onChange={(e) => setItem(index, { due: e.target.value || null })}
                        onBlur={save.flush}
                        placeholder="—"
                        aria-label={t("due")}
                        className="h-7 w-full max-w-[120px] rounded-full border border-transparent bg-surface-raised px-2 text-small text-ink-muted outline-none focus:border-brand"
                      />
                    </div>
                    <RemoveButton
                      label={`${t("delete")} ${item.task}`}
                      onClick={() =>
                        edit({
                          action_items: (minutes.action_items ?? []).filter((_, i) => i !== index),
                        })
                      }
                    />
                  </div>
                ))}
              </div>
            )}
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
              className="flex w-fit cursor-pointer items-center gap-1.5 text-small-strong text-brand-ink hover:underline"
            >
              <Icon name="plus-14" />
              {t("addActionItem")}
            </button>
          </Section>

          {counts.questions > 0 && (
            <Section id="questions" title={t("sectionQuestions")} count={counts.questions}>
              {(minutes.open_questions ?? []).map((question, index) => (
                <div key={index} className="group flex items-start gap-3">
                  <Icon name="alert-18" className="mt-[5px] text-live" />
                  <EditableText
                    value={question}
                    onChange={(value) => setListItem("open_questions", index, value)}
                    onCommit={save.flush}
                    ariaLabel={`${t("sectionQuestions")} ${index + 1}`}
                    className="text-[16px] leading-[28px]"
                  />
                  <RemoveButton
                    label={`${t("delete")} ${index + 1}`}
                    onClick={() => removeListItem("open_questions", index)}
                  />
                </div>
              ))}
            </Section>
          )}

          {minutes.next_meeting && (
            <Section id="next" title={t("sectionNextMeeting")}>
              <div className="flex items-center gap-3.5 rounded-md bg-brand-soft px-[18px] py-3.5">
                <Icon name="clock-20" className="text-brand-ink" />
                <EditableText
                  value={minutes.next_meeting}
                  onChange={(value) => edit({ next_meeting: value })}
                  onCommit={save.flush}
                  ariaLabel={t("sectionNextMeeting")}
                  className="text-[16px] leading-[28px] font-semibold"
                />
              </div>
            </Section>
          )}
        </article>
      </div>
    </div>
  );
}

/** Row delete: quiet until the row is hovered or focused. */
function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex size-8 shrink-0 cursor-pointer items-center justify-center self-start rounded-full text-ink-subtle opacity-100 hover:bg-danger-soft hover:text-danger focus-visible:opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
    >
      <Icon name="trash" />
    </button>
  );
}
