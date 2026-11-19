"""Compare diarization models on your own recordings against hand-made RTTMs.

    uv run python scripts/eval_diarization.py DATA_DIR
    uv run python scripts/eval_diarization.py DATA_DIR --models community-1 suplime-large \\
        --out results/diarization.csv --device cuda

DATA_DIR holds audio files (any format the app accepts) and, next to each, a
reference RTTM with the same stem: `board-2026-10.m4a` + `board-2026-10.rttm`.
Audio without a reference is skipped.

Every file goes through the worker's own decoding path -- ffmpeg to 16 kHz mono
WAV (sarai.audio.normalize), soundfile (stages.read_wav), then the in-memory
waveform dict (diarize.pipeline_input) -- and each pipeline runs through
diarize._run_pipeline, so the mps -> cpu fallback applies here as well.

Scoring (pyannote.metrics DiarizationErrorRate):
  - collar 0 s, overlapping speech scored (skip_overlap=False);
  - no oracle speaker count: the pipeline gets no num/min/max_speakers;
  - UEM = the whole file, so silence the model labels as speech is a false alarm;
  - the hypothesis is the annotation the worker uses (`exclusive`, at most one
    speaker at a time) unless you pass --output regular, which scores the
    overlap-aware annotation instead. Exclusive output cannot get the second
    voice in an overlap right, so expect its missed-detection share to be higher;
  - raw pipeline output, before the worker's turn shaping (merge < 0.5 s gaps,
    split > 30 s turns). Shaping is identical for every model.

Per file and model it reports DER, missed speech, false alarm and confusion (each
as a fraction of reference speech, so they sum to DER), the reference and
hypothesis speaker counts, wall-clock seconds (pipeline call only, after one
untimed warm-up per model), real-time factor and peak VRAM (CUDA only; blank on
cpu/mps). The macro average weights every file equally; speaker-count accuracy
is the share of files where the counts match exactly. Results go to a CSV (one
row per file and model, plus one MACRO row per model) and to stdout. With
--save-rttm the hypotheses are written out too, for inspecting errors.

Making reference RTTMs
----------------------
RTTM is one line per speaker turn:

    SPEAKER <file-id> 1 <start-seconds> <duration-seconds> <NA> <NA> <speaker> <NA> <NA>

Only start, duration and speaker matter here; the file id should be the audio
file's stem. Speaker names only need to be consistent within one file -- the
metric finds the best mapping between your names and the model's labels.

Quickest route with Audacity (free):
  1. Open the recording and add a label track (Tracks > Add New > Label Track).
  2. Select each stretch of speech, press Ctrl+B and type the speaker's name.
     When two people talk at once, give both of them a label over that stretch --
     labels may overlap.
  3. File > Export > Export Labels -> board-2026-10.txt (tab-separated:
     start, end, name).
  4. Convert:
       awk -F'\\t' -v id=board-2026-10 '{printf "SPEAKER %s 1 %.3f %.3f <NA> <NA> %s <NA> <NA>\\n",
           id, $1, $2-$1, $3}' board-2026-10.txt > board-2026-10.rttm

Labelling rules that keep the numbers honest with a 0 s collar:
  - Label speech, not turns: end a label at pauses longer than ~0.5 s, but do
    not chase every breath. Use the same rule in every file.
  - Include short backchannels ("ครับ", "ค่ะ", "อืม") as their own labels; the
    models are scored on them.
  - Zoom to the waveform at boundaries. 0.2 s of sloppiness per turn adds up.
  - Do not start from one model's output and correct it: the reference then
    inherits that model's boundaries and favours it. Label from scratch.
  - 3-5 files of 5-10 minutes covering your real conditions (room mic, Zoom,
    many speakers, Thai/English switching) say more than one long file.
"""

from __future__ import annotations

import argparse
import csv
import gc
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

# Running this file directly puts scripts/ on sys.path, not the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sarai import audio  # noqa: E402
from sarai.config import ALLOWED_UPLOAD_EXTENSIONS, get_settings  # noqa: E402
from sarai.worker import diarize  # noqa: E402
from sarai.worker.stages import read_wav  # noqa: E402

ALIASES = {
    "community-1": "pyannote/speaker-diarization-community-1",
    "suplime-large": "rewayai/suplime-large",
    "suplime": "rewayai/suplime",
}
DEFAULT_MODELS = ["community-1", "suplime-large"]
WARMUP_SECONDS = 10


@dataclass
class Row:
    model: str
    file: str
    duration_s: float | None = None
    der: float | None = None
    missed: float | None = None
    false_alarm: float | None = None
    confusion: float | None = None
    ref_speakers: int | None = None
    hyp_speakers: int | None = None
    speaker_count_ok: float | None = None
    wall_s: float | None = None
    rtf: float | None = None
    peak_vram_mib: float | None = None
    error: str = ""


@dataclass
class Item:
    stem: str
    wav: Path
    reference: Any  # pyannote.core.Annotation


def find_pairs(data_dir: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for src in sorted(data_dir.iterdir()):
        if src.suffix.lower() not in ALLOWED_UPLOAD_EXTENSIONS:
            continue
        rttm = src.with_suffix(".rttm")
        if rttm.exists():
            pairs.append((src, rttm))
        else:
            print(f"skip {src.name}: no {rttm.name}", file=sys.stderr)
    return pairs


def load_reference(rttm: Path, stem: str) -> Any:
    from pyannote.database.util import load_rttm

    annotations = load_rttm(str(rttm))  # type: ignore[no-untyped-call]
    if not annotations:
        raise ValueError(f"{rttm} has no SPEAKER lines")
    if stem in annotations:
        return annotations[stem]
    if len(annotations) == 1:
        return next(iter(annotations.values()))
    raise ValueError(f"{rttm} holds several file ids and none is {stem!r}")


def score(reference: Any, hypothesis: Any, duration: float) -> dict[str, float]:
    from pyannote.core import Segment, Timeline
    from pyannote.metrics.diarization import DiarizationErrorRate

    metric = DiarizationErrorRate(collar=0.0, skip_overlap=False)
    uem = Timeline([Segment(0.0, duration)])
    detail = metric(reference, hypothesis, uem=uem, detailed=True)
    total = detail["total"] or 1.0
    return {
        "der": detail["diarization error rate"],
        "missed": detail["missed detection"] / total,
        "false_alarm": detail["false alarm"] / total,
        "confusion": detail["confusion"] / total,
    }


def load_model(model: str, device: str) -> Any:
    import torch
    from pyannote.audio import Pipeline

    diarize.require_model_package(model)
    pipeline = Pipeline.from_pretrained(model, token=get_settings().hf_token)
    if pipeline is None:
        raise RuntimeError(f"no pipeline for {model}.\n{diarize.gate_help(model)}")
    pipeline.to(torch.device(device))
    return pipeline


def hypothesis_of(output: Any, which: str) -> Any:
    if which == "regular":
        return getattr(output, "speaker_diarization", output)
    return diarize.to_annotation(output)


def evaluate_model(
    model: str, items: list[Item], device: str, which: str, rttm_dir: Path | None
) -> list[Row]:
    import torch

    cuda = device == "cuda"
    print(f"\n== {model} on {device}", flush=True)
    try:
        pipeline = load_model(model, device)
    except Exception as exc:  # noqa: BLE001 - report the failure, keep comparing others
        print(f"   could not load: {exc}", file=sys.stderr)
        return [Row(model, item.stem, error=f"load: {exc}") for item in items]

    rows: list[Row] = []
    warmed = False
    for item in items:
        row = Row(model, item.stem)
        try:
            samples, sample_rate = read_wav(item.wav)
            row.duration_s = len(samples) / sample_rate
            if not warmed:
                head = samples[: sample_rate * WARMUP_SECONDS]
                diarize._run_pipeline(pipeline, diarize.pipeline_input(item.wav, head, sample_rate))
                warmed = True
            if cuda:
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            output = diarize._run_pipeline(
                pipeline, diarize.pipeline_input(item.wav, samples, sample_rate)
            )
            if cuda:
                torch.cuda.synchronize()
            row.wall_s = time.perf_counter() - started
            row.rtf = row.wall_s / row.duration_s if row.duration_s else None
            if cuda:
                row.peak_vram_mib = torch.cuda.max_memory_allocated() / 2**20
            hypothesis = hypothesis_of(output, which)
            for key, value in score(item.reference, hypothesis, row.duration_s).items():
                setattr(row, key, value)
            row.ref_speakers = len(item.reference.labels())
            row.hyp_speakers = len(hypothesis.labels())
            row.speaker_count_ok = float(row.ref_speakers == row.hyp_speakers)
            if rttm_dir is not None:
                out = rttm_dir / model.replace("/", "__") / f"{item.stem}.rttm"
                out.parent.mkdir(parents=True, exist_ok=True)
                hypothesis.uri = item.stem
                with out.open("w") as handle:
                    hypothesis.write_rttm(handle)
        except Exception as exc:  # noqa: BLE001 - one bad file must not end the run
            row.error = f"{type(exc).__name__}: {exc}"
        print(_line(row), flush=True)
        rows.append(row)

    del pipeline
    gc.collect()
    if cuda:
        torch.cuda.empty_cache()
    return rows


def macro(model: str, rows: list[Row]) -> Row:
    ok = [r for r in rows if not r.error]
    failed = len(rows) - len(ok)
    out = Row(model, "MACRO", error=f"{failed} file(s) failed" if failed else "")
    numeric = [f.name for f in fields(Row) if f.name not in ("model", "file", "error")]
    for name in numeric:
        values = [getattr(r, name) for r in ok if getattr(r, name) is not None]
        if values:
            setattr(out, name, statistics.fmean(values))
    return out


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:.1f}%"


def _num(value: float | None, digits: int = 1) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _line(r: Row) -> str:
    if r.der is None:
        return f"{r.model:<42} {r.file:<28} ERROR {r.error}"
    spk = "-" if r.hyp_speakers is None else f"{r.hyp_speakers}/{r.ref_speakers}"
    return (
        f"{r.model:<42} {r.file:<28} DER {_pct(r.der):>6}  miss {_pct(r.missed):>6}  "
        f"FA {_pct(r.false_alarm):>6}  conf {_pct(r.confusion):>6}  spk {spk:>5}  "
        f"{_num(r.wall_s):>7}s  RTF {_num(r.rtf, 3)}  VRAM {_num(r.peak_vram_mib, 0)} MiB"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("data_dir", type=Path, help="audio files + same-stem .rttm references")
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help=f"aliases {sorted(ALIASES)} or full Hugging Face ids (default: %(default)s)",
    )
    parser.add_argument("--out", type=Path, default=Path("diarization_eval.csv"))
    parser.add_argument("--device", help="cuda | mps | cpu (default: DIARIZATION_DEVICE)")
    parser.add_argument("--output", choices=["exclusive", "regular"], default="exclusive")
    parser.add_argument("--save-rttm", type=Path, help="write hypothesis RTTMs under this dir")
    args = parser.parse_args()

    pairs = find_pairs(args.data_dir)
    if not pairs:
        print(f"no audio + .rttm pairs in {args.data_dir}", file=sys.stderr)
        return 1
    device = args.device or diarize.diarization_device()
    models = [ALIASES.get(m, m) for m in args.models]
    for model in models:
        if warning := diarize.license_warning(model):
            print(f"note: {warning}", file=sys.stderr)

    rows: list[Row] = []
    with tempfile.TemporaryDirectory(prefix="sarai-eval-") as tmp:
        items = []
        for src, rttm in pairs:
            print(f"decoding {src.name}", flush=True)
            wav = audio.normalize(src, Path(tmp) / f"{src.stem}.wav")
            items.append(Item(src.stem, wav, load_reference(rttm, src.stem)))
        per_model = {
            m: evaluate_model(m, items, device, args.output, args.save_rttm) for m in models
        }

    summary = []
    for model, model_rows in per_model.items():
        rows.extend(model_rows)
        summary.append(macro(model, model_rows))
    rows.extend(summary)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[f.name for f in fields(Row)])
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)

    print(f"\n== per file ({args.output} output, collar 0 s, overlap scored)")
    for r in rows[: -len(summary)]:
        print(_line(r))
    print(f"\n== macro average over {len(items)} file(s)")
    for r in summary:
        print(f"{_line(r)}  spk-count acc {_pct(r.speaker_count_ok)}  {r.error}".rstrip())
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
