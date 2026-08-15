# Build Prompt: Sarai AI

> Paste this whole file into Claude Code as your opening message, or save it as `SPEC.md` in an empty repo and tell Claude Code: *"Read SPEC.md and implement Phase 0 and Phase 1. Stop and show me before continuing."*

---

## 0. Your task

Build **Sarai AI** — a self-hosted web application that turns meeting audio into an editable Word document of meeting minutes. It must handle Thai, English, and mixed Thai-English speech (code-switching), which is how real Thai corporate meetings are conducted.

Work in **phases**. After each phase, stop, run the verification steps for that phase, and report back before starting the next one. Do not scaffold all phases at once.

### Non-negotiables

- Audio never leaves the local network. Transcription is self-hosted. Only the **text** transcript is sent to a third-party LLM, and even that must be disableable via config.
- The summary is generated as **structured JSON first**, then rendered to `.docx`. Never have the LLM write the document directly.
- The user can **edit the transcript and fix speaker names before** the summary is generated. Garbage transcript in, garbage minutes out — the review step is the product, not a nice-to-have.
- Thai text must render correctly in the output `.docx` (correct font, no tofu boxes).

---

## 1. Architecture

Two processes, one Python codebase, one shared set of Pydantic models.

```
┌─────────────────┐     HTTP/JSON      ┌──────────────────────────┐
│  web/           │ ─────────────────► │  api  (uvicorn)          │
│  React + TS     │ ◄───────────────── │  FastAPI :8000           │
│  Tailwind       │   SSE progress     │  uploads, CRUD, SSE      │
│  :5173          │                    │  NO torch imported here  │
└─────────────────┘                    └────────────┬─────────────┘
                                                    │
                                       ┌────────────▼─────────────┐
                                       │  SQLite (WAL)            │
                                       │  jobs table = the queue  │
                                       └────────────▲─────────────┘
                                                    │ claim / update
                                       ┌────────────┴─────────────┐
                                       │  worker  (separate proc) │
                                       │  torch + Typhoon +       │
                                       │  pyannote loaded once    │
                                       │  ffmpeg, LLM, docx       │
                                       └──────────────────────────┘
```

**Why two processes and not one:** the worker holds several GB of model weights on the GPU and runs jobs that take minutes. If that lives inside the web process, one transcription blocks every HTTP request and a model OOM takes your API down with it. The API process must never `import torch` — enforce this with a test that greps the api package for torch imports.

**Why they share a codebase:** `Segment`, `MinutesJSON`, and the DB layer are defined once as Pydantic models in `sarai/models.py` and imported by the API, the worker, and the schema generator that emits TypeScript types for the frontend. This is the main reason Python is the right call here — in a split-language stack these definitions live in three places and silently diverge.

---

## 2. Repo structure

```
sarai/
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── .env.example
├── sarai/
│   ├── models.py           # Pydantic: Segment, MinutesJSON, Meeting, Job. SHARED.
│   ├── config.py           # pydantic-settings, env only
│   ├── db.py               # sqlite3 + WAL, migrations, repository functions
│   ├── api/
│   │   ├── main.py         # FastAPI app factory
│   │   ├── routes/         # meetings.py, transcripts.py, summaries.py, events.py
│   │   └── deps.py
│   ├── worker/
│   │   ├── main.py         # poll loop, claim, dispatch, retry
│   │   ├── stages.py       # normalize -> diarize -> transcribe -> summarize -> render
│   │   ├── asr.py          # model loading + inference
│   │   └── diarize.py
│   ├── llm/
│   │   ├── base.py         # Summarizer protocol
│   │   ├── deepseek.py
│   │   ├── anthropic.py
│   │   └── prompts.py
│   ├── docgen/
│   │   ├── render.py       # MinutesJSON -> .docx
│   │   └── fonts/          # Sarabun-Regular.ttf, Sarabun-Bold.ttf
│   ├── audio.py            # ffmpeg wrapper, probe, normalize
│   └── thai.py             # tokenization, number/BE-date normalization
├── scripts/
│   └── gen_types.py        # Pydantic -> web/src/types.ts
├── tests/
└── web/
    ├── src/
    │   ├── pages/
    │   ├── components/
    │   ├── lib/api.ts
    │   ├── lib/i18n.ts
    │   └── types.ts        # GENERATED — do not hand-edit
    └── package.json
```

---

## 3. Tech stack — use exactly these

**Backend**
- Python 3.11+, `uv` for dependency management
- FastAPI + uvicorn (API), plain `python -m sarai.worker.main` (worker)
- **stdlib `sqlite3`** with a thin repository layer in `db.py`. WAL mode, `busy_timeout=5000`. No ORM — write SQL.
- Pydantic v2 for every boundary: HTTP bodies, DB row hydration, LLM output validation
- `transformers`, `torch`, `pyannote.audio` — **worker only**
- Model: `typhoon-ai/typhoon-whisper-turbo` (default), env override to `typhoon-ai/typhoon-whisper-large-v3` for higher accuracy at lower speed
- `python-docx` for document generation
- `pythainlp` for Thai tokenization and normalization
- `httpx` for LLM calls. `ruff` + `mypy --strict` in CI.

**Frontend**
- Vite + React 18 + TypeScript (strict mode)
- Tailwind CSS
- TanStack Query for server state
- No component library. Hand-build the components.
- `web/src/types.ts` is generated from the Pydantic models by `scripts/gen_types.py`. Wire it into the Makefile as `make types` and run it in CI to fail on drift.

---

## 4. Data model (SQLite)

```sql
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
```

**Queue semantics.** The worker claims a job with a single atomic statement:

```sql
UPDATE jobs SET claimed_by = ?, claimed_at = datetime('now')
WHERE id = (SELECT id FROM jobs
            WHERE stage = 'queued' AND claimed_at IS NULL
            ORDER BY updated_at LIMIT 1)
RETURNING *;
```

On worker startup, release any job whose `claimed_at` is older than 30 minutes — that's crash recovery. Poll every 2 seconds when idle.

`Segment` in `models.py`:

```python
class Segment(BaseModel):
    id: int
    start: float  # seconds
    end: float
    speaker: str  # "SPEAKER_00"
    text: str
    confidence: float | None = None
```

---

## 5. HTTP API

```
POST   /api/meetings                 multipart: file, title, meeting_date,
                                     language_hint, attendees[], glossary[]
                                     -> 201 {meeting_id, job_id}

GET    /api/meetings                 -> list, newest first
GET    /api/meetings/:id             -> meeting + job stage + has_transcript/has_summary

GET    /api/jobs/:id/events          -> SSE. Emits {stage, progress, detail, error}
                                        on change. Heartbeat every 15s.

GET    /api/meetings/:id/transcript  -> {segments, speakers}
PATCH  /api/meetings/:id/transcript  -> {segments} — full replace, sets edited=1
PATCH  /api/meetings/:id/speakers    -> {"SPEAKER_00": "คุณสมชาย", ...}

POST   /api/meetings/:id/summarize   -> enqueues summarize job, returns job_id
GET    /api/meetings/:id/summary     -> MinutesJSON
PATCH  /api/meetings/:id/summary     -> user edits, re-renders docx synchronously
GET    /api/meetings/:id/document    -> streams the .docx

DELETE /api/meetings/:id             -> removes DB rows and all files on disk
GET    /api/health                   -> {api, db, worker_heartbeat, llm}
```

**Uploads:** 500 MB limit, accept `.mp3 .m4a .wav .ogg .flac .mp4`. Stream to disk with `aiofiles` in chunks — never `await file.read()` on the whole thing, that will OOM the API process on a 3-hour recording.

**SSE:** the API polls the jobs table, it does not hold a connection to the worker. Async generator, `yield` on change, `asyncio.sleep(1)` between polls. Disconnect cleanly when the job reaches a terminal stage.

---

## 6. Transcription pipeline (worker)

Load the ASR and diarization models **once at worker startup** into module-level globals. Never per job.

**Stage order — this matters:**

1. `ffmpeg` → 16 kHz mono WAV.
2. Run `pyannote/speaker-diarization-3.1` on the full file for speaker turns.
3. Merge adjacent same-speaker turns less than 0.5s apart.
4. Split any turn longer than 30s at the nearest silence.
5. Transcribe **each turn separately** through Typhoon.
6. Write segments in chronological order.

Transcribing per-turn rather than transcribing the whole file and aligning speakers afterwards gives dramatically better speaker attribution, and it bounds the hallucination problem — Whisper-family models hallucinate on long silences, and per-turn slicing removes most silence from the input.

**Progress:** update `jobs.progress` and `jobs.detail` every 10 turns. The user is watching a stepper for several minutes; silence reads as a hang and they will re-upload.

**Hallucination guard:** drop any segment under 0.3s, or whose text repeats the same token run more than 3 times. Whisper produces "ครับ ครับ ครับ ครับ…" loops on near-silence.

---

## 7. LLM summarization

```python
class Summarizer(Protocol):
    async def summarize(self, inp: SummarizeInput) -> MinutesJSON: ...
```

Two implementations, selected by `LLM_PROVIDER`: `deepseek` (OpenAI-compatible endpoint) and `anthropic`. Both are text-only — audio never reaches them.

**Validation loop.** Parse the response with `MinutesJSON.model_validate_json()`. On `ValidationError`, retry once with the Pydantic error message appended to the prompt — models correct their own schema violations reliably when shown the error. Fail the job with a readable message after the second failure. Never return partial data silently.

**Map-reduce for long meetings.**
1. Under ~40k characters → single call.
2. Otherwise split into ~30k-character chunks **at segment boundaries, never mid-segment**, with 2 segments of overlap.
3. Summarize each chunk into a partial `MinutesJSON`.
4. Reduce: one final call merging the partials, deduplicating decisions, consolidating action items by owner.

### System prompt (use verbatim as the starting point)

```
You are an experienced Thai corporate secretary writing formal meeting minutes
(รายงานการประชุม). You receive a diarized transcript of a real meeting.

OUTPUT: valid JSON only. No markdown fences, no preamble, no explanation.

Schema:
{
  "title": string,
  "meeting_date": string | null,
  "attendees": [{"name": string, "role": string | null}],
  "summary": string,                 // 3-5 sentences, executive overview
  "agenda": [string],
  "discussion": [
    {"topic": string, "points": [string], "speakers": [string]}
  ],
  "decisions": [{"decision": string, "rationale": string | null}],
  "action_items": [
    {"task": string, "owner": string | null, "due": string | null,
     "source_quote": string}
  ],
  "open_questions": [string],
  "next_meeting": string | null
}

RULES — follow these strictly:

1. LANGUAGE: Write each field in the language that dominated that part of the
   discussion. Do NOT translate. If the meeting was conducted in Thai with
   English technical terms mixed in, preserve that mixture exactly as spoken.
   A Thai reader must recognize their own meeting.

2. NEVER INVENT. If no owner was named for an action item, use null. If no
   deadline was stated, use null. Do not guess. Do not infer an owner from
   who happened to be speaking.

3. EVIDENCE: every action_item must include "source_quote" — a short verbatim
   snippet from the transcript that justifies it. If you cannot find one, the
   action item does not belong in the list.

4. DECISIONS vs DISCUSSION: a decision is something the group concluded or
   committed to. "We should probably look into X" is discussion. "OK let's go
   with X, ตกลงตามนี้" is a decision. Be conservative.

5. NAMES: use the speaker labels provided. Correct obvious ASR misspellings of
   names and terms using the glossary provided. Do not correct anything else.

6. NOISE: ignore small talk, greetings, connection problems, and side
   conversations that carry no decision or information.
```

User message carries: attendee list, glossary, title/date if supplied, and the transcript as `[HH:MM:SS] SpeakerLabel: text` lines.

---

## 8. Document generation (`python-docx`)

Render `MinutesJSON` → `.docx`:

1. Title, meeting date, generation timestamp
2. ผู้เข้าร่วมประชุม / Attendees — two-column table
3. สรุปผู้บริหาร / Executive Summary
4. วาระการประชุม / Agenda — numbered
5. รายละเอียดการประชุม / Discussion — heading per topic, bulleted points
6. มติที่ประชุม / Decisions — numbered, rationale as sub-text
7. **สิ่งที่ต้องดำเนินการ / Action Items — three-column table (Task | Owner | Due).** This is the section people actually read. Page break before it if the doc is long.
8. ประเด็นค้าง / Open Questions
9. Footer: `Generated by Sarai AI` + model name + timestamp

### Thai font — do not skip this

`python-docx` does not set complex-script attributes for you. For **every** run:

```python
run.font.name = "Sarabun"
rpr = run._element.get_or_add_rPr()
rfonts = rpr.get_or_add_rFonts()
rfonts.set(qn("w:ascii"), "Sarabun")
rfonts.set(qn("w:hAnsi"), "Sarabun")
rfonts.set(qn("w:cs"), "Sarabun")  # complex script — REQUIRED for Thai
```

Set `w:szCs` alongside `w:sz` too, or Thai renders at the wrong point size. Write one `styled_run()` helper and route every piece of text through it — do not repeat this by hand.

Ship `Sarabun-Regular.ttf` and `Sarabun-Bold.ttf` in `sarai/docgen/fonts/` (Open Font License) and embed them so the file renders on machines without the font installed.

---

## 9. Frontend screens

Bilingual UI (Thai default, English toggle, persisted in localStorage). Sarabun for Thai, Inter for English.

**`/` — Meetings list.** Title, date, duration, stage badge, actions. Empty state with a prominent upload CTA.

**`/new` — Upload.** Drag-and-drop, then: title, meeting date, language (auto/ไทย/English), attendees (repeatable name+role rows), glossary (chip input for project names, codenames, acronyms). Helper text should explain that the glossary materially improves name accuracy — users skip it otherwise.

**`/meetings/:id` — Processing.** Subscribe to SSE. Stage stepper: Normalizing → Diarizing → Transcribing → Ready for review. Show elapsed time and `n/total segments`.

**`/meetings/:id/review` — Transcript editor.** *The most important screen.*
- Segment list: timestamp, speaker dropdown, editable text
- Speaker legend at top: rename `SPEAKER_00` once, propagates everywhere
- Audio player pinned to bottom; clicking a segment seeks to that timestamp; playing segment highlighted
- Debounced autosave on blur
- Prominent "Generate Minutes" button

**`/meetings/:id/summary` — Review & export.** Structured JSON rendered as editable sections, action items as an editable table, "Download .docx" and "Regenerate".

---

## 10. Thai-language requirements

Correctness requirements, not polish:

- **Never split Thai text on spaces.** Thai has no word boundaries. Any truncation, chunking, or preview logic uses character counts or `pythainlp.word_tokenize`.
- **Code-switching must survive.** Test with Thai sentences containing English nouns. If the ASR transliterates "deploy" into Thai script, or the LLM translates Thai into English in the output, that is a bug.
- **Numbers.** Thai number verbalization is context-dependent ("สองพันห้า" → 2,500). Instruct the LLM to normalize spoken numbers to digits in decisions and action items, where a wrong figure has consequences.
- **ไม้ยมก (ๆ).** The repetition marker is frequently mis-transcribed. Normalization pass in `thai.py` for common cases.
- **Buddhist era dates.** "ปี 2569" means CE 2026. Convert BE→CE when parsing; treat any year above 2500 as BE.

---

## 11. Build phases

Complete, verify, report. Then continue.

**Phase 0 — Skeleton.** Repo structure, `pyproject.toml` with `api`/`worker`/`dev` dependency groups (torch **only** in `worker`), docker-compose, Makefile, health endpoints, Vite proxying `/api`, `scripts/gen_types.py` working end to end.
*Verify:* `make dev` brings up API + worker + web; `/api/health` shows a recent worker heartbeat; `make types` regenerates `web/src/types.ts`.

**Phase 1 — Upload + storage.** Streaming upload, ffmpeg normalization to 16 kHz mono WAV, duration probe, meetings CRUD, upload UI.
*Verify:* upload an mp3, normalized wav appears in `data/work/`, meeting listed with correct duration, API RSS stays flat during a 300 MB upload.

**Phase 2 — ASR.** Model loading at worker startup, diarization, per-turn transcription, hallucination guard.
*Verify:* a 2-minute Thai clip produces sensible segments with 2+ distinct speakers. Note cold-start time in the README.

**Phase 3 — Job pipeline.** Atomic claim, retry with backoff, stale-claim recovery, SSE endpoint, processing UI.
*Verify:* upload → stages advance live in the browser → lands in `awaiting_review`. Kill the worker mid-job; on restart the job is reclaimed and completes.

**Phase 4 — Transcript review.** Editor, speaker renaming, audio player with seek-on-click, autosave.
*Verify:* rename `SPEAKER_00`, edit a segment, reload, changes persisted.

**Phase 5 — Summarization.** Both providers, map-reduce chunking, Pydantic validation with retry, summary review UI.
*Verify:* generate minutes from a real meeting; every action item's `source_quote` actually appears in the transcript. Assert this in a test.

**Phase 6 — Document generation.** `python-docx` renderer with Sarabun embedding and complex-script attributes.
*Verify:* open the output in Microsoft Word **and** LibreOffice on a machine without Sarabun installed. Thai renders correctly in both. This is the check people skip and regret.

**Phase 7 — Hardening.** Delete with file cleanup, disk quota check before accepting uploads, graceful shutdown draining in-flight jobs, structured logging with job IDs, README with GPU requirements and setup.

---

## 12. Do not

- Do not import `torch` anywhere reachable from the API process. Add a test that greps `sarai/api/` for it.
- Do not add authentication in the first pass. Single-tenant on a trusted network. Note in the README where auth would attach.
- Do not add Redis, Celery, or RQ. The jobs table plus a polling worker handles this workload for years, and it means one less service to run.
- Do not use an ORM. Do not add Alembic — plain numbered SQL migration files applied at startup.
- Do not use `asyncio` inside the worker for the ML stages. They are CPU/GPU-bound and synchronous; async buys nothing and complicates debugging.
- Do not send audio to any third-party API under any circumstance.
- Do not let the LLM produce the final document text directly. JSON in the middle, always.
- Do not swallow errors. Every failure path surfaces a message the user can act on.
- Do not write frontend tests in this pass. Do write pytest coverage for `docgen`, the map-reduce chunker, `thai.py` normalization, and the job claim logic — that is where subtle bugs hide.

---

## 13. Ask me before you start

1. Is there a GPU available, and how much VRAM? (Determines Turbo vs Large-v3 as default.)
2. DeepSeek or Anthropic as the default summarizer?
3. Is a HuggingFace token available? `pyannote/speaker-diarization-3.1` is gated and requires accepting the license.
4. Deployment target — bare metal, single Docker host, or Kubernetes?