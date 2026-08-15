CREATE TABLE meetings (
  id             TEXT PRIMARY KEY,
  title          TEXT NOT NULL,
  meeting_date   TEXT,
  source_file    TEXT NOT NULL,
  audio_path     TEXT NOT NULL,
  duration_sec   REAL,
  language_hint  TEXT NOT NULL DEFAULT 'auto',   -- auto | th | en
  glossary       TEXT,                            -- JSON array of strings
  attendees      TEXT,                            -- JSON array of {name, role}
  created_at     TEXT NOT NULL
);

CREATE TABLE jobs (
  id           TEXT PRIMARY KEY,
  meeting_id   TEXT NOT NULL REFERENCES meetings(id),
  kind         TEXT NOT NULL,   -- transcribe | summarize
  stage        TEXT NOT NULL,   -- queued|normalizing|diarizing|transcribing|
                                -- awaiting_review|summarizing|rendering|done|failed
  progress     REAL NOT NULL DEFAULT 0,
  detail       TEXT,            -- "142/380 segments"
  error        TEXT,
  attempts     INTEGER NOT NULL DEFAULT 0,
  claimed_by   TEXT,            -- worker pid, for crash recovery
  claimed_at   TEXT,
  updated_at   TEXT NOT NULL
);
CREATE INDEX idx_jobs_claimable ON jobs(stage, claimed_at);
CREATE INDEX idx_jobs_meeting ON jobs(meeting_id, updated_at);

CREATE TABLE transcripts (
  meeting_id   TEXT PRIMARY KEY REFERENCES meetings(id),
  segments     TEXT NOT NULL,   -- JSON array of Segment
  edited       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE speakers (
  meeting_id   TEXT NOT NULL REFERENCES meetings(id),
  key          TEXT NOT NULL,   -- "SPEAKER_00"
  label        TEXT NOT NULL,   -- "คุณสมชาย"
  PRIMARY KEY (meeting_id, key)
);

CREATE TABLE summaries (
  meeting_id   TEXT PRIMARY KEY REFERENCES meetings(id),
  data         TEXT NOT NULL,   -- MinutesJSON
  model        TEXT NOT NULL,
  docx_path    TEXT,
  created_at   TEXT NOT NULL
);

-- Single-row table the worker touches every poll. The API reads it for
-- /api/health so the UI can tell "queued" from "nothing is running".
CREATE TABLE worker_heartbeat (
  id           INTEGER PRIMARY KEY CHECK (id = 1),
  pid          TEXT NOT NULL,
  beat_at      TEXT NOT NULL
);
