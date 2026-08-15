# Sarai AI

Self-hosted meeting minutes for Thai, English, and Thai-English code-switched
meetings. Upload a recording, review the transcript and fix the speaker names,
then generate a structured summary that renders to an editable `.docx`.

**Audio never leaves your network.** Transcription runs locally on your own GPU.
Only the *text* transcript is sent to an LLM for summarization, and that can be
turned off entirely with `LLM_ENABLED=false`.

## Build status

| Phase | Scope | State |
|-------|-------|-------|
| 0 | Skeleton: repo layout, config, DB + migrations, health, type generation, docker | done |
| 1 | Upload + storage: streaming upload, ffmpeg normalization, duration probe, meetings CRUD, upload UI | done |
| 2 | ASR: model loading, diarization, per-turn transcription, hallucination guard | done |
| 3 | Job pipeline: SSE progress, retry, crash recovery UI | done |
| 4 | Transcript review editor | not started |
| 5 | Summarization (DeepSeek / Anthropic) | not started |
| 6 | `.docx` generation with Sarabun | not started |
| 7 | Hardening | partly (delete + disk quota + graceful shutdown exist) |

A transcribe job runs end to end today: normalize → diarize → transcribe →
`awaiting_review`. Summarization still fails with `Summarization is not built
yet (Phase 5)` — deliberate, so a job never reports success it did not achieve.

## Architecture

Two processes, one Python codebase, one set of Pydantic models.

```
web (React/TS, :5173) ──HTTP/JSON──> api (FastAPI, :8000) ──> SQLite (WAL)
                                                                  ^
                                                                  | claim/update
                                                            worker (torch, ffmpeg)
```

- The **jobs table is the queue**. No Redis, no Celery. The worker claims a job
  with one atomic `UPDATE ... RETURNING` and polls every 2 s when idle.
- **Crash recovery has two halves.** A claim older than 30 minutes is swept on
  startup — that covers a host that vanished. A worker that crashed and came
  straight back instead requeues its own claims immediately, checking each
  claiming pid with `kill(pid, 0)` so a second worker on the same host keeps the
  job it is actually running. Without that half, a restart within the 30-minute
  window strands the job in `claimed` where nothing will ever pick it up.
- The **API never imports torch** — enforced by `tests/test_no_torch_in_api.py`,
  which walks the import graph and also asserts a fresh interpreter that imports
  the app has no ML modules loaded.
- `sarai/models.py` is the single source of truth. `make types` regenerates
  `web/src/types.ts`; CI fails on drift.

## Requirements

- Python 3.11+, [uv](https://docs.astral.sh/uv/)
- Node 20+
- `ffmpeg` and `ffprobe` on `PATH`
- For Phase 2 onward: a GPU. ~6 GB VRAM for `typhoon-whisper-turbo`, ~12 GB for
  `typhoon-whisper-large-v3`. `ASR_DEVICE=auto` picks cuda, then mps, then cpu;
  CPU works but runs at roughly real time or slower.
- A HuggingFace token for diarization, and **two licenses accepted with that
  same account** — the pipeline pulls a separate segmentation model, and the two
  repos are gated independently:
  - <https://huggingface.co/pyannote/speaker-diarization-community-1>
  - <https://huggingface.co/pyannote/segmentation-3.0>

  `pyannote.audio` 4.x redirects the older `speaker-diarization-3.1` name to
  `community-1`, so a 403 can name a repo you never put in your config. The
  default `DIARIZATION_MODEL` names `community-1` directly to keep that visible.

  Missing either one degrades to single-speaker mode: you still get a full
  transcript, every segment labelled `SPEAKER_00`, and a loud error in the
  worker log naming both URLs. The worker does not refuse to start.

## Quick start

```bash
cp .env.example .env      # then edit
make install              # API + dev deps and the frontend (no torch)
make dev                  # api :8000, worker, web :5173
```

`make install-worker` adds torch, transformers and pyannote — several GB, and
only needed once you are running transcription.

Check it came up:

```bash
curl localhost:8000/api/health
# {"api":true,"db":true,"worker_heartbeat":"...","worker_alive":true,"llm":"deepseek"}
```

`worker_alive` is false when the last heartbeat is over 30 s old; the web UI
shows a banner in that case, so a queue that is not moving is never a mystery.
The beat runs on its own thread inside the worker, so it keeps landing during a
90-minute transcription — beating only between jobs made the UI declare the
worker dead exactly while it was busiest.

## Common commands

| Command | What it does |
|---------|--------------|
| `make dev` | API + worker + web together |
| `make api` / `make worker` / `make web` | one process at a time |
| `make types` | regenerate `web/src/types.ts` from the Pydantic models |
| `make test` | pytest |
| `make lint` | ruff + `mypy --strict` |
| `make check` | everything CI runs |
| `make up` | docker compose (single host, GPU passthrough on the worker) |

## Transcription

The worker loads Typhoon Whisper and pyannote once at startup, never per job.
Measured cold start on an M-series Mac (`ASR_DEVICE=auto` → mps): **~50 s on the
first run** including the model download, **~15 s** warm from the HF cache. A
CUDA box with the weights cached is faster; a cold CPU-only box is slower.

Stage order, and why:

1. `ffmpeg` → 16 kHz mono WAV.
2. pyannote diarizes the whole file into speaker turns.
3. Turns by the same speaker less than 0.5 s apart are merged — diarization
   splits on breaths, and transcribing fragments loses sentence context.
4. Turns over 30 s are split at their quietest point, found from an RMS
   envelope. Cutting at silence costs nothing; cutting mid-word costs a word.
5. Each turn is transcribed separately. This is what makes speaker attribution
   correct by construction, and it keeps long silences — the thing that makes
   Whisper hallucinate — out of the model's input entirely.
6. The guard drops any segment under 0.3 s, empty or boilerplate output
   ("Thanks for watching!"), and repetition loops. Loops are checked twice: on
   whitespace tokens for English, and on character n-grams for Thai, which has
   no word boundaries and so produces "ครับครับครับครับ" as one string.

`progress` and `detail` are written every 10 turns. Per-segment confidence comes
from the mean token logprob and is stored for the review UI.

### The glossary is fed to Whisper, not just the LLM

Whisper transliterates unfamiliar English into Thai script — "deploy" comes back
as "ดิโปรย", which no downstream step can reliably tell from a real Thai word.
The glossary (plus attendee names) is therefore used as Whisper's prompt prefix,
which biases decoding toward those spellings. Measured on the test clip, same
audio, same model:

| glossary | result |
|----------|--------|
| empty | `ผมขอเริ่มที่เรื่องดิโปรยระบบใหม่ก่อนนะครับตอนนี้คิวเอ้ยังไม่ผ่าน` |
| `deploy, QA, server` | `ผมขอเริ่มที่เรื่อง deploy ระบบใหม่ก่อนนะครับ ตอนนี้ QA ยังไม่ผ่าน` |

It is a bias, not a guarantee — a term the speaker pronounces with heavy Thai
phonology can still come back transliterated. The glossary is passed to the
summarizer as well, and the reviewer can fix anything left over in Phase 4.

### Two things pyannote 4.x will bite you with

- It **redirects** `speaker-diarization-3.1` to `speaker-diarization-community-1`,
  so a 403 names a repo you never configured. `DIARIZATION_MODEL` defaults to
  the real name for that reason.
- Handed a file path, it decodes through **torchcodec**, which links against
  whichever FFmpeg build it finds and dies if that is not the one on `PATH`.
  We pass the already-decoded waveform instead — one less decode, and one less
  fragile native dependency.
- Its result is a `DiarizeOutput`, not an `Annotation`. We read
  `exclusive_speaker_diarization` from it: the overlapping variant assigns
  simultaneous speech to several speakers, which would send the same audio
  through ASR once per speaker.

## Configuration

Every setting is an environment variable; see `.env.example` for the full list
with comments. The ones that matter most:

| Variable | Default | Notes |
|----------|---------|-------|
| `DATA_DIR` | `./data` | uploads, normalized wavs, docs and the SQLite file |
| `ASR_MODEL` | `typhoon-ai/typhoon-whisper-turbo` | set to `typhoon-ai/typhoon-whisper-large-v3` for accuracy over speed |
| `ASR_DEVICE` | `auto` | `auto` \| `cuda` \| `mps` \| `cpu` |
| `HF_TOKEN` | unset | required for diarization |
| `LLM_ENABLED` | `true` | `false` disables third-party summarization entirely |
| `LLM_PROVIDER` | `deepseek` | `deepseek` \| `anthropic` |
| `UPLOAD_MAX_BYTES` | 500 MB | enforced while streaming, not after |
| `MIN_FREE_DISK_BYTES` | 5 GB | uploads are rejected below this |

## Storage layout

```
data/
├── sarai.db                    SQLite (WAL)
├── uploads/<meeting_id><ext>   original upload, kept for playback
├── work/<meeting_id>.wav       16 kHz mono, what the models read
└── docs/<meeting_id>.docx      rendered minutes
```

Paths are derived from the meeting id, never from the uploaded filename.
`DELETE /api/meetings/:id` removes the rows and every file above.

## API

```
POST   /api/meetings                 multipart upload -> 201 {meeting_id, job_id}
GET    /api/meetings                 list, newest first
GET    /api/meetings/:id             meeting + job stage + has_transcript/has_summary
GET    /api/meetings/:id/audio       original file, for the review player
GET    /api/jobs/:id/events          SSE: {job_id, stage, progress, detail, error}
DELETE /api/meetings/:id             rows + files
GET    /api/health                   {api, db, worker_heartbeat, worker_alive, llm}
```

Transcript, summary and document endpoints arrive in phases 4-6.

### Live progress

The API polls the jobs table once a second and yields a frame when anything
changes; it holds no connection to the worker. That keeps the worker a plain
synchronous process, lets a restarted API pick up an in-flight job with no
coordination, and costs one SELECT per second per watcher.

```
event: job     {JobEvent}     on change
event: end     {JobEvent}     terminal stage, then the server closes
event: gone    {detail}       the job row was deleted mid-stream
: heartbeat                   comment frame every 15 s
```

The client **must** close its `EventSource` on `end` and `gone`. (`gone`
rather than `error`: a server-sent `error` event arrives on the same listener
EventSource uses for transport failures, and those two mean opposite things.) EventSource
reconnects on any close it did not initiate, so a finished job would otherwise
reopen the stream forever. `useJobEvents` does this, retries three times on
transport failures, and then reports `lost` — at which point the meeting page
falls back to polling. The two never run at once.

## Authentication

There is none, by design: single-tenant on a trusted network. If you need it,
the attachment point is `create_app()` in `sarai/api/main.py` — add auth
middleware there and a `Depends` guard in `sarai/api/deps.py`. Do not expose
this to the internet without it; `/api/meetings/:id/audio` serves raw meeting
recordings to anyone who can reach the port.

## Testing notes

`pytest` covers the job claim protocol (exclusivity, FIFO, stale-claim
recovery), the ffmpeg wrapper, upload limits and cleanup, Thai round-tripping
through SQLite, and type-generation drift. Each test gets its own `DATA_DIR`.

Model-dependent code is covered with the models stubbed: `test_transcribe_stage.py`
checks ordering, the guard, progress and what reaches the database without
loading several GB of weights.

Verified by hand on Phase 1: a 300 MB upload holds the API process flat at
~20 MB RSS, because the handler streams to disk in 1 MiB chunks.

Verified by hand on Phase 2: a 41 s Thai clip of two alternating speakers
produces 6 segments with **6/6 correct speaker attribution**, Thai transcribed
correctly, code-switching preserved when the terms are in the glossary, at
0.94-1.00 mean confidence.
