# Sarai AI

Self-hosted meeting minutes for Thai, English, and Thai-English code-switched
meetings. Upload a recording, review the transcript and fix the speaker names,
then generate a structured summary that renders to an editable `.docx`.

**Audio never leaves your network.** Transcription runs locally on your own GPU.
Only the *text* transcript is sent to an LLM for summarization, and that can be
turned off entirely with `LLM_ENABLED=false`.

> **Hands-off flow.** The upload form asks for the recording, a title, the
> date and time and, optionally, who was there. Everything after that is
> automatic: transcription, then one LLM call that detects the meeting type and
> names each diarized speaker (`sarai/llm/analyze.py`), then the summary, ending
> in a `.docx` and a PDF. A speaker is only named when a verbatim quote in the
> transcript supports it; anyone else becomes `ผู้พูด 1`, `ผู้พูด 2`, ... The PDF
> is rendered with WeasyPrint, which needs Pango on the host
> (`libpango-1.0-0 libpangoft2-1.0-0 libthai0` on Debian/Ubuntu).
>
> **Meeting types.** Each meeting has a type — `general` (default),
> `executive`, `standup`, `lecture`, `interview` or `workshop` — detected from
> the transcript and changeable on the review screen before regenerating. The type sets
> the summarizer's persona, what the summary is for, which sections it leans
> on, and the summary/discussion headings in the editor and `.docx`
> (`sarai/meeting_types.py`). The `MinutesJSON` schema and the evidence rules
> (no invented owners, verbatim source quotes) are the same for every type.
> Meetings created before types existed are treated as `executive`.

## Build status

| Phase | Scope | State |
|-------|-------|-------|
| 0 | Skeleton: repo layout, config, DB + migrations, health, type generation, docker | done |
| 1 | Upload + storage: streaming upload, ffmpeg normalization, duration probe, meetings CRUD, upload UI | done |
| 2 | ASR: model loading, diarization, per-turn transcription, hallucination guard | done |
| 3 | Job pipeline: SSE progress, retry, crash recovery UI | done |
| 4 | Transcript review editor | done |
| 5 | Summarization (DeepSeek / Anthropic / Gemini) | done |
| 6 | `.docx` generation with Sarabun | done (font files fetched separately, see below) |
| 7 | Hardening | partly (delete + disk quota + graceful shutdown exist) |

Both jobs run end to end today. Transcribe: normalize → diarize → transcribe →
`awaiting_review`. Summarize: `summarizing` → `rendering` → `done`, leaving a
`.docx` on disk. The review screen sits between them, and nothing is sent to a
summarizer until a human presses the button on it.

**Fonts are not in the repo.** `.docx` files name Sarabun either way, but they
only *carry* it once you run:

```bash
uv run python scripts/fetch_fonts.py     # ~500 KB, OFL, from Google Fonts
```

Without it Thai renders correctly on machines that have Sarabun installed and
falls back to a substitute font everywhere else.

## Example output

[`examples/parliament-question-time`](examples/parliament-question-time/) holds
minutes generated from a recorded Thai House of Representatives session, as
`.docx` and Markdown. It is unedited machine output with known errors; read the
disclaimer there before using it.

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
  CPU works but runs at roughly real time or slower. On Apple Silicon the worker
  switches to MLX on its own — see below.
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
cp .env.example .env.local   # then edit
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

### Two backends, chosen by the hardware

Same weights, two runtimes. `ASR_BACKEND=auto` picks between them at startup:

| machine | backend | model |
|---------|---------|-------|
| CUDA GPU | transformers | `ASR_MODEL` |
| Apple Silicon, no CUDA | MLX | `ASR_MODEL_MLX` |
| anything else (CPU) | transformers | `ASR_MODEL` |

The trigger is the resolved torch device, not the OS: `mps` is only ever
resolved on Apple Silicon without CUDA, which is exactly the machine MLX exists
for. Pinning `ASR_DEVICE` to `cuda` or `cpu` therefore keeps transformers by
construction, and `ASR_BACKEND=transformers|mlx` overrides the lot.

MLX is worth the second code path: transformers-on-mps falls back to CPU for
several Whisper ops, MLX does not. Measured on an M-series Mac against a real
Thai recording, `chayapats/typhoon-whisper-turbo-mlx` transcribed a 15 s turn in
**2.9 s** — roughly 5× real time — at 0.96 mean confidence.

`mlx-whisper` installs only on Apple Silicon (the dependency carries a
`sys_platform == 'darwin' and platform_machine == 'arm64'` marker). Where it is
absent the worker logs a warning once and falls back to transformers on mps, so
a Mac without it still transcribes — just slowly.

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
summarizer as well, and the reviewer can fix anything left over on the review
screen.

## Summarization

The transcript goes out as text and comes back as `MinutesJSON`. Nothing else
about the meeting leaves the machine, and the audio never does.

- **Under 40k characters, one call.** Longer meetings are split at *segment*
  boundaries — never mid-segment, and never on spaces, which do not mark words
  in Thai — with two segments of overlap so a decision spoken across a seam is
  not lost, then reduced by a final merge call.
- **Two chances at the schema.** The response is parsed with
  `MinutesJSON.model_validate_json()`; on a `ValidationError` the model is asked
  again *with its own validation error appended*, which it corrects reliably.
  A second failure fails the job with the validator's message rather than
  saving partial minutes.
- **Every action item must quote the transcript.** `source_quote` is checked
  against the transcript (whitespace-insensitive, since Thai spacing is
  arbitrary) and items whose quote is not there are dropped, with a count
  reported on the job. An invented quote is an invented commitment, and someone
  being assigned work they never agreed to is the worst output this system
  could produce.
- **A refusal or a missing key fails immediately.** Those are `StageFailed`,
  not retried three times, because the answer will not change in a minute and
  the message is what the user needs.

## Document generation

`python-docx` sets `w:ascii` and `w:hAnsi` when you assign a font, and stops
there. Thai is a complex script: without `w:cs` Word substitutes its own font,
and without `w:szCs` it renders at the wrong point size. Every run in the
document therefore goes through one `styled_run()` helper that sets all four —
this is the check that is invisible on a developer machine with Sarabun
installed, and obvious to everyone else.

When `scripts/fetch_fonts.py` has been run, the TTFs are also embedded as
obfuscated `.odttf` parts (ECMA-376 §17.8.1 — a fixed XOR against a GUID, which
Word and LibreOffice both read) so the file renders on a machine with no Thai
font at all.

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

### Optional: SUPlime-L diarization (non-commercial only)

[`rewayai/suplime-large`](https://huggingface.co/rewayai/suplime-large) is an
alternative pyannote 4.x pipeline (WavLM-Large segmentation, up to 4 speakers
per 10 s window, at most 2 at once). It is opt-in and never the default.

> **License:** its weights are **CC BY-NC 4.0 — non-commercial use only**. Sarai
> itself is MIT, but a worker running SUPlime-L must not be used for commercial
> work. The worker logs a warning at startup whenever it is selected.

Enable it:

```bash
make install-suplime   # = uv sync --group api --group worker --group dev --extra suplime
```

then in `.env.local`:

```
DIARIZATION_MODEL=rewayai/suplime-large
```

- **HF_TOKEN is still required.** The repo is gated with automatic approval:
  open the model page once with the account that issued `HF_TOKEN` and accept.
  It does not need the two pyannote gates above.
- **Missing package fails loudly.** If `suplime` is not installed, the worker
  refuses to start (and a job fails at once) with an error naming the install
  command. It does not fall back to `SPEAKER_00`. A failed download or a
  missing token still falls back, as for the default model.
- `make install-worker` syncs exactly the listed groups, so running it later
  **removes** `suplime` again. Use `make install-suplime` instead.
- Its output carries `exclusive_speaker_diarization` (the pipeline subclasses
  pyannote's `SpeakerDiarization`), so turns flow into ASR exactly as with the
  default model.
- Training data is mostly English and Mandarin, with no Thai. Measure it on your
  own recordings before switching — see below.

Hardware, measured on an RTX 5070 (12 GB) and a 16-thread CPU, warm model:

| | community-1 | SUPlime-L |
|---|---|---|
| CUDA, real-time factor | 0.017 | 0.087 (~5× slower) |
| CUDA, peak VRAM | 2.7 GB | 8.5 GB |
| CPU, real-time factor | — | ~3 (30 s of audio took 88 s) |

- **CUDA** works and is the only setup the model card covers. The WavLM
  backbone runs under fp16 autocast; `SUPLIME_FP16=0` forces fp32 (more VRAM).
  It needs about 8.5 GB of free VRAM next to the ASR model, so a 12 GB card is
  tight and 8 GB cards will not fit both.
- **CPU** works but is about three times slower than real time — an hour-long
  meeting takes about three hours to diarize. Usable only for testing.
- **Apple Silicon (mps)** has not been tested. fp16 autocast is CUDA-only, so
  it would run in fp32. If an op fails on mps, the existing mps → cpu fallback
  takes over, at CPU speed. Run the evaluation below on the Mac before relying
  on it.

### Comparing diarization models on your recordings

`scripts/eval_diarization.py` runs each model over a folder of recordings with
hand-labelled RTTM references and reports DER (0 s collar, overlap scored, no
oracle speaker count), missed speech, false alarm, confusion, speaker-count
accuracy, wall-clock time and peak VRAM per file, plus a macro average, as CSV
and on stdout. Its docstring explains how to make the RTTM files with Audacity.

```bash
make install-suplime
uv run python scripts/eval_diarization.py path/to/eval-set \
    --out results/diarization.csv --save-rttm results/hyp
```

`--models` defaults to `community-1 suplime-large`; `--output regular` scores
the overlap-aware annotation instead of the exclusive one the worker uses.

## Configuration

Every setting is an environment variable; see `.env.example` for the full list
with comments. The ones that matter most:

| Variable | Default | Notes |
|----------|---------|-------|
| `DATA_DIR` | `./data` | uploads, normalized wavs, docs and the SQLite file |
| `ASR_MODEL` | `typhoon-ai/typhoon-whisper-turbo` | set to `typhoon-ai/typhoon-whisper-large-v3` for accuracy over speed |
| `ASR_DEVICE` | `auto` | `auto` \| `cuda` \| `mps` \| `cpu` |
| `ASR_BACKEND` | `auto` | `auto` \| `transformers` \| `mlx`; `auto` means MLX on Apple Silicon |
| `ASR_MODEL_MLX` | `chayapats/typhoon-whisper-turbo-mlx` | the MLX conversion of `ASR_MODEL`; keep the two in step |
| `HF_TOKEN` | unset | required for diarization |
| `DIARIZATION_MODEL` | `pyannote/speaker-diarization-community-1` | `rewayai/suplime-large` is opt-in and **non-commercial**, see [above](#optional-suplime-l-diarization-non-commercial-only) |
| `LLM_ENABLED` | `true` | `false` disables third-party summarization entirely |
| `LLM_PROVIDER` | `deepseek` | `deepseek` \| `anthropic` \| `gemini` (`GEMINI_API_KEY`, `GEMINI_MODEL`) |
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

GET    /api/meetings/:id/transcript  {segments, speakers, edited}
PATCH  /api/meetings/:id/transcript  {segments} -- full replace, sets edited=1
PATCH  /api/meetings/:id/speakers    {"SPEAKER_00": "คุณสมชาย"}; blank resets to the key

POST   /api/meetings/:id/summarize   -> 202 {meeting_id, job_id}
GET    /api/meetings/:id/summary     {data: MinutesJSON, model, has_document, created_at}
PATCH  /api/meetings/:id/summary     MinutesJSON -- saves and re-renders the .docx
GET    /api/meetings/:id/document    streams the .docx

DELETE /api/meetings/:id             rows + files
GET    /api/health                   {api, db, worker_heartbeat, worker_alive, llm}
```

The transcript is replaced whole rather than patched per row: two people
editing one transcript is not a supported scenario, and a partial-patch
protocol invites the silent lost update that a full replace makes impossible.

`POST /summarize` returns the job already running if one is, so an impatient
second click does not queue a duplicate LLM run.

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

## License

Sarai AI is released under the [MIT License](LICENSE).

Third-party components keep their own licenses and are not part of this repo:

- **Model weights** are downloaded at runtime from HuggingFace, each under its
  own license. The pyannote diarization and segmentation models are gated:
  you must accept their terms with your own HuggingFace account (see
  [Requirements](#requirements)). The optional SUPlime-L diarization weights
  (`rewayai/suplime-large`) are **CC BY-NC 4.0, non-commercial only**; they are
  never downloaded unless you select them. Check the model cards for
  `typhoon-ai/typhoon-whisper-*` before commercial use.
- **Sarabun font** is fetched by `scripts/fetch_fonts.py` and is licensed under
  the SIL Open Font License (OFL).
