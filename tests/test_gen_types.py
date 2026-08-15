"""web/src/types.ts must never drift from the Pydantic models."""

from __future__ import annotations

from pathlib import Path

from scripts.gen_types import generate

TYPES_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "types.ts"


def test_generated_types_are_committed() -> None:
    assert TYPES_TS.exists(), "run `make types`"
    assert TYPES_TS.read_text(encoding="utf-8") == generate(), (
        "web/src/types.ts is stale -- run `make types`"
    )


def test_enums_render_as_string_unions() -> None:
    out = generate()
    assert 'export type Stage = "queued" | "normalizing"' in out
    assert 'export type LanguageHint = "auto" | "th" | "en";' in out


def test_optional_and_nullable_fields() -> None:
    out = generate()
    assert "  confidence?: number | null;" in out
    assert "  speakers: Record<string, string>;" in out
    assert "  segments: Segment[];" in out
