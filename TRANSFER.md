# TRANSFER — read this first

Instructions for the Claude Code session on the destination PC. This project was
built on a Mac and is being moved. Nothing here overrides `SPEC.md`, which is
still the authority on architecture and phases; `README.md` is the authority on
what is built and what was measured.

Do not start writing Phase 4 code until the checklist below is done and
`make check` passes on the new machine.

---

## 1. What this project is

Sarai AI — self-hosted Thai/English meeting minutes. Upload a recording →
local ASR + diarization → transcript review → LLM summary → `.docx`.

Two processes, one codebase: FastAPI API (never imports torch) and a synchronous
worker (torch, pyannote, ffmpeg). SQLite in WAL is both the database and the job
queue. React/Vite frontend on :5173 proxying `/api` to :8000.

**Non-negotiable:** audio never leaves the network. Only transcript *text* goes
to an LLM. See `SPEC.md` §12 for the rest of the "do not" list.

## 2. State at the moment of transfer

| Phase | Scope | State |
|-------|-------|-------|
| 0 | Skeleton, config, DB, migrations, health, type generation, docker | done |
| 1 | Streaming upload, ffmpeg normalization, meetings CRUD, upload UI | done |
| 2 | ASR, diarization, per-turn transcription, hallucination guard | done |
| 3 | SSE progress, retry, crash recovery, processing UI | done (see caveat) |
| 4 | Transcript review editor | **next** |
| 5 | Summarization (DeepSeek default, Anthropic second) | not started |
| 6 | `.docx` with Sarabun embedding | not started |
| 7 | Hardening | partly |

Green on the Mac at transfer time: **92 pytest**, `mypy --strict`, `ruff`,
`ruff format --check`, `gen_types.py --check`, web `tsc`.

### Phase 3 caveat — one verification is unfinished

Phase 3's own verify steps passed:

- Live SSE frames confirmed over `curl -N` and in Chrome on a real job:
  stepper advanced, progress bar moved, elapsed timer ticked, no console errors.
- Kill-mid-job recovery confirmed: `pkill -9` the worker during diarization,
  restart, the job was requeued and re-ran from `normalizing`.

**Not finished:** the end-to-end run of the real 92-minute recording. It was
still in the diarization stage when the session was interrupted, so no real
human recording has ever reached `awaiting_review`. Diarization of 92 minutes
on Apple CPU was still going after ~10 minutes; a CUDA box should be much
faster. **Redo this on the PC** — see §6.

### Two real bugs were found and fixed during Phase 3 (do not undo them)

1. **Restart recovery.** The 30-minute stale-claim sweep alone meant a worker
   that crashed and restarted immediately left its job `claimed` and unpickable
   for half an hour. `worker.main.recover_local_claims` now requeues this host's
   claims whose pid is dead (`kill(pid, 0)`), so a second worker on the same
   host keeps the job it is actually running. Covered by
   `tests/test_worker_recovery.py`.
2. **Heartbeat.** `db.beat` used to run at the top of the claim loop, so during
   a 90-minute transcription the API reported the worker dead and the UI showed
   the "no worker running" banner while the progress bar was moving. It is now a
   daemon thread beating every 10 s on its own connection. Covered by
   `tests/test_worker_heartbeat.py`.

---

## 3. What to copy, what to leave behind

Copy the project directory **without** these — they are large, machine-specific,
or private:

```
.venv/            rebuild with uv on the PC
node_modules/     rebuild with npm ci
data/             ~261 MB of uploads, wavs and the SQLite file. Local state.
sample/           82 MB private meeting recording. See below.
.mypy_cache/ .pytest_cache/ .ruff_cache/ web/dist/ __pycache__/
.env              secrets — move by hand, see §4
```

`sample/` holds a real recorded call with a named participant. It is now in
`.gitignore` and must never be committed or uploaded anywhere. Move it by hand
(USB, direct copy) if the PC needs it for verification, or re-export it from
the original source on the PC.

Everything else — `sarai/`, `web/`, `tests/`, `scripts/`, `docker/`, `SPEC.md`,
`README.md`, `Makefile`, `pyproject.toml`, `uv.lock`, `.github/` — transfers.

## 4. Secrets

`.env` is gitignored and is **not** part of the transfer bundle. On the PC:

```bash
cp .env.example .env
```

Then fill in by hand, from the values on the Mac:

| Key | Needed for | Notes |
|-----|-----------|-------|
| `HF_TOKEN` | diarization | Two HuggingFace gates must be accepted with the same account — see README "Requirements". Missing it degrades to single-speaker, it does not crash. |
| `DEEPSEEK_API_KEY` | Phase 5 summarizer | default provider |
| `ANTHROPIC_API_KEY` | Phase 5 summarizer | optional second provider |

The Mac `.env` also carries a `TYPHOON_API` key. It is **deliberately unused**:
Typhoon's hosted ASR would send audio off the network, which violates the
project's one hard rule. Their OpenAI-compatible *text* endpoint would be an
acceptable third Phase 5 summarizer, but the user has not asked for it — ask
before wiring it.

Never print, echo, or commit any of these values.

## 5. Set up on the PC and push to GitHub

The repo **is already under git** and travels with its history. One commit on
`main`, remote `origin` already set to
`https://github.com/Krist-Kul/sarai-ai.git`. Nothing has been pushed yet.

Copy the `.git/` directory along with the working tree, or the history is lost
and you are back to `git init`.

### 5.1 Install

```bash
uv sync --group api --group dev        # API + tooling, no torch
cd web && npm install && cd ..
uv sync --group api --group worker --group dev   # adds torch/pyannote, several GB
```

`ffmpeg` and `ffprobe` must be on `PATH`.

**If the PC is Windows:** the `Makefile` targets are bash and assume a POSIX
shell. Either work inside WSL2 (recommended — ffmpeg and uv behave normally
there) or run the underlying commands directly:

```
uv run uvicorn sarai.api.main:app --reload --port 8000
uv run python -m sarai.worker.main
cd web && npm run dev
```

`worker.main` uses `os.kill(pid, 0)` for crash recovery, which works on Windows
Python as well, but the whole stack has only ever been exercised on macOS/Linux.
If anything platform-specific breaks, say so rather than papering over it.

**GPU:** `ASR_DEVICE=auto` picks cuda → mps → cpu. On an NVIDIA PC this should
land on cuda; confirm with the worker's startup log line
(`ASR model ready on cuda`). ~6 GB VRAM for `typhoon-whisper-turbo`, ~12 GB for
`typhoon-whisper-large-v3` (`ASR_MODEL` env override).

### 5.2 Verify before committing anything

```bash
make check      # ruff, mypy --strict, types drift, pytest, web tsc
```

All of it must be green. 92 tests at time of writing.

### 5.3 Push

Re-check the ignore rules on the new machine before pushing — this is the step
where secrets or the 82 MB private recording would leak:

```bash
git status --short                     # should be clean, or only intended changes
git ls-files | grep -iE "\.env$|^data/|^sample/|\.mp4$|\.mp3$|\.wav$"
# must print nothing
```

If anything shows up there, stop and fix it before pushing — a secret in a
pushed commit is not fixed by a later commit that removes it.

Then:

```bash
git push -u origin main
```

Ask the user before pushing. Pushing publishes the code to their account, and
it is their call, not yours.

`.github/workflows/ci.yml` runs on push. Note it installs only the `api` and
`dev` groups, while several tests import `numpy` through `sarai.worker.*`. If
CI fails on that import, the fix is to add `numpy` to the `dev` group (not to
weaken the tests, and **not** to add torch to `api` — `tests/test_no_torch_in_api.py`
exists to prevent exactly that).

## 6. Finish the Phase 3 verification on the PC

The one outstanding item. With API + worker + web running:

1. Upload the real recording through the UI at `/new` (or `curl -F` against
   `POST /api/meetings`).
2. Watch `/meetings/:id`. Expected: the stepper advances
   Normalizing → Diarizing → Transcribing → Ready for review, the progress bar
   and `n/total turns` update live, the elapsed timer ticks, and the "live"
   indicator stays on. The page must never fall back to polling
   (`liveLost` string) unless the API is actually down.
3. It must land in `awaiting_review` with a real segment count.

Then record in `README.md` (Testing notes) what the Phase 2 note does for the
synthetic clip: duration, wall time, number of turns, number of speakers, and a
judgement on speaker attribution and Thai/English code-switching quality.

If diarization is implausibly slow on the PC too, check whether pyannote landed
on CPU — the worker logs `diarization model ready on <device>` at startup, and
on the Mac it was CPU while ASR was on mps.

## 7. Then: Phase 4

`SPEC.md` §11: transcript review editor. Segment list with timestamps, speaker
dropdowns and editable text; speaker legend where renaming `SPEAKER_00` once
propagates; audio player pinned to the bottom with click-a-segment-to-seek;
debounced autosave; "Generate Minutes" button. Backend endpoints
`GET/PATCH /api/meetings/:id/transcript` and `PATCH /api/meetings/:id/speakers`
are specified in `SPEC.md` §5 and **not yet built** — the DB layer for them
(`db.get_transcript`, `db.save_transcript`, `db.save_speakers`) already exists.

Verify: rename `SPEAKER_00`, edit a segment, reload, changes persisted.

Work one phase at a time. Complete it, run its verify steps, report, stop.

## 8. House rules that are easy to trip over

- `web/src/types.ts` is generated from `sarai/models.py`. Never hand-edit;
  run `make types`. CI fails on drift.
- The API must never import torch. `tests/test_no_torch_in_api.py` enforces it.
- No ORM, no Alembic — numbered SQL files in `sarai/migrations/`, applied at
  startup.
- No Redis/Celery/RQ. The jobs table is the queue.
- No `asyncio` in the worker's ML stages. They are synchronous on purpose.
- Never split Thai text on spaces. Thai has no word boundaries — use character
  counts or `pythainlp.word_tokenize`.
- Frontend tests are deliberately out of scope for this pass. Python tests are
  not: `docgen`, the map-reduce chunker, `thai.py` and the job claim logic all
  need coverage as they are built.
