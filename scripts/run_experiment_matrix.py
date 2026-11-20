"""Run the ASR x diarization x LLM experiment matrix on one recording.

    python scripts/run_experiment_matrix.py all --wav data/work/<id>.wav \\
        --title "..." --out data/experiments/<name>

Phases, each in its own subprocess so every model gets the whole GPU:

  diarize  one pass per diarization model            -> turns/<diar>.json
  asr      one model load per ASR model, all turn sets -> transcripts/<asr>__<diar>.json
  llm      one provider at a time, all transcripts     -> runs/<run>/minutes.{json,pdf}
  report   comparison + every run's minutes            -> report.pdf

It reuses the worker's own pieces (diarize.diarize, asr.transcribe and its
hallucination guard, llm.analyze + summarize, docgen.pdf), so a run here is
what the app would produce with the same settings. Finished outputs are
skipped on a re-run, so an interrupted matrix resumes where it stopped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ASR = {
    "large-v3": "typhoon-ai/typhoon-whisper-large-v3",
    "turbo": "typhoon-ai/typhoon-whisper-turbo",
}
DIAR = {
    "pyannote": "pyannote/speaker-diarization-community-1",
}
LLM = ("deepseek", "gemini")  # deepseek first: gemini 503s can stall for an hour

# The user's numbering, kept so the report reads in the same order.
RUNS = [
    ("large-v3", "pyannote", "deepseek"),
    ("large-v3", "pyannote", "gemini"),
    ("turbo", "pyannote", "deepseek"),
    ("turbo", "pyannote", "gemini"),
]

log = logging.getLogger("matrix")


def run_name(i: int, asr: str, diar: str, llm: str) -> str:
    return f"{i:02d}_{asr}_{diar}_{llm}"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _peak_vram_gb() -> float | None:
    import torch

    if not torch.cuda.is_available():
        return None
    return round(torch.cuda.max_memory_allocated() / 2**30, 2)


# --------------------------------------------------------------------------- diarize


def phase_diarize(args: argparse.Namespace) -> None:
    from sarai.worker import diarize, stages

    out = args.out / "turns" / f"{args.key}.json"
    if out.exists():
        log.info("skip diarize %s (exists)", args.key)
        return
    samples, sr = stages.read_wav(args.wav)
    t0 = time.perf_counter()
    if diarize.load_pipeline() is None:
        raise SystemExit(f"diarization model {DIAR[args.key]} failed to load")
    load_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    turns = diarize.diarize(args.wav, samples, sr)
    run_s = time.perf_counter() - t0
    _write_json(
        out,
        {
            "model": DIAR[args.key],
            "audio_seconds": len(samples) / sr,
            "load_seconds": round(load_s, 1),
            "diarize_seconds": round(run_s, 1),
            "peak_vram_gb": _peak_vram_gb(),
            "speakers": sorted({t.speaker for t in turns}),
            "turns": [[t.start, t.end, t.speaker] for t in turns],
        },
    )
    log.info("diarize %s: %d turns in %.0fs", args.key, len(turns), run_s)


# --------------------------------------------------------------------------- asr


def phase_asr(args: argparse.Namespace) -> None:
    from sarai.models import LanguageHint
    from sarai.worker import asr, stages

    samples, sr = stages.read_wav(args.wav)
    t0 = time.perf_counter()
    asr.load_model()
    load_s = time.perf_counter() - t0
    for diar in DIAR:
        out = args.out / "transcripts" / f"{args.key}__{diar}.json"
        src = args.out / "turns" / f"{diar}.json"
        if out.exists() or not src.exists():
            log.info("skip asr %s on %s", args.key, diar)
            continue
        turns = json.loads(src.read_text(encoding="utf-8"))["turns"]
        segments, dropped = [], 0
        t0 = time.perf_counter()
        for i, (start, end, speaker) in enumerate(turns, 1):
            clip = samples[max(0, int(start * sr)) : min(len(samples), int(end * sr))]
            if clip.size == 0:
                dropped += 1
                continue
            res = asr.transcribe(clip, LanguageHint.AUTO, None)
            if asr.looks_hallucinated(res.text, end - start):
                dropped += 1
                continue
            segments.append(
                {
                    "id": len(segments),
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "speaker": speaker,
                    "text": res.text,
                    "confidence": res.confidence,
                }
            )
            if i % 100 == 0:
                log.info("asr %s/%s %d/%d", args.key, diar, i, len(turns))
        _write_json(
            out,
            {
                "asr_model": ASR[args.key],
                "diarization": diar,
                "load_seconds": round(load_s, 1),
                "asr_seconds": round(time.perf_counter() - t0, 1),
                "peak_vram_gb": _peak_vram_gb(),
                "turns": len(turns),
                "dropped": dropped,
                "segments": segments,
            },
        )
        log.info("asr %s/%s: %d segments, %d dropped", args.key, diar, len(segments), dropped)


# --------------------------------------------------------------------------- llm


async def _with_retry(label: str, fn, tries: int = 10):  # type: ignore[no-untyped-def]
    from sarai.llm import LLMError

    for attempt in range(1, tries + 1):
        try:
            return await fn()
        except LLMError as exc:
            # Gemini answers 503 "high demand" in bursts; DeepSeek times out now and then.
            if attempt == tries:
                raise
            wait = min(600, 60 * attempt)
            log.warning("%s failed (%s); retry %d/%d in %ds", label, str(exc)[:160], attempt, tries, wait)
            await asyncio.sleep(wait)
    raise AssertionError("unreachable")


def phase_llm(args: argparse.Namespace) -> None:
    from sarai.config import get_settings
    from sarai.docgen.pdf import render_pdf
    from sarai.llm import summarize_minutes
    from sarai.llm.analyze import analyze, fallback_labels
    from sarai.models import Segment, SummarizeInput

    settings = get_settings()
    for i, (a, d, provider) in enumerate(RUNS, 1):
        if provider != args.key:
            continue
        name = run_name(i, a, d, provider)
        rdir = args.out / "runs" / name
        src = args.out / "transcripts" / f"{a}__{d}.json"
        if (rdir / "result.json").exists() or not src.exists():
            log.info("skip llm %s", name)
            continue
        tr = json.loads(src.read_text(encoding="utf-8"))
        segments = [Segment(**s) for s in tr["segments"]]
        keys = sorted({s.speaker for s in segments})
        base = SummarizeInput(title=args.title, segments=segments, speakers={k: k for k in keys})

        t0 = time.perf_counter()
        error = None
        try:
            mtype, names = asyncio.run(
                _with_retry(f"{name} analyze", lambda: analyze(base, settings))
            )
            labels = fallback_labels(keys)
            labels.update({k: v for k, v in names.items() if k in labels})
            inp = base.model_copy(update={"meeting_type": mtype, "speakers": labels})
            analyze_s = time.perf_counter() - t0
            t0 = time.perf_counter()
            minutes, model, dropped = asyncio.run(
                _with_retry(f"{name} summarize", lambda: summarize_minutes(inp, settings))
            )
            summarize_s = time.perf_counter() - t0
        except Exception as exc:  # noqa: BLE001 - record the failure, keep going
            log.exception("run %s failed", name)
            error = f"{type(exc).__name__}: {exc}"

        rdir.mkdir(parents=True, exist_ok=True)
        if error is None:
            (rdir / "minutes.json").write_text(
                minutes.model_dump_json(indent=2), encoding="utf-8"
            )
            render_pdf(minutes, rdir / "minutes.pdf", model=model, meeting_type=mtype)
            _write_json(rdir / "transcript.json", {"speakers": labels, **tr})
        _write_json(
            rdir / "result.json",
            {
                "run": i,
                "asr": ASR[a],
                "diarization": DIAR[d],
                "llm_provider": provider,
                "error": error,
                **(
                    {}
                    if error
                    else {
                        "llm_model": model,
                        "meeting_type": mtype.value,
                        "speaker_names": labels,
                        "named_speakers": sum(1 for k in keys if k in names),
                        "action_items": len(minutes.action_items),
                        "decisions": len(minutes.decisions),
                        "topics": len(minutes.discussion),
                        "dropped_quotes": dropped,
                        "analyze_seconds": round(analyze_s, 1),
                        "summarize_seconds": round(summarize_s, 1),
                    }
                ),
            },
        )
        log.info("llm %s done%s", name, f" (FAILED: {error[:120]})" if error else "")


# --------------------------------------------------------------------------- report


def _fmt_s(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{int(v // 60)}m{int(v % 60):02d}s"


def phase_report(args: argparse.Namespace) -> None:
    from html import escape as e

    from weasyprint import HTML

    from sarai.docgen.fonts import FONT_NAME
    from sarai.docgen.pdf import _font_faces, to_html
    from sarai.models import MeetingType, MinutesJSON

    turns = {
        d: json.loads((args.out / "turns" / f"{d}.json").read_text(encoding="utf-8"))
        for d in DIAR
        if (args.out / "turns" / f"{d}.json").exists()
    }
    trs = {}
    for a in ASR:
        for d in DIAR:
            p = args.out / "transcripts" / f"{a}__{d}.json"
            if p.exists():
                trs[(a, d)] = json.loads(p.read_text(encoding="utf-8"))
    audio_s = next(iter(turns.values()))["audio_seconds"] if turns else None

    rows, sections, minutes_docs = [], [], []
    totals: list[tuple[int, str, str, str, float | None]] = []
    hl = {int(x) for x in args.highlight.split(",") if x.strip()}
    for i, (a, d, llm) in enumerate(RUNS, 1):
        name = run_name(i, a, d, llm)
        mark = " class='hl'" if i in hl else ""
        rp = args.out / "runs" / name / "result.json"
        r = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {"error": "not run"}
        tr = trs.get((a, d), {})
        tu = turns.get(d, {})
        ok = not r.get("error")
        llm_s = (r.get("analyze_seconds") or 0) + (r.get("summarize_seconds") or 0)
        # End-to-end for this combination, as one job would run it: both model
        # loads, diarization, ASR over every turn, and both LLM calls.
        total_s = (
            tu.get("load_seconds", 0) + tu.get("diarize_seconds", 0)
            + tr.get("load_seconds", 0) + tr.get("asr_seconds", 0) + llm_s
            if ok and tu and tr else None
        )
        totals.append((i, a, d, llm, total_s))
        rows.append(
            f"<tr{mark}>"
            f"<td>{i}</td><td>{e(a)}</td><td>{e(d)}</td><td>{e(llm)}</td>"
            f"<td>{len(tu.get('speakers', [])) or '-'}</td>"
            f"<td>{len(tr.get('segments', [])) or '-'}</td>"
            f"<td>{_fmt_s(tu.get('diarize_seconds'))}</td>"
            f"<td>{_fmt_s(tr.get('asr_seconds'))}</td>"
            f"<td>{_fmt_s(llm_s) if ok else '-'}</td>"
            f"<td><b>{_fmt_s(total_s)}</b></td>"
            f"<td>{e(r.get('meeting_type', '-'))}</td>"
            f"<td>{r.get('named_speakers', '-')}</td>"
            f"<td>{r.get('decisions', '-')}</td><td>{r.get('action_items', '-')}</td>"
            f"<td>{'ok' if ok else 'FAILED'}</td>"
            "</tr>"
        )
        if ok:
            names = ", ".join(f"{k}={v}" for k, v in r["speaker_names"].items())
            sections.append(
                f"<h3{mark}>{i}. {e(a)} + {e(d)} + {e(llm)} ({e(r['llm_model'])})</h3>"
                f"<p class='meta'>Speakers: {e(names)}</p>"
            )
            m = MinutesJSON.model_validate_json(
                (args.out / "runs" / name / "minutes.json").read_text(encoding="utf-8")
            )
            sections.append(f"<p>{e(m.summary)}</p>")
            html = to_html(m, model=r["llm_model"], meeting_type=MeetingType(r["meeting_type"]))
            banner = (
                f"<p style='background:#f4efe7;padding:4pt 8pt;font-size:10pt'>"
                f"Run {i}: ASR {e(a)} · diarization {e(d)} · LLM {e(llm)}</p>"
            )
            minutes_docs.append(html.replace("<body>", "<body>" + banner, 1))
        else:
            sections.append(f"<h3>{i}. {e(a)} + {e(d)} + {e(llm)}</h3><p>FAILED: {e(str(r.get('error')))}</p>")

    asr_rows = "".join(
        f"<tr><td>{e(a)}</td><td>{e(d)}</td><td>{t['turns']}</td><td>{len(t['segments'])}</td>"
        f"<td>{t['dropped']}</td><td>{_fmt_s(t['asr_seconds'])}</td>"
        f"<td>{t['asr_seconds'] / audio_s:.2f}</td><td>{t.get('peak_vram_gb') or '-'}</td></tr>"
        for (a, d), t in trs.items()
    ) if audio_s else ""
    diar_rows = "".join(
        f"<tr><td>{e(d)}</td><td>{len(t['speakers'])}</td><td>{len(t['turns'])}</td>"
        f"<td>{_fmt_s(t['diarize_seconds'])}</td><td>{t['diarize_seconds'] / t['audio_seconds']:.3f}</td>"
        f"<td>{t.get('peak_vram_gb') or '-'}</td></tr>"
        for d, t in turns.items()
    )

    # Same-segment comparison: the first minutes of each transcript side by side.
    sample = []
    for (a, d), t in trs.items():
        lines = [s for s in t["segments"] if s["start"] < 120][:8]
        body = "<br>".join(
            f"<b>{e(s['speaker'])}</b> [{int(s['start'] // 60)}:{int(s['start'] % 60):02d}] {e(s['text'])}"
            for s in lines
        )
        sample.append(f"<h3>{e(a)} + {e(d)}</h3><p class='small'>{body}</p>")

    css = _font_faces() + f"""
@page {{ size: A4; margin: 14mm 12mm; @bottom-right {{ content: counter(page) " / " counter(pages); font-size: 8pt; }} }}
body {{ font-family: '{FONT_NAME}', sans-serif; font-size: 10.5pt; line-height: 1.45; }}
h1 {{ font-size: 17pt; margin: 0 0 4pt; }} h2 {{ font-size: 13pt; margin: 14pt 0 4pt; }}
h3 {{ font-size: 11.5pt; margin: 10pt 0 2pt; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9pt; }}
th, td {{ border: 0.5pt solid #b8ad9f; padding: 2pt 4pt; text-align: left; vertical-align: top; }}
th {{ background: #f4efe7; }} tr.hl td {{ background: #fff3b0; font-weight: bold; }}
h3.hl {{ background: #fff3b0; padding: 2pt 4pt; }} .meta, .small {{ font-size: 9pt; color: #555; }}
"""
    report = f"""<html><head><meta charset='utf-8'><style>{css}</style></head><body>
<h1>Experiment matrix: {e(args.title)}</h1>
<p class='meta'>Audio {_fmt_s(audio_s)} · GPU {e(args.gpu)} · generated {time.strftime('%Y-%m-%d %H:%M')}.
Each LLM run first names speakers and detects the meeting type, then writes the minutes, like the app's hands-off flow.
{"Highlighted rows: runs " + ", ".join(map(str, sorted(hl))) + ". " if hl else ""}Times are wall clock. Total = model loads + diarization + ASR + LLM for that run. RTF = processing time / audio length (lower is faster).</p>
<h2>Summary</h2>
<table><tr><th>#</th><th>ASR</th><th>Diar.</th><th>LLM</th><th>Spk</th><th>Seg</th><th>Diar time</th>
<th>ASR time</th><th>LLM time</th><th>Total</th><th>Type</th><th>Named</th><th>Dec.</th><th>Actions</th><th>Status</th></tr>
{''.join(rows)}</table>
<h2>Diarization</h2>
<table><tr><th>Model</th><th>Speakers</th><th>Turns</th><th>Time</th><th>RTF</th><th>Peak VRAM GB</th></tr>{diar_rows}</table>
<h2>ASR</h2>
<table><tr><th>ASR</th><th>Diar. turns from</th><th>Turns</th><th>Segments</th><th>Dropped</th><th>Time</th><th>RTF</th><th>Peak VRAM GB</th></tr>{asr_rows}</table>
<h2>Run summaries</h2>{''.join(sections)}
<h2 style='page-break-before:always'>Transcript sample (first 2 minutes)</h2>{''.join(sample)}
<p class='meta'>Full minutes for every run follow, one per section.</p>
</body></html>"""

    _write_json(
        args.out / "timings.json",
        [{"run": i, "asr": a, "diarization": d, "llm": l, "total_seconds": None if t is None else round(t, 1)} for i, a, d, l, t in totals],
    )
    docs = [HTML(string=report).render()] + [HTML(string=h).render() for h in minutes_docs]
    pages = [p for d in docs for p in d.pages]
    dest = args.out / "report.pdf"
    docs[0].copy(pages).write_pdf(str(dest))
    log.info("report written to %s (%d pages)", dest, len(pages))


# --------------------------------------------------------------------------- driver


def phase_all(args: argparse.Namespace) -> None:
    base = [sys.executable, __file__, "--wav", str(args.wav), "--out", str(args.out),
            "--title", args.title, "--gpu", args.gpu]
    steps = [("diarize", d, {"DIARIZATION_MODEL": DIAR[d]}) for d in DIAR]
    steps += [("asr", a, {"ASR_MODEL": ASR[a]}) for a in ASR]
    steps += [("llm", p, {"LLM_PROVIDER": p}) for p in LLM]
    for phase, key, env in steps:
        log.info("=== %s %s", phase, key)
        rc = subprocess.run([*base, phase, key], env={**os.environ, **env}).returncode
        if rc != 0:
            log.error("%s %s exited %d; continuing", phase, key, rc)
    subprocess.run([*base, "report", "-"], check=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--wav", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--title", default="")
    p.add_argument("--gpu", default="")
    p.add_argument("--highlight", default="", help="report: run numbers to highlight, e.g. 2,4")
    p.add_argument("phase", choices=["all", "diarize", "asr", "llm", "report"])
    p.add_argument("key", nargs="?", default="-")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    {"all": phase_all, "diarize": phase_diarize, "asr": phase_asr,
     "llm": phase_llm, "report": phase_report}[args.phase](args)


if __name__ == "__main__":
    main()
