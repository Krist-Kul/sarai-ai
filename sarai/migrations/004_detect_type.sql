-- The upload form no longer asks for a meeting type: when none is given, the
-- summarize job asks the LLM to pick one from the transcript and saves it.
-- Existing meetings already have a type someone chose, so they keep it.
ALTER TABLE meetings ADD COLUMN detect_type INTEGER NOT NULL DEFAULT 0;
