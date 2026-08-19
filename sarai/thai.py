"""Thai text handling.

Two rules drive everything here:

* Thai has no spaces between words, so any truncation or chunking that splits
  on whitespace either does nothing or cuts a word in half. Length is counted
  in characters, and word-aware truncation goes through `pythainlp`.
* ASR output has predictable Thai-specific defects -- a spelled-out ไม้ยมก, a
  Buddhist-era year -- that are cheap to repair before the LLM ever sees them.

`pythainlp` is a worker-group dependency. Everything here degrades to a
character-based path when it is missing, so the API can import this module.
"""

from __future__ import annotations

import re

# The repetition marker. ASR frequently writes it as the word "ๆ" preceded by a
# space, or spells it out as "ไม้ยมก", or duplicates the previous word instead.
MAI_YAMOK = "ๆ"

_SPACE_BEFORE_YAMOK = re.compile(r"\s+ๆ")
_YAMOK_SPELLED = re.compile(r"\s*ไม้ยมก")
_REPEATED_THAI_WORD = re.compile(r"([ก-ฮ][ก-๎]{1,7}) \1(?![ก-๎])")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")

# Any four-digit year at or above this is a Buddhist-era year. 2500 BE is 1957
# CE; no meeting transcript carries a CE year that large.
BE_CUTOFF = 2500
BE_OFFSET = 543

_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def normalize(text: str) -> str:
    """Repair the Thai-specific defects an ASR pass reliably introduces.

    Conservative on purpose: this runs on every segment before summarization,
    and a normalizer that rewrites meaning is worse than no normalizer.
    """
    if not text:
        return text
    out = _YAMOK_SPELLED.sub(MAI_YAMOK, text)
    out = _SPACE_BEFORE_YAMOK.sub(MAI_YAMOK, out)
    # "ครับ ครับ" -> "ครับๆ" only for short words: a repeated long phrase is
    # far more likely to be someone actually saying it twice.
    out = _REPEATED_THAI_WORD.sub(rf"\1{MAI_YAMOK}", out)
    out = _MULTI_SPACE.sub(" ", out)
    return out.strip()


def be_to_ce(year: int) -> int:
    """Buddhist era to common era. Years below the cutoff pass through."""
    return year - BE_OFFSET if year >= BE_CUTOFF else year


def convert_be_years(text: str) -> str:
    """Rewrite Buddhist-era years in place: 'ปี 2569' -> 'ปี 2026'."""

    def repl(match: re.Match[str]) -> str:
        year = int(match.group(1))
        return str(be_to_ce(year)) if year >= BE_CUTOFF else match.group(1)

    return _YEAR.sub(repl, text)


def char_len(text: str) -> int:
    """Length in characters. Never `len(text.split())` -- see the module docstring."""
    return len(text)


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    """Cut to `limit` characters, at a word boundary when pythainlp is available.

    Falls back to a hard character cut, which can land inside a Thai word but
    never inside a UTF-8 sequence, and never silently drops the tail.
    """
    if limit <= 0 or len(text) <= limit:
        return text
    budget = max(0, limit - len(suffix))
    try:
        from pythainlp.tokenize import word_tokenize
    except ImportError:
        return text[:budget] + suffix

    out: list[str] = []
    used = 0
    for token in word_tokenize(text, keep_whitespace=True):
        if used + len(token) > budget:
            break
        out.append(token)
        used += len(token)
    if not out:
        return text[:budget] + suffix
    return "".join(out).rstrip() + suffix
