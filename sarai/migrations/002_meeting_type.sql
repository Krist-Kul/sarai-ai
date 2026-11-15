-- Meetings uploaded before meeting types existed were all summarized as
-- executive meetings; keep them that way so a regenerate does not change shape.
-- New meetings get their type from the upload form (default 'general').
ALTER TABLE meetings ADD COLUMN meeting_type TEXT NOT NULL DEFAULT 'executive';
