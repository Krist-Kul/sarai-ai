-- Upload option: queue the minutes job as soon as transcription finishes,
-- instead of parking at awaiting_review. Existing meetings were all uploaded
-- under review-first, so they keep that behaviour; new uploads default to on.
ALTER TABLE meetings ADD COLUMN auto_summarize INTEGER NOT NULL DEFAULT 0;
